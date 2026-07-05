# -*- mode: python ; coding: utf-8 -*-
# Builds the game client/server executable from main.py.
# Run on macOS to produce dist/ProjectGamePH.app, on Windows to produce dist/ProjectGamePH.exe
# (PyInstaller cannot cross-compile - build separately on each target OS).
import sys

datas = [
    ("config", "config"),
    ("client/assets", "client/assets"),
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

if sys.platform == "darwin":
    # .app bundles are inherently a directory, so build onedir and let
    # BUNDLE assemble the .app around it.
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="ProjectGamePH",
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
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="ProjectGamePH",
    )
    app = BUNDLE(
        coll,
        name="ProjectGamePH.app",
        icon=None,
        bundle_identifier=None,
    )
else:
    # Single-file .exe on Windows - friends just download and double-click.
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="ProjectGamePH",
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
    )
