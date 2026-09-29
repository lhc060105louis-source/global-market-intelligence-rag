from app.paths import AppPaths


def test_paths_honor_override(tmp_path, monkeypatch):
    monkeypatch.setenv("KOL_PLATFORM_DATA_DIR", str(tmp_path))
    paths = AppPaths.from_environment()
    assert paths.database_path == tmp_path / "kol_platform.db"
    assert paths.log_dir == tmp_path / "logs"
