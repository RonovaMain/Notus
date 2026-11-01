# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec (one-dir build). Used by both CI workflows:  pyinstaller notus.spec --noconfirm --clean
import sys
from pathlib import Path

ROOT = Path(SPECPATH)

a = Analysis(
    [str(ROOT / "run_notus.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "assets"), "assets")],
    hiddenimports=[],
    excludes=["tkinter", "unittest", "pydoc", "test", "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets",
              "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtMultimedia", "PyQt6.Qt3DCore", "PyQt6.QtBluetooth"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Notus",
    console=False,
    icon=str(ROOT / "assets" / "icon.ico") if sys.platform == "win32" else None,
    upx=False,
    debug=False,
    strip=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Notus")
