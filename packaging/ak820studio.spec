# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for AK820 Studio (onedir, windowed).
# Run from the project root via packaging\build.bat, which passes
# --distpath dist-app --workpath build-app.

import os

from PyInstaller.utils.hooks import collect_data_files

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
ICON = os.path.join(SPECPATH, "app.ico")
if not os.path.isfile(ICON):
    ICON = None


def _collect(package):
    """Collect data files for a package if it is importable; skip otherwise."""
    try:
        return collect_data_files(package)
    except Exception:
        return []


datas = [
    (os.path.join(ROOT, "ui", "dist"), "ui/dist"),
]
datas += _collect("_sounddevice_data")
datas += _collect("webview")

hiddenimports = [
    # pywebview Windows backend (WinForms + Edge WebView2 via pythonnet)
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    "clr_loader",
    "pythonnet",
    "clr",
    # HID access
    "hid",
    # System tray
    "pystray._win32",
    # Audio
    "soundcard.mediafoundation",
    "sounddevice",
    "_sounddevice",
]

excludes = [
    "PyQt6",
    "PyQt5",
    "tkinter",
    "matplotlib",
    "GPUtil",
    "pynput",
]

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AK820Studio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AK820Studio",
)
