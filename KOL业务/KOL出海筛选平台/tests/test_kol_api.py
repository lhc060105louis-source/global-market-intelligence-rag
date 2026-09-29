def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_empty_kol_list(client):
    response = client.get("/kols")

    assert response.status_code == 200
    assert response.json() == []


def test_create_and_update_kol(client):
    payload = {
        "name": "EV Review UK",
        "platform": "YouTube",
        "handle": "@evreviewuk",
        "profile_url": "https://youtube.com/@evreviewuk",
        "country": "GB",
        "language": "en",
        "content_categories": "EV, car review",
        "followers": 120000,
        "average_engagement_rate": 3.8,
        "audience_country_ratio": 72,
    }

    created = client.post("/kols", json=payload)
    assert created.status_code == 201
    kol_id = created.json()["id"]
    assert created.json()["name"] == "EV Review UK"

    updated = client.put(f"/kols/{kol_id}", json={**payload, "followers": 125000})
    assert updated.status_code == 200
    assert updated.json()["followers"] == 125000
    assert client.get(f"/kols/{kol_id}").json()["followers"] == 125000


def test_create_kol_rejects_duplicate_platform_handle(client):
    payload = {"platform": "YouTube", "handle": "@same", "country": "GB"}
    assert client.post("/kols", json=payload).status_code == 201
    duplicate = client.post("/kols", json=payload)
    assert duplicate.status_code == 409


def test_list_kols_includes_persisted_workflow_stage(client):
    created = client.post("/kols", json={"platform": "YouTube", "handle": "@stage", "country": "GB"}).json()
    assert client.put(f"/kols/{created['id']}/workflow", json={"stage": 4}).status_code == 200
    listed = client.get("/kols?keyword=@stage").json()[0]
    assert listed["workflow_stage"] == 4


def test_partial_edit_preserves_imported_platform_account_identity(client):
    payload = {"platform": "YouTube", "platform_account_id": "UC-stable", "handle": "@stable", "country": "GB", "name": "Before"}
    created = client.post("/kols", json=payload).json()
    updated = client.put(f"/kols/{created['id']}", json={"name": "After", "followers": 42})
    assert updated.status_code == 200
    assert updated.json()["platform"] == "YouTube"
    assert updated.json()["platform_account_id"] == "UC-stable"
    assert updated.json()["handle"] == "@stable"


def test_write_persists_raw_assessment_and_normalizes_blank_identity(client):
    created = client.post("/kols", json={"platform": "YouTube", "country": "GB", "handle": "  ", "platform_account_id": "UC-one", "commercial_inputs": {"geo": 80}, "risk_inputs": {"incident": "none"}})
    assert created.status_code == 201
    detail = created.json()
    assert detail["handle"] is None
    assert detail["commercial_inputs"] == {"geo": 80}
    assert detail["risk_inputs"] == {"incident": "none"}
    second = client.post("/kols", json={"platform": "YouTube", "country": "GB", "handle": "", "platform_account_id": "UC-two"})
    assert second.status_code == 201
    edited = client.put(f"/kols/{detail['id']}", json={"name": "Edited", "handle": ""})
    assert edited.status_code == 200
    assert edited.json()["handle"] is None
    assert edited.json()["platform_account_id"] == "UC-one"


def test_lookup_youtube_returns_modal_preview(client, monkeypatch):
    monkeypatch.setattr("app.api.kols.fetch_youtube_channel_metadata", lambda url: {"id": "UC-preview", "channel": "Preview EV", "channel_url": url, "channel_follower_count": 3210, "description": "EV reviews"})
    response = client.post("/kols/lookup-youtube", json={"profile_url": "https://youtube.com/@preview"})
    assert response.status_code == 200
    assert response.json()["platform_account_id"] == "UC-preview"
    assert response.json()["followers"] == 3210


def seed_kols(client):
    csv_data = (
        "platform,country,handle,name,followers,audience_fit,content_relevance,"
        "interaction_quality,voc_value,commercial_efficiency,brand_fit,"
        "execution_capability,historical_controversy,ad_disclosure,"
        "competitor_conflict,fake_traffic,data_privacy,sensitive_audience,"
        "sustainability_claims,execution_risk\n"
        "YouTube,UK,@alex,Alex EV,120000,80,80,80,80,80,80,80,"
        "10,10,10,10,10,10,10,10\n"
        "TikTok,DE,@mobil,Mobil DE,50000,60,60,60,60,60,60,60,"
        "50,50,50,50,50,50,50,50\n"
    )
    response = client.post(
        "/imports",
        files={"file": ("seed.csv", csv_data.encode(), "text/csv")},
    )
    assert response.status_code == 201


