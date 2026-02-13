#!/usr/bin/env python3
"""
Mewgenics Translator (OpenAI LLM)

pip install openai

Three-way translation:
  data/extracted         — current English CSVs from the game (read-only input)
  data/{lang}/translated — CSVs with translations in the target column
  data/{lang}/glossary.csv    — optional glossary (en,<target_col>) for guided translation
  data/{lang}/prompt.txt      — optional custom translation instructions

The 'en' column is preserved in translated, so changes in the source
English text are detected by comparing 'en' columns between extracted and
translated files. Only new/changed entries are re-translated.

Glossary terms are included in the LLM prompt so it uses correct grammatical
forms (cases, declensions) in context.

Usage:
    python translate.py                        # translate all CSVs (default: uk)
    python translate.py --lang <code>          # translate to a specific language
    python translate.py --column jp            # write into 'jp' column instead of 'sp'
    python translate.py --model gpt-4o         # use a different model
    python translate.py --workers 16           # more parallel requests
    python translate.py --file items.csv       # translate one file
    python translate.py --resume               # continue after interrupt

Environment:
    OPENAI_BASE_URL - optional, for custom OpenAI-compatible API endpoint
    OPENAI_API_KEY — required
"""

import csv
import os
import sys
import json
import time
import io
import re
import argparse
import glob
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI

EXTRACTED_DIR = 'data/extracted'
DEFAULT_LANG = 'uk'
DEFAULT_COLUMN = 'sp'
DEFAULT_MODEL = 'gpt-5-mini'
DEFAULT_WORKERS = 8
BATCH_SIZE = 20

LANG_NAMES = {
    'uk': 'Ukrainian',
    'de': 'German',
    'fr': 'French',
    'es': 'Spanish',
    'it': 'Italian',
    'pt': 'Portuguese',
    'pl': 'Polish',
    'ja': 'Japanese',
    'ko': 'Korean',
    'zh': 'Chinese (Simplified)',
}


def translated_dir(lang):
    return f'data/{lang}/translated'


def progress_file(lang):
    return f'data/{lang}/progress.json'


def load_progress(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_progress(data, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_csv_file(filepath):
    """Read a CSV file and return (header, rows)."""
    with open(filepath, 'r', encoding='utf-8-sig', errors='replace') as f:
        content = f.read()
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        return None, None
    return rows[0], rows


def find_column(header, name):
    try:
        return header.index(name)
    except ValueError:
        return None


def build_column_map(filepath, column):
    """Read a CSV and return {key: value} for the given column."""
    header, rows = read_csv_file(filepath)
    if header is None:
        return {}
    key_idx = find_column(header, 'KEY')
    if key_idx is None:
        key_idx = 0
    col_idx = find_column(header, column)
    if col_idx is None:
        return {}
    result = {}
    for row in rows[1:]:
        if key_idx < len(row) and col_idx < len(row):
            result[row[key_idx]] = row[col_idx].strip()
    return result


def load_glossary(lang):
    """Load glossary from data/{lang}/glossary.csv. Returns {english: translation}."""
    path = f'data/{lang}/glossary.csv'
    if not os.path.exists(path):
        return {}
    glossary = {}
    with open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            en = row.get('en', '').strip()
            tr = row.get(lang, '').strip()
            if en and tr:
                glossary[en] = tr
    if glossary:
        print(f"  Glossary: {len(glossary)} terms from {path}")
    return glossary


def load_custom_prompt(lang):
    """Load optional custom prompt from data/{lang}/prompt.txt."""
    path = f'data/{lang}/prompt.txt'
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return None


def build_system_prompt(lang, glossary, custom_prompt):
    lang_name = LANG_NAMES.get(lang, lang)

    parts = [
        f"You are a professional game translator. Translate English text to {lang_name}.",
        "",
        "Rules:",
        "- Preserve ALL markup tags exactly as they appear: {variables}, [img:...], [b], [/b], [i], [/i], [s:...], [/s], [color...], [/color], [n]",
        "- Keep the same tone and style as the original (casual, humorous, dramatic, etc.)",
        "- This is a cat breeding/genetics game — keep translations appropriate to the context",
        "- Translate naturally, using correct grammar and declensions for the target language",
        "- If a string is a single word or a proper name that should not be translated, return it as-is",
        "- Sometimes there is quoted text - it may need to be translated, depending on context. If in doubt, translate it.",
        "- Glossary terms (if any) should be used in the translation, but adapt their form as needed for grammar and style. Do NOT just insert them verbatim without adjusting cases, declensions, etc.",
    ]

    if glossary:
        parts.append("")
        parts.append("Glossary — use these translations, adapting grammatical forms as needed:")
        for en, tr in sorted(glossary.items()):
            parts.append(f"  \"{en}\" → \"{tr}\"")

    if custom_prompt:
        parts.append("")
        parts.append(custom_prompt)

    parts.extend([
        "",
        "You will receive a JSON array of strings to translate.",
        "Respond with a JSON array of translated strings, in the same order.",
        "Do NOT add any explanation, markdown formatting, or extra text — ONLY the JSON array.",
    ])

    return '\n'.join(parts)


def translate_batch(client, model, system_prompt, texts):
    """Translate a batch of texts using OpenAI API. Returns list of translations."""
    user_content = json.dumps(texts, ensure_ascii=False)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown code fence if present
        if raw.startswith('```'):
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)

        result = json.loads(raw)
        if isinstance(result, list) and len(result) == len(texts):
            return result
        print(f" length mismatch ({len(result)} vs {len(texts)}), 1-by-1...", end="", flush=True)
    except Exception as e:
        print(f" ERROR: {e}, 1-by-1...", end="", flush=True)

    # Fallback: translate one by one
    results = []
    for t in texts:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps([t], ensure_ascii=False)},
                ],
                temperature=0.3,
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith('```'):
                raw = re.sub(r'^```(?:json)?\s*', '', raw)
                raw = re.sub(r'\s*```$', '', raw)
            parsed = json.loads(raw)
            results.append(parsed[0] if isinstance(parsed, list) and parsed else t)
        except Exception:
            results.append(t)
    return results


