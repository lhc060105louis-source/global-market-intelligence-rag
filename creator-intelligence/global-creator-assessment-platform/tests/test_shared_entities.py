from uuid import UUID


def _create_kol(client):
    response = client.post(
        "/kols",
        json={
            "name": "EV Review",
            "platform": "youtube",
            "handle": "@ev",
            "country": "GB",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_kol_exposes_stable_sync_metadata(client):
    created = _create_kol(client)

    assert str(UUID(created["sync_id"])) == created["sync_id"]
    assert created["version"] == 1
    assert created["deleted_at"] is None
    assert created["updated_by_device"]


def test_workflow_change_appends_history(client):
    kol = _create_kol(client)

    response = client.put(f"/kols/{kol['id']}/workflow", json={"stage": 2})

    assert response.status_code == 200
    history = client.get(f"/kols/{kol['id']}/workflow/history")
    assert history.status_code == 200
    assert [item["stage"] for item in history.json()] == [0, 2]