def test_search_filters_country_platform_and_scores(client):
    seed_kols(client)

    assert len(client.get("/kols?country=UK").json()) == 1
    assert len(client.get("/kols?platform=YouTube").json()) == 1
    assert len(client.get("/kols?min_commercial_score=70").json()) == 1
    assert len(client.get("/kols?max_risk_score=20").json()) == 1


def test_search_filters_inclusive_minimum_commercial_score_and_excludes_unscored(client):
    seed_kols(client)
    unscored = client.post(
        "/kols",
        json={"platform": "YouTube", "handle": "@unscored", "country": "GB"},
    )
    assert unscored.status_code == 201

    boundary = client.get("/kols", params={"min_commercial_score": 80})
    lower_boundary = client.get("/kols", params={"min_commercial_score": 60})
    combined = client.get(
        "/kols",
        params={
            "country": "GB",
            "platform": "YouTube",
            "min_followers": 100000,
            "min_commercial_score": 80,
        },
    )

    assert boundary.status_code == 200
    assert [kol["handle"] for kol in boundary.json()] == ["@alex"]
    assert lower_boundary.status_code == 200
    assert [kol["handle"] for kol in lower_boundary.json()] == ["@alex", "@mobil"]
    assert combined.status_code == 200
    assert [kol["handle"] for kol in combined.json()] == ["@alex"]
    assert all(
        kol["handle"] != "@unscored"
        for kol in boundary.json() + lower_boundary.json() + combined.json()
    )


def test_search_filters_inclusive_follower_range_and_excludes_unknown(client):
    seed_kols(client)
    unknown = client.post(
        "/kols",
        json={"platform": "YouTube", "handle": "@unknown", "country": "GB"},
    )
    assert unknown.status_code == 201

    minimum = client.get("/kols", params={"min_followers": 50000})
    maximum = client.get("/kols", params={"max_followers": 50000})
    range_response = client.get(
        "/kols",
        params={"min_followers": 50000, "max_followers": 120000},
    )
    combined = client.get(
        "/kols",
        params={"country": "GB", "platform": "YouTube", "min_followers": 120000},
    )

    assert minimum.status_code == 200
    assert [kol["handle"] for kol in minimum.json()] == ["@alex", "@mobil"]
    assert maximum.status_code == 200
    assert [kol["handle"] for kol in maximum.json()] == ["@mobil"]
    assert range_response.status_code == 200
    assert [kol["handle"] for kol in range_response.json()] == ["@alex", "@mobil"]
    assert combined.status_code == 200
    assert [kol["handle"] for kol in combined.json()] == ["@alex"]
    assert all(
        kol["handle"] != "@unknown"
        for kol in minimum.json()
        + maximum.json()
        + range_response.json()
        + combined.json()
    )


def test_default_search_orders_value_high_and_risk_low(client):
    seed_kols(client)

    kols = client.get("/kols").json()

    assert [kol["handle"] for kol in kols] == ["@alex", "@mobil"]
    assert kols[0]["score_summary"]["commercial_score"] == 80
    assert kols[0]["score_summary"]["risk_level"] == "low"


def test_manual_override_preserves_auto_score(client):
    seed_kols(client)
    kol_id = client.get("/kols?country=UK").json()[0]["id"]

    response = client.post(
        f"/kols/{kol_id}/scores",
        json={
            "score_type": "commercial",
            "dimension": "audience_fit",
            "manual_score": 95,
            "evidence": "Reviewed audience report",
            "source": "analyst",
        },
    )

    assert response.status_code == 200
    record = next(
        item
        for item in response.json()["score_records"]
        if item["dimension"] == "audience_fit"
    )
    assert record["auto_score"] == 80
    assert record["manual_score"] == 95
    assert record["final_score"] == 95
    assert response.json()["score_summary"]["commercial_score"] > 80


