from __future__ import annotations

import os
import sys
from pathlib import Path

GPAK_NAME = "resources.gpak"
GAME_DIR_NAME = "Mewgenics"


def _candidates_from_libraryfolders(steam_path: str) -> list[str]:
    """Parse libraryfolders.vdf and return candidate game directories."""
    candidates = [os.path.join(steam_path, "steamapps", "common", GAME_DIR_NAME)]

    vdf = os.path.join(steam_path, "config", "libraryfolders.vdf")
    if not os.path.exists(vdf):
        vdf = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    if os.path.exists(vdf):
        with open(vdf, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip().strip('"')
                if "path" in line.lower():
                    parts = line.split('"')
                    for p in parts:
                        p = p.strip()
                        if p and os.path.isdir(p):
                            candidates.append(os.path.join(p, "steamapps", "common", GAME_DIR_NAME))

    return candidates


def _find_steam_path_windows() -> str | None:
    """Find Steam install path on Windows via registry."""
    import winreg

    for reg_path in (
        r"SOFTWARE\WOW6432Node\Valve\Steam",
        r"SOFTWARE\Valve\Steam",
    ):
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
            steam_path = winreg.QueryValueEx(key, "InstallPath")[0]
            winreg.CloseKey(key)
            return steam_path
        except (OSError, FileNotFoundError):
            continue
    return None


def _find_steam_paths_linux() -> list[str]:
    """Find all Steam install paths on Linux (native, Flatpak, Snap)."""
    home = Path.home()
    seen: set[str] = set()
    result: list[str] = []
    for candidate in (
        home / ".local" / "share" / "Steam",
        home / ".steam" / "steam",
        home / ".steam" / "root",
        home / "snap" / "steam" / "common" / ".local" / "share" / "Steam",
        home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
    ):
        if candidate.is_dir() and (candidate / "steamapps").is_dir():
            resolved = str(candidate.resolve())
            if resolved not in seen:
                seen.add(resolved)
                result.append(resolved)
    return result


def find_game_path() -> Path | None:
    """Auto-detect Mewgenics install path via Steam registry + library folders."""
    if sys.platform == "win32":
        steam_path = _find_steam_path_windows()
        steam_paths = [steam_path] if steam_path else []
    elif sys.platform == "linux":
        steam_paths = _find_steam_paths_linux()
    else:
        return None

    candidates: list[str] = []
    for sp in steam_paths:
        candidates.extend(_candidates_from_libraryfolders(sp))

    for c in candidates:
        if os.path.isfile(os.path.join(c, GPAK_NAME)):
            return Path(c)

    return None
