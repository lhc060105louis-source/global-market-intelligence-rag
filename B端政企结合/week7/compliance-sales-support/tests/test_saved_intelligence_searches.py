from conftest import auth_headers


def test_saved_searches_require_identity(client):
    assert client.get("/api/intelligence/saved-searches").status_code == 401


def test_saved_search_lifecycle_is_organization_scoped(client, account):
    headers = auth_headers(account)
    payload = {
        "name": "德国电动公交监控",
        "keyword": "电动公交",
        "country": "DE",
        "source": "TED",
        "frequency": "daily",
    }

    created = client.post("/api/intelligence/saved-searches", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    item = created.json()
    assert item["frequency_label"] == "每天"
    assert item["enabled"] is True
    assert item["next_alert_at"]

    duplicate = client.post("/api/intelligence/saved-searches", json=payload, headers=headers)
    assert duplicate.status_code == 409

    listed = client.get("/api/intelligence/saved-searches", headers=headers)
    assert listed.status_code == 200
    assert any(row["id"] == item["id"] for row in listed.json())

    other = client.post("/api/auth/register", json={
        "email": "saved-search-other@example.com",
        "password": "correct-horse-456",
        "display_name": "另一组织用户",
        "organization_name": "另一测试组织",
    })
    assert other.status_code == 201, other.text
    other_headers = auth_headers(other.json())
    assert client.patch(
        f"/api/intelligence/saved-searches/{item['id']}",
        json={"enabled": False}, headers=other_headers,
    ).status_code == 404

    paused = client.patch(
        f"/api/intelligence/saved-searches/{item['id']}",
        json={"enabled": False, "frequency": "weekly"}, headers=headers,
    )
    assert paused.status_code == 200, paused.text
    assert paused.json()["enabled"] is False
    assert paused.json()["frequency_label"] == "每周"
    assert paused.json()["next_alert_at"] is None

    empty_filter = client.patch(
        f"/api/intelligence/saved-searches/{item['id']}",
        json={"keyword": "", "country": "", "source": ""}, headers=headers,
    )
    assert empty_filter.status_code == 422

    deleted = client.delete(f"/api/intelligence/saved-searches/{item['id']}", headers=headers)
    assert deleted.status_code == 204
    assert all(row["id"] != item["id"] for row in client.get(
        "/api/intelligence/saved-searches", headers=headers,
    ).json())


def test_saved_search_validation_and_keyword_filter_contract(client, account):
    headers = auth_headers(account)
    no_filter = client.post("/api/intelligence/saved-searches", json={
        "name": "无条件监控", "frequency": "daily",
    }, headers=headers)
    assert no_filter.status_code == 422

    invalid_frequency = client.post("/api/intelligence/saved-searches", json={
        "name": "错误频率监控", "keyword": "battery", "frequency": "hourly",
    }, headers=headers)
    assert invalid_frequency.status_code == 422

    response = client.get("/api/intelligence", params={"keyword": "battery", "limit": 10})
    assert response.status_code == 200
    assert response.json()["limit"] == 10
