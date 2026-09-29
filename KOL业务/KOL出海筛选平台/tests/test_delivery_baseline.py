import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient


def test_delivery_package_is_canonical_app_root(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    assert (root / "01_KOL合作管理平台.html").exists()
    assert (root / "app" / "static" / "index.html").exists()
    assert importlib.util.find_spec("app.main") is not None

    from app.main import create_app

    client = TestClient(
        create_app(
            f"sqlite:///{tmp_path / 'baseline.db'}",
            session_token="test-token",
        )
    )
    response = client.get("/")

    assert response.status_code == 200
    assert "KOL 合作管理平台" in response.text
    assert "v3.0" in response.text


def test_desktop_bundle_keeps_numbered_delivery_artifacts():
    root = Path(__file__).resolve().parents[1]
    spec = (root / "packaging" / "kol-platform.spec").read_text("utf-8")

    for filename in (
        "01_KOL合作管理平台.html",
        "02_商业价值评分模型.html",
        "03_风险评分模型.html",
        "04_核心逻辑代码（含注释）.js",
        "05_技术架构图.html",
        "06_BYD_Xpeng_KOL评估数据.xlsx",
        "07_评估模型说明文稿.docx",
        "README.txt",
    ):
        assert filename in spec