def write_translated_csv(out_dir, filename, header, rows, key_idx, en_idx, target_col, translations):
    """Write CSV with translations in the target column, preserving 'en'."""
    out_header = list(header)
    target_idx = find_column(out_header, target_col)
    if target_idx is None:
        out_header.append(target_col)
        target_idx = len(out_header) - 1

    outpath = os.path.join(out_dir, filename)
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    output = io.StringIO()
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(out_header)
    for row in rows[1:]:
        new_row = list(row)
        while len(new_row) < len(out_header):
            new_row.append('')
        if key_idx < len(row) and row[key_idx] in translations:
            new_row[target_idx] = translations[row[key_idx]]
        writer.writerow(new_row)
    with open(outpath, 'w', encoding='utf-8-sig', newline='') as f:
        f.write(output.getvalue())


def translate_file(client, model, system_prompt, filename, progress, lang, target_col, workers):
    out_dir = translated_dir(lang)
    prog_file = progress_file(lang)

    extracted_path = os.path.join(EXTRACTED_DIR, filename)
    translated_path = os.path.join(out_dir, filename)

    header, rows = read_csv_file(extracted_path)
    if header is None:
        print(f"  Skip {filename} (empty)")
        return

    en_idx = find_column(header, 'en')
    if en_idx is None:
        print(f"  Skip {filename} (no 'en' column)")
        return

    key_idx = find_column(header, 'KEY')
    if key_idx is None:
        key_idx = 0

    # Current English text
    current_en = {}
    for row in rows[1:]:
        if key_idx < len(row) and en_idx < len(row):
            current_en[row[key_idx]] = row[en_idx].strip()

    # Previous English text and existing translations from translated file
    prev_en = {}
    existing_tr = {}
    if os.path.exists(translated_path):
        prev_en = build_column_map(translated_path, 'en')
        existing_tr = build_column_map(translated_path, target_col)

    # In-progress translations (for resume)
    if filename not in progress:
        progress[filename] = {}
    file_tr = progress[filename]

    # Decide what to keep vs re-translate
    translations = {}
    to_keys = []
    to_texts = []
    for key, en_text in current_en.items():
        if not en_text:
            continue
        if key in file_tr:
            translations[key] = file_tr[key]
        elif key in prev_en and prev_en[key] == en_text and key in existing_tr and existing_tr[key]:
            translations[key] = existing_tr[key]
        else:
            to_keys.append(key)
            to_texts.append(en_text)

    total = len(translations) + len(to_keys)
    if not to_keys:
        print(f"  {filename}: {total} strings [up to date]")
        write_translated_csv(out_dir, filename, header, rows, key_idx, en_idx, target_col, translations)
        return

    kept = len(translations)
    # Split into batches
    batches = []
    for i in range(0, len(to_keys), BATCH_SIZE):
        batches.append((to_keys[i:i+BATCH_SIZE], to_texts[i:i+BATCH_SIZE]))
    total_batches = len(batches)
    print(f"  {filename}: {len(to_keys)} to translate ({kept} kept), {total_batches} batches, {workers} workers")

    lock = threading.Lock()
    completed = [0]

    def do_batch(batch_idx, batch_keys, batch_texts):
        t0 = time.time()
        translated = translate_batch(client, model, system_prompt, batch_texts)
        elapsed = time.time() - t0
        with lock:
            for k, t in zip(batch_keys, translated):
                translations[k] = t
                file_tr[k] = t
            completed[0] += 1
            save_progress(progress, prog_file)
            done = len(translations)
            print(f"    [{completed[0]}/{total_batches}] +{len(batch_keys)} -> {done}/{total} ({elapsed:.1f}s)")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = []
        for idx, (bk, bt) in enumerate(batches):
            futures.append(pool.submit(do_batch, idx, bk, bt))
        for f in as_completed(futures):
            f.result()  # propagate exceptions

    write_translated_csv(out_dir, filename, header, rows, key_idx, en_idx, target_col, translations)
    print(f"  -> {filename} saved to {out_dir}/")



