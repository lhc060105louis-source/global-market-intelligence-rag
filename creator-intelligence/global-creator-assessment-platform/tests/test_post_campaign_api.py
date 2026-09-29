def test_post_campaign_overview(client):
    response = client.get("/post-campaign/overview")
    assert response.status_code == 200
    data = response.json()
    assert data["campaign"] == "BYD Germany New Vehicle Launch Reach Campaign"
    assert data["metrics"]["impressions"] > 0
    assert data["ranking"]


def test_post_campaign_kol_and_sentiment(client):
    kol = client.get("/post-campaign/kols/@AutoBildDE")
    assert kol.status_code == 200
    assert kol.json()["handle"] == "@AutoBildDE"

    sentiment = client.get("/post-campaign/sentiment")
    assert sentiment.status_code == 200
    assert sentiment.json()["positive"] == 76


def test_campaign_decision(client):
    response = client.post(
        "/post-campaign/review/decision",
        json={"decision": "Recommend Continuing the Partnership", "notes": "Retain long-form video partnerships."},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "Confirmed"

    saved = client.get("/post-campaign/review").json()
    assert saved["decision"] == "Recommend Continuing the Partnership"


def test_crisis_flow(client):
    crises = client.get("/post-campaign/crises")
    assert crises.status_code == 200
    code = crises.json()["items"][0]["crisis_code"]

    detail = client.get(f"/post-campaign/crises/{code}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "In Progress"

    action = client.post(f"/post-campaign/crises/{code}/actions/legal-review")
    assert action.status_code == 200
    assert action.json()["verified"] is True

    decision = client.post(
        f"/post-campaign/crises/{code}/decision",
        json={"decision": "Limit Exposure"},
    )
    assert decision.status_code == 200
    assert decision.json()["decision"] == "Limit Exposure"

    closed = client.post(f"/post-campaign/crises/{code}/close")
    assert closed.status_code == 200
    assert closed.json()["status"] == "Closed"
