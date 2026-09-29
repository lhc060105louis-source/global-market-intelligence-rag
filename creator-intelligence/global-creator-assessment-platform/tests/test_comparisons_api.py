from test_importer import upload_csv


def _seed(client, count=5):
    rows = ["platform,country,handle,name,followers,audience_fit,historical_controversy"]
    rows.extend(
        f"YouTube,GB,@kol{i},KOL {i},{1000 + i},80,10" for i in range(count)
    )
    upload_csv(client, "\n".join(rows) + "\n")
    return client.get("/kols").json()


def test_comparison_rejects_five_kols(client):
    kols = _seed(client)
    response = client.post("/comparisons", json={"kol_ids": [kol["id"] for kol in kols[:5]]})
    assert response.status_code == 422


def test_comparison_returns_dimension_evidence(client):
    kol = _seed(client, 1)[0]
    response = client.post("/comparisons", json={"kol_ids": [kol["id"]]})

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert "score_records" in item
    assert item["score_records"]
    assert {"dimension", "final_score", "evidence", "source"}.issubset(item["score_records"][0])