def main():
    p = argparse.ArgumentParser(description="Mewgenics Translator (OpenAI LLM)")
    p.add_argument('--lang', default=DEFAULT_LANG, help=f'Target language code (default: {DEFAULT_LANG})')
    p.add_argument('--column', default=DEFAULT_COLUMN, help=f'CSV column for translations (default: {DEFAULT_COLUMN})')
    p.add_argument('--model', default=DEFAULT_MODEL, help=f'OpenAI model (default: {DEFAULT_MODEL})')
    p.add_argument('--workers', type=int, default=DEFAULT_WORKERS, help=f'Parallel API requests (default: {DEFAULT_WORKERS})')
    p.add_argument('--file', help='Translate one file')
    p.add_argument('--fresh', action='store_true', help='Ignore existing progress file and start fresh')
    args = p.parse_args()

    lang = args.lang
    target_col = args.column

    if not os.path.isdir(EXTRACTED_DIR):
        print(f"ERROR: '{EXTRACTED_DIR}' not found. Run: python extract_text.py")
        sys.exit(1)

    client = OpenAI()
    glossary = load_glossary(lang)
    custom_prompt = load_custom_prompt(lang)
    system_prompt = build_system_prompt(lang, glossary, custom_prompt)

    prog_file = progress_file(lang)
    progress = {} if args.fresh else load_progress(prog_file)

    csv_files = sorted(os.path.relpath(p, EXTRACTED_DIR) for p in glob.glob(os.path.join(EXTRACTED_DIR, '**', '*.csv'), recursive=True))
    if args.file:
        if args.file not in csv_files:
            print(f"Not found: {args.file}\nAvailable: {', '.join(csv_files)}")
            sys.exit(1)
        csv_files = [args.file]

    out_dir = translated_dir(lang)
    print(f"Language: {lang} | Column: {target_col} | Model: {args.model} | Workers: {args.workers} | Files: {len(csv_files)} | Batch: {BATCH_SIZE} | Progress: {'fresh' if args.fresh else 'resume'}\n")

    t0 = time.time()
    for fn in csv_files:
        translate_file(client, args.model, system_prompt, fn, progress, lang, target_col, args.workers)

    print(f"\nDone in {time.time()-t0:.0f}s!")
    print(f"Translations in: {out_dir}/")


if __name__ == '__main__':
    main()
