from pathlib import Path


PACKAGING = Path("packaging")


def test_pyinstaller_spec_bundles_runtime_and_static_assets():
    text = (PACKAGING / "kol-platform.spec").read_text("utf-8")
    for marker in (
        "app/static", "app.launcher", "yt_dlp", "fastapi", "uvicorn",
        "keyring.backends", "pystray", "PIL", "collect_submodules",
    ):
        assert marker in text
    assert "database" not in text.lower()
    assert "sample" not in text.lower()


def test_macos_build_supports_smoke_sign_notarize_and_dmg():
    build = (PACKAGING / "macos/build.sh").read_text("utf-8")
    entitlements = (PACKAGING / "macos/entitlements.plist").read_text("utf-8")
    for marker in ("--smoke", "venv", "PyInstaller", "APPLE_SIGN_IDENTITY", "codesign", "notarytool", "hdiutil", "CreatorPartnershipPlatform.dmg"):
        assert marker in build
    assert "mktemp -d /private/tmp/kol-macos-build." in build
    assert '"$VENV/bin/python" -m PyInstaller' in build
    assert "Python 3.10+" in build
    assert 'PYTHON="${PYTHON:-python3}"' in build
    assert "com.apple.security.network.server" in entitlements


def test_windows_build_and_installer_are_per_user_and_preserve_data():
    build = (PACKAGING / "windows/build.ps1").read_text("utf-8")
    installer = (PACKAGING / "windows/installer.iss").read_text("utf-8")
    for marker in ("[switch]$Smoke", "venv", "PyInstaller", "ISCC", "kol-platform.spec"):
        assert marker in build
    assert "& $Python -m PyInstaller" in build
    assert "Python 3.10+" in build
    for marker in ("PrivilegesRequired=lowest", "{localappdata}", "{userprograms}", "{userdesktop}", "UninstallDelete"):
        assert marker in installer
    assert "OutputBaseFilename=CreatorPartnershipPlatform-Setup" in installer
    assert "{localappdata}\\Capgemini\\CreatorPartnershipPlatform is preserved" in installer


def test_native_build_scripts_use_english_release_artifact_names():
    macos = (PACKAGING / "macos/build.sh").read_text("utf-8")
    windows = (PACKAGING / "windows/build.ps1").read_text("utf-8")
    assert 'APP_NAME="CreatorPartnershipPlatform"' in macos
    assert '$AppName = "CreatorPartnershipPlatform"' in windows
    assert '"$ROOT/dist/macos"' in macos
    assert '"dist/windows"' in windows
