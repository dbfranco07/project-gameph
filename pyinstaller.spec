# -*- mode: python ; coding: utf-8 -*-
# Builds the game client/server executable from main.py.
# Run on macOS to produce dist/ProjectGamePH.app, on Windows to produce dist/ProjectGamePH.exe
# (PyInstaller cannot cross-compile - build separately on each target OS).
import sys

from PyInstaller.utils.hooks import collect_submodules

datas = [
    ("config", "config"),
    ("client/assets", "client/assets"),
]

# Heroes and items are discovered at runtime with `pkgutil.iter_modules` (drop
# a file in the package and it exists — see server/heroes/__init__.py). Nothing
# imports them by name, so PyInstaller's static analysis never sees them and
# left them out of the bundle entirely: the packaged app started with an empty
# hero registry and died on `DEFAULT_HERO 'ranger' is not a known hero`.
# Collecting them as hidden imports bundles them and lets the frozen importer
# enumerate them.
hiddenimports = (collect_submodules("server.heroes")
                 + collect_submodules("server.items"))

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
