def test_v3_navigation_and_desktop_features_are_present(client):
    html = client.get("/").text

    for label in (
        "数据大屏",
        "KOL 列表",
        "KOL 对比",
        "候选名单",
        "合作管理",
        "合同管理",
        "效果复盘",
        "系统设置",
    ):
        assert label in html
    assert "v3.0" in html
    assert "localStorage" not in html
    assert "localStorage" not in client.get("/static/app.js").text


def test_frontend_declares_sync_states_and_real_data_modules(client):
    html = client.get("/").text
    assert 'id="sync-status"' in html
    for script in ("shortlists.js", "contracts.js", "reviews.js", "sync.js"):
        assert f'/static/{script}' in html

    sync_script = client.get("/static/sync.js").text
    for state in ("offline", "syncing", "synced", "conflict", "failed"):
        assert state in sync_script


def test_shortlists_can_be_listed(client):
    created = client.post(
        "/shortlists",
        json={"name": "德国上市候选", "target_country": "DE"},
    )
    assert created.status_code == 201

    response = client.get("/shortlists")

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["德国上市候选"]