def test_manual_override_rejects_unknown_dimension(client):
    seed_kols(client)
    kol_id = client.get("/kols").json()[0]["id"]

    response = client.post(
        f"/kols/{kol_id}/scores",
        json={
            "score_type": "commercial",
            "dimension": "made_up",
            "manual_score": 50,
        },
    )

    assert response.status_code == 422


def test_enrich_youtube_updates_missing_followers(client, monkeypatch):
    csv_data = (
        "platform,country,handle,name,profile_url,followers\n"
        "YouTube,UK,@ukev,UK EV,https://www.youtube.com/@ukev,\n"
        "TikTok,DE,@mobil,Mobil DE,,50000\n"
    )
    response = client.post(
        "/imports",
        files={"file": ("seed.csv", csv_data.encode(), "text/csv")},
    )
    assert response.status_code == 201
    kol_id = client.get("/kols?platform=YouTube").json()[0]["id"]

    def fake_fetch(url):
        assert url == "https://www.youtube.com/@ukev"
        return {
            "id": "UC123",
            "channel": "UK EV Reviews",
            "channel_url": "https://www.youtube.com/@ukev",
            "channel_follower_count": 123456,
            "description": "BYD and electric car reviews in Britain",
        }

    monkeypatch.setattr("app.api.kols.fetch_youtube_channel_metadata", fake_fetch)

    enrich = client.post("/kols/enrich-youtube", json={"kol_ids": [kol_id]})

    assert enrich.status_code == 200
    assert enrich.json() == {
        "requested": 1,
        "updated": 1,
        "skipped": 0,
        "failed": 0,
    }
    updated = client.get(f"/kols/{kol_id}").json()
    assert updated["followers"] == 123456
    assert updated["platform_account_id"] == "UC123"
    assert updated["name"] == "UK EV Reviews"


def test_enrich_youtube_skips_non_youtube_and_complete_rows(client, monkeypatch):
    seed_kols(client)
    kol_ids = [item["id"] for item in client.get("/kols").json()]
    calls = []

    def fake_fetch(url):
        calls.append(url)
        return {"channel_follower_count": 999}

    monkeypatch.setattr("app.api.kols.fetch_youtube_channel_metadata", fake_fetch)

    response = client.post("/kols/enrich-youtube", json={"kol_ids": kol_ids})

    assert response.status_code == 200
    assert response.json()["updated"] == 0
    assert response.json()["skipped"] == 2
    assert calls == []


def test_enrich_youtube_handles_row_deleted_during_lookup(client, monkeypatch):
    from app.models import Kol

    csv_data = (
        "platform,country,handle,name,profile_url,followers\n"
        "YouTube,UK,@ukev,UK EV,https://www.youtube.com/@ukev,\n"
    )
    response = client.post(
        "/imports",
        files={"file": ("seed.csv", csv_data.encode(), "text/csv")},
    )
    assert response.status_code == 201
    kol_id = client.get("/kols").json()[0]["id"]

    def fake_fetch(url):
        with client.app.state.session_factory() as session:
            kol = session.get(Kol, kol_id)
            session.delete(kol)
            session.commit()
        return {"channel_follower_count": 123456}

    monkeypatch.setattr("app.api.kols.fetch_youtube_channel_metadata", fake_fetch)

    enrich = client.post("/kols/enrich-youtube", json={"kol_ids": [kol_id]})

    assert enrich.status_code == 200
    assert enrich.json()["updated"] == 0
    assert enrich.json()["failed"] == 1
def test_direct_api_normalizes_country_and_deduplicates_identity_chain(client):
    first = client.post("/kols", json={"platform": "YouTube", "country": "UK", "handle": "@MixedCase", "profile_url": "https://www.youtube.com/@MixedCase/"})
    assert first.status_code == 201
    assert first.json()["country"] == "GB"
    assert client.post("/kols", json={"platform": "youtube", "country": "英国", "handle": "@different", "profile_url": "http://youtube.com/@mixedcase?view=1"}).status_code == 409
    assert client.post("/kols", json={"platform": "YouTube", "country": "GB", "handle": " @MIXEDCASE "}).status_code == 409


def test_direct_update_normalizes_country(client):
    kol = client.post("/kols", json={"platform": "YouTube", "country": "DE", "handle": "@country"}).json()
    updated = client.put(f"/kols/{kol['id']}", json={"country": "United Kingdom"})
    assert updated.status_code == 200
    assert updated.json()["country"] == "GB"
