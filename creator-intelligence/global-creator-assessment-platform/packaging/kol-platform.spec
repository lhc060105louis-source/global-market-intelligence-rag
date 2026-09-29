# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPEC).resolve().parents[1]
IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"
APP_NAME = "CreatorPartnershipPlatform"

# app.launcher:main is the desktop entry; executing launcher.py calls main().
entry = ROOT / "app" / "launcher.py"
datas = [(str(ROOT / "app/static"), "app/static")]
datas += [
    (str(ROOT / "supabase/schema.sql"), "supabase"),
    (str(ROOT / "supabase/rls.sql"), "supabase"),
]
datas += collect_data_files("fastapi")
datas += collect_data_files("uvicorn")
datas += collect_data_files("yt_dlp")
datas += collect_data_files("keyring")
hiddenimports = (
    ["app.launcher", "fastapi", "uvicorn", "yt_dlp", "pystray", "PIL"]
    + collect_submodules("uvicorn")
    + collect_submodules("yt_dlp")
    + collect_submodules("keyring.backends")
    + collect_submodules("pystray")
    + collect_submodules("PIL")
)
icon_candidate = ROOT / "packaging" / ("macos/app.icns" if IS_MAC else "windows/app.ico")
icon = str(icon_candidate) if icon_candidate.exists() else None

a = Analysis(
    [str(entry)],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "tests"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name=APP_NAME,
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, icon=icon,
)
collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=APP_NAME)

if IS_MAC:
    app = BUNDLE(
        collection,
        name=f"{APP_NAME}.app",
        icon=icon,
        bundle_identifier="com.capgemini.kol-platform",
        info_plist={"NSHighResolutionCapable": True, "LSUIElement": True},
    )
