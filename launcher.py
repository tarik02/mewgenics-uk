#!/usr/bin/env python3
"""
Windows launcher for the Mewgenics Ukrainian translation installer.
Designed to be bundled into a single .exe via PyInstaller.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path


def get_base_path() -> Path:
    """Return the base path for bundled data files."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is not None:
        return Path(meipass)
    return Path(__file__).resolve().parent


def run() -> None:
    from install import main

    translations = get_base_path() / "data" / "uk" / "translated"
    main(translations_dir=translations)


if __name__ == "__main__":
    print("=" * 50)
    print("  Mewgenics — Український переклад")
    print("=" * 50)
    print()

    try:
        run()
    except SystemExit as e:
        if e.code and e.code != 0:
            print(f"\nProcess finished with code {e.code}")
    except Exception:
        print("\nUnexpected error:")
        traceback.print_exc()

    print()
    input("Press Enter to close... ")
