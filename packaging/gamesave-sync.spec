# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec, shared by the Linux/Windows/macOS builds.

Build with:

    pyinstaller packaging/gamesave-sync.spec

Produces a one-folder bundle in dist/. The AppImage script wraps that folder
into an AppDir; the Windows and macOS jobs zip it as-is.
"""

import re
import sys
from pathlib import Path

# SPECPATH is injected by PyInstaller and points at this file's directory.
ROOT = Path(SPECPATH).parent
ICON_DIR = ROOT / "assets"

# Read the version from the package rather than repeating it here, so a bump in
# one place cannot silently ship a stale CFBundleVersion. Parsed rather than
# imported: importing would pull PySide6 into the spec's own interpreter.
VERSION = re.search(
    r'VERSION = "([^"]+)"', (ROOT / "gamesync" / "__init__.py").read_text()
).group(1)

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"

if IS_WINDOWS:
    icon = str(ICON_DIR / "icon.ico")
elif IS_MACOS:
    icon = str(ICON_DIR / "icon.icns")
    if not Path(icon).exists():
        icon = None
else:
    icon = str(ICON_DIR / "icon.png")


a = Analysis(
    # Not gamesync/__main__.py: PyInstaller runs the script without a parent
    # package, which breaks its relative imports. See packaging/entrypoint.py.
    [str(ROOT / "packaging" / "entrypoint.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ICON_DIR / "icon.png"), "assets")],
    hiddenimports=[
        # keyring resolves its backend at runtime, so PyInstaller cannot see
        # these by following imports.
        "keyring.backends",
        "keyring.backends.SecretService",
        "keyring.backends.chainer",
        "keyring.backends.fail",
        "keyring.backends.libsecret",
        "keyring.backends.Windows",
        "keyring.backends.macOS",
        "jeepney",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Qt ships a lot we never touch; dropping these keeps the bundle far
    # smaller without affecting the widgets we actually use.
    excludes=[
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtQuick",
        "PySide6.QtQml",
        "PySide6.Qt3DCore",
        "PySide6.QtMultimedia",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtBluetooth",
        "PySide6.QtPositioning",
        "PySide6.QtSql",
        "PySide6.QtTest",
        "PySide6.QtDesigner",
        "tkinter",
        "matplotlib",
        "numpy",
        "PIL",
        "pytest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GameSave Sync" if (IS_WINDOWS or IS_MACOS) else "gamesave-sync",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI app: no terminal window on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="GameSave Sync" if (IS_WINDOWS or IS_MACOS) else "gamesave-sync",
)

if IS_MACOS:
    app = BUNDLE(
        coll,
        name="GameSave Sync.app",
        icon=icon,
        bundle_identifier="io.github.kyleisdork.gamesavesync",
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.utilities",
            "LSMinimumSystemVersion": "11.0",
        },
    )
