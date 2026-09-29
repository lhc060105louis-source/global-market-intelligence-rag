from test_assessment import HIGH_VALUE_INPUTS, LOW_RISK_INPUTS


def test_desktop_frontend_does_not_automatically_read_legacy_browser_data():
    from pathlib import Path

    script = (Path(__file__).parents[1] / "app/static/app.js").read_text()
    assert "localStorage" not in script
    assert "/migrations/local-storage" not in script


def test_legacy_migration_normalizes_deduplicates_scores_and_restores_stage(client):
    data = {**HIGH_VALUE_INPUTS, **LOW_RISK_INPUTS}
    payload = [{
        "name": "Legacy EV", "handle": "@legacy", "platform": "YouTube",
        "market": "UK", "followers": "120,000", "data": data, "stage": 4,
    }]

    first = client.post("/migrations/local-storage", json=payload)
    second = client.post("/migrations/local-storage", json=payload)

    assert first.status_code == 200
    assert first.json() == {"created": 1, "updated": 0, "failed": 0}
    assert second.json() == {"created": 0, "updated": 1, "failed": 0}
    kols = client.get("/kols").json()
    assert len(kols) == 1
    detail = client.get(f"/kols/{kols[0]['id']}").json()
    assert detail["country"] == "GB"
    assert detail["followers"] == 120000
    assert detail["workflow_stage"] == 4
    assert detail["commercial_inputs"] == HIGH_VALUE_INPUTS
    assert detail["risk_inputs"] == LOW_RISK_INPUTS
    assert detail["flags"] == []
    assert detail["score_summary"]["commercial_score"] == 88


def test_legacy_migration_counts_bad_rows_without_deleting_other_rows(client):
    response = client.post("/migrations/local-storage", json=[
        {"name": "", "platform": "YouTube", "market": "UK", "data": {}, "stage": 0},
        {"name": "Bad stage", "handle": "@bad", "platform": "TikTok", "market": "DE", "data": {}, "stage": 9},
    ])
    assert response.status_code == 200
    assert response.json() == {"created": 0, "updated": 0, "failed": 2}
    assert client.get("/kols").json() == []


def test_exact_legacy_shape_without_account_identity_is_stably_deduplicated(client):
    payload = [{
        "name": "Legacy EV", "platform": "YouTube", "market": "UK",
        "followers": "1,200", "data": {}, "stage": 2,
    }]
    assert client.post("/migrations/local-storage", json=payload).json() == {
        "created": 1, "updated": 0, "failed": 0,
    }
    assert client.post("/migrations/local-storage", json=payload).json() == {
        "created": 0, "updated": 1, "failed": 0,
    }
    items = client.get("/kols").json()
    assert len(items) == 1
    assert items[0]["platform_account_id"].startswith("legacy:")
