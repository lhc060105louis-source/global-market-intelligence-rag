def _create_kol(client):
    response = client.post(
        "/kols",
        json={
            "name": "EV Review",
            "platform": "youtube",
            "handle": "@commercial",
            "country": "DE",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_contract_and_review_are_persisted(client):
    kol_id = _create_kol(client)

    contract = client.post(
        f"/kols/{kol_id}/contracts",
        json={
            "title": "Launch campaign",
            "status": "draft",
            "currency": "EUR",
            "amount": 5000,
        },
    )
    review = client.post(
        f"/kols/{kol_id}/reviews",
        json={
            "campaign": "Launch campaign",
            "impressions": 120000,
            "engagements": 8400,
            "conversions": 140,
        },
    )

    assert contract.status_code == 201
    assert contract.json()["title"] == "Launch campaign"
    assert review.status_code == 201
    assert review.json()["engagements"] == 8400
    assert len(client.get(f"/kols/{kol_id}/contracts").json()) == 1
    assert len(client.get(f"/kols/{kol_id}/reviews").json()) == 1
