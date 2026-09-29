def _seed(client):
    response = client.post("/imports", files={"file": (
        "seed.csv", b"platform,country,handle,name\nYouTube,UK,@flow,Flow\n", "text/csv"
    )})
    assert response.status_code == 201
    return client.get("/kols").json()[0]["id"]


def test_workflow_stage_persists(client):
    kol_id = _seed(client)
    response = client.put(f"/kols/{kol_id}/workflow", json={"stage": 3})
    assert response.status_code == 200
    assert response.json()["stage"] == 3
    assert client.get(f"/kols/{kol_id}").json()["workflow_stage"] == 3


def test_workflow_rejects_stage_seven(client):
    kol_id = _seed(client)
    assert client.put(f"/kols/{kol_id}/workflow", json={"stage": 7}).status_code == 422
