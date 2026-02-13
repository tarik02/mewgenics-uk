#!/usr/bin/env python3
"""
Extract text files from Mewgenics resources.gpak.

Usage:
    python extract_text.py [--gpak <path>] [--output <dir>]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from game import find_original_gpak_path
from gpak import Gpak

def main() -> None:
    parser = argparse.ArgumentParser(description="Extract text files from Mewgenics resources.gpak")
    parser.add_argument("--gpak", type=Path, default=None, help="Path to resources.gpak (auto-detected if omitted)")
    parser.add_argument(
        "--output", "-o", type=Path, default=Path("data/extracted"), help="Output directory (default: data/extracted)",
    )
    args = parser.parse_args()

    gpak_path: Path | None = args.gpak
    if gpak_path is None:
        gpak_path = find_original_gpak_path()
        if gpak_path is None:
            print("Error: could not auto-detect game path. Provide --gpak path manually.")
            sys.exit(1)
        print(f"Auto-detected: {gpak_path}")

    if not gpak_path.is_file():
        print(f"Error: {gpak_path} not found")
        sys.exit(1)

    output_dir: Path = args.output

    with gpak_path.open("rb") as f:
        gpak = Gpak.open(f)

        text_entries = [e for e in gpak.entries if e.name.startswith('data/text/')]

        if not text_entries:
            print("No text files found in archive.")
            sys.exit(1)

        print(f"Found {len(text_entries)} text files in {gpak_path.name}")

        for entry in text_entries:
            data = gpak.read_entry(entry)
            out_path = output_dir / entry.name.replace("\\", "/")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(data)
            print(f"  {entry.name} ({entry.size:,} bytes)")

        print(f"\nExtracted {len(text_entries)} files to {output_dir}/")


if __name__ == "__main__":
    main()