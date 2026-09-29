from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_readme_describes_desktop_cloud_delivery():
    readme = (ROOT / "README.txt").read_text("utf-8")

    for phrase in (
        "macOS",
        "Windows",
        "SQLite",
        "Supabase",
        "断网",
        "系统凭据库",
        "YouTube",
        "Reddit",
        "TikTok",
    ):
        assert phrase in readme
    assert "service_role" not in readme


def test_packaging_bundles_sync_schema_and_delivery_files():
    spec = (ROOT / "packaging" / "kol-platform.spec").read_text("utf-8")

    assert "supabase" in spec
    assert "schema.sql" in spec
    assert "README.txt" in spec


def test_architecture_document_describes_offline_sync():
    architecture = (ROOT / "05_技术架构图.html").read_text("utf-8")

    for phrase in ("SQLite", "Supabase", "同步队列", "Keychain", "Credential Manager"):
        assert phrase in architecture
