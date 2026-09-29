from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_desktop_builds_use_english_application_names():
    macos = (ROOT / "packaging" / "macos" / "build.sh").read_text("utf-8")
    windows = (ROOT / "packaging" / "windows" / "build.ps1").read_text("utf-8")

    assert 'APP_NAME="CreatorPartnershipPlatform"' in macos
    assert '$AppName = "CreatorPartnershipPlatform"' in windows


def test_packaging_bundles_sync_schema_and_delivery_files():
    spec = (ROOT / "packaging" / "kol-platform.spec").read_text("utf-8")

    assert "supabase" in spec
    assert "schema.sql" in spec
    assert "README.txt" in spec


def test_windows_installer_uses_english_labels_and_preserves_user_data():
    installer = (ROOT / "packaging" / "windows" / "installer.iss").read_text("utf-8")
    assert 'AppName "Creator Partnership Platform"' in installer
    assert "Create a desktop shortcut" in installer
    assert "CreatorPartnershipPlatform is preserved" in installer
