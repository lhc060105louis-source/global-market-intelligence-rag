# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPEC).resolve().parents[1]
IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"
APP_NAME = "KOL合作管理平台"

# app.launcher:main is the desktop entry; executing launcher.py calls main().
entry = ROOT / "app" / "launcher.py"
datas = [(str(ROOT / "app/static"), "app/static")]
datas += [
    (str(ROOT / "supabase/schema.sql"), "supabase"),
    (str(ROOT / "supabase/rls.sql"), "supabase"),
]
DELIVERY_FILES = [
    "01_KOL合作管理平台.html",
    "02_商业价值评分模型.html",
    "03_风险评分模型.html",
    "04_核心逻辑代码（含注释）.js",
    "05_技术架构图.html",
    "06_BYD_Xpeng_KOL评估数据.xlsx",
    "07_评估模型说明文稿.docx",
    "README.txt",
]
datas += [(str(ROOT / filename), ".") for filename in DELIVERY_FILES]
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
