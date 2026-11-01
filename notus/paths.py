"""Filesystem layout: where the app, its backend binaries and user data live."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_FOLDER = "Notus"
EXE_SUFFIX = ".exe" if os.name == "nt" else ""


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Folder that contains Notus(.exe) (or the repo root when run from source)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    """Folder with bundled read-only resources (PyInstaller's _internal)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", app_dir()))
    return Path(__file__).resolve().parent.parent


def asset(name: str) -> Path:
    return resource_dir() / "assets" / name


def is_portable() -> bool:
    """Portable mode: a file called portable.flag lies next to the executable."""
    return (app_dir() / "portable.flag").exists()


def data_dir() -> Path:
    override = os.environ.get("NOTUS_DATA_DIR")
    if override:
        base = Path(override)
    elif is_portable():
        base = app_dir() / "data"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_FOLDER
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "notus"
    base.mkdir(parents=True, exist_ok=True)
    return base


def chats_dir() -> Path:
    d = data_dir() / "chats"
    d.mkdir(parents=True, exist_ok=True)
    return d


def backend_candidates(custom: str = "") -> list[Path]:
    found: list[Path] = []
    if custom:
        found.append(Path(custom))
    env = os.environ.get("NOTUS_BACKEND")
    if env:
        found.append(Path(env))
    found.append(app_dir() / "backend")
    found.append(app_dir() / "llama.cpp" / "build" / "bin")
    found.append(app_dir() / "llama.cpp" / "build" / "bin" / "Release")
    return found


def find_backend_exe(name: str = "llama-server", custom: str = "") -> Path | None:
    for d in backend_candidates(custom):
        p = d / (name + EXE_SUFFIX)
        if p.is_file():
            return p
    w = shutil.which(name)
    return Path(w) if w else None
