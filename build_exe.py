#!/usr/bin/env python3
"""Build a single-file Windows executable with embedded translation data."""

from __future__ import annotations

import os

import PyInstaller.__main__

sep = ";" if os.name == "nt" else ":"

PyInstaller.__main__.run(
    [
        "launcher.py",
        "--onefile",
        "--name=mewgenics-uk",
        f"--add-data=data/uk/translated{sep}data/uk/translated",
        "--console",
        "--clean",
    ]
)
