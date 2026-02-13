#!/usr/bin/env python3
"""
Back up and re-package the game gpak with updated Ukrainian translations.

Usage:
    python patch_gpak.py [--gpak <path>] [--translations <dir>]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from game import find_gpak_path
from gpak import Gpak

DEFAULT_TRANSLATIONS = Path("data/uk/translated")


def collect_replacements(translations_dir: Path) -> dict[str, Path]:
    """Build a mapping of gpak entry names to translated file paths."""
    replacements: dict[str, Path] = {}
    for file in translations_dir.rglob("*"):
        if not file.is_file():
            continue
        rel = str(file.relative_to(translations_dir)).replace("\\", "/")
        replacements[rel] = file
    return replacements


def main(
    *,
    gpak_path: Path | None = None,
    translations_dir: Path | None = None,
    no_backup: bool = False,
) -> None:
    if gpak_path is None:
        gpak_path = find_gpak_path()
        if gpak_path is None:
            print("Error: could not auto-detect game path. Provide --gpak path manually.")
            sys.exit(1)
        print(f"Auto-detected: {gpak_path}")

    if not gpak_path.is_file():
        print(f"Error: {gpak_path} not found")
        sys.exit(1)

    if translations_dir is None:
        translations_dir = DEFAULT_TRANSLATIONS
    if not translations_dir.is_dir():
        print(f"Error: translations directory not found: {translations_dir}")
        sys.exit(1)

    replacements = collect_replacements(translations_dir)
    if not replacements:
        print("No translated files found.")
        sys.exit(1)

    print(f"Found {len(replacements)} translated file(s)")

    # Backup
    backup_path = gpak_path.with_suffix(".gpak.bak")
    if not no_backup:
        if backup_path.exists():
            print(f"Backup already exists: {backup_path}")
        else:
            print(f"Backing up to {backup_path} ...")
            shutil.copy2(gpak_path, backup_path)
            print("Backup created.")

    # Use backup as source if it exists (preserves original data across re-patches)
    src_path = backup_path if backup_path.exists() else gpak_path
    tmp_path = gpak_path.with_suffix(".gpak.tmp")
    print(f"Patching gpak (source: {src_path.name}) ...")

    try:
        with src_path.open("rb") as src, tmp_path.open("wb") as dst:
            gpak = Gpak.open(src)
            existing = {e.name for e in gpak.entries}
            gpak.patch(dst, replacements)

        replaced = [n for n in replacements if n in existing]
        added = [n for n in replacements if n not in existing]

        print(f"  Replaced {len(replaced)} existing entry/entries")
        if added:
            print(f"  Added {len(added)} new entry/entries:")
            for name in sorted(added):
                print(f"    + {name}")

        # Swap temp file into place
        tmp_path.replace(gpak_path)
        print(f"Done. Patched gpak written to {gpak_path}")

    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def cli() -> None:
    parser = argparse.ArgumentParser(
        description="Back up and re-package resources.gpak with Ukrainian translations",
    )
    parser.add_argument(
        "--gpak", type=Path, default=None,
        help="Path to resources.gpak (auto-detected if omitted)",
    )
    parser.add_argument(
        "--translations", "-t", type=Path, default=None,
        help=f"Directory with translated files (default: {DEFAULT_TRANSLATIONS})",
    )
    parser.add_argument(
        "--no-backup", action="store_true",
        help="Skip creating a backup of the original gpak",
    )
    args = parser.parse_args()

    main(
        gpak_path=args.gpak,
        translations_dir=args.translations,
        no_backup=args.no_backup,
    )


if __name__ == "__main__":
    cli()
