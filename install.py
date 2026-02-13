#!/usr/bin/env python3
"""
Install Ukrainian translations into the Mewgenics game directory.

Copies translated files next to the game executable, where the game
loads them as loose file overrides for resources.gpak content.

Usage:
    python install.py [--game-dir <path>] [--translations <dir>]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from game import find_game_path

DEFAULT_TRANSLATIONS = Path("data/uk/translated")


def main(
    *,
    game_dir: Path | None = None,
    translations_dir: Path | None = None,
) -> None:
    if game_dir is None:
        game_dir = find_game_path()
        if game_dir is None:
            print("Error: could not auto-detect game path. Provide --game-dir path manually.")
            sys.exit(1)
        print(f"Auto-detected: {game_dir}")

    if not game_dir.is_dir():
        print(f"Error: {game_dir} is not a directory")
        sys.exit(1)

    if translations_dir is None:
        translations_dir = DEFAULT_TRANSLATIONS
    if not translations_dir.is_dir():
        print(f"Error: translations directory not found: {translations_dir}")
        sys.exit(1)

    files = [f for f in translations_dir.rglob("*") if f.is_file()]
    if not files:
        print("No translated files found.")
        sys.exit(1)

    print(f"Found {len(files)} translated file(s)")
    print(f"Installing to {game_dir} ...")

    for file in files:
        rel = file.relative_to(translations_dir)
        dest = game_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, dest)
        print(f"  {rel}")

    print(f"\nDone. Copied {len(files)} file(s) to {game_dir}")


def cli() -> None:
    parser = argparse.ArgumentParser(
        description="Install Ukrainian translations into the Mewgenics game directory",
    )
    parser.add_argument(
        "--game-dir", type=Path, default=None,
        help="Path to the Mewgenics game directory (auto-detected if omitted)",
    )
    parser.add_argument(
        "--translations", "-t", type=Path, default=None,
        help=f"Directory with translated files (default: {DEFAULT_TRANSLATIONS})",
    )
    args = parser.parse_args()

    main(
        game_dir=args.game_dir,
        translations_dir=args.translations,
    )


if __name__ == "__main__":
    cli()
