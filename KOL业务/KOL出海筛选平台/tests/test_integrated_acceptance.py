from io import BytesIO

from openpyxl import load_workbook

from app.collectors.base import CollectedProfile
from app.security import SESSION_HEADER


def wait_for_job(client, job_id, attempts=5):
    for _ in range(attempts):
        job = client.get(f"/collections/{job_id}").json()
        if job["status"] in {"completed", "failed"}:
            return job
    raise AssertionError("collection job did not finish")


def test_mocked_youtube_discovery_to_scored_comparison_and_filtered_export(client):
    class FakeYoutube:
        platform = "youtube"

        def collect(self, *, keywords, languages, markets, limit):
            assert keywords == ["BYD"]
            assert languages == ["en"]
            assert markets == ["GB"]
            return [CollectedProfile(
                platform="YouTube",
                handle="@british-ev",
                platform_account_id="UC-acceptance",
                name="British EV Lab",
                profile_url="https://www.youtube.com/@british-ev",
                country_hint="GB",
                language_hint="en",
                content_text="Independent BYD electric car review for UK drivers",
                content_categories="automotive,ev,car_review",
                followers=125_000,
                average_engagement_rate=0.042,
                evidence=["matched keyword: BYD", "matched market: GB"],
                source_url="https://www.youtube.com/watch?v=acceptance",
            )]

    assert client.headers[SESSION_HEADER] == "pytest-session"
    client.app.state.collection_collectors = {"youtube": FakeYoutube()}
    created = client.post("/collections", json={
        "keywords": ["BYD"], "markets": ["GB"],
        "languages": ["en"], "limit_per_platform": 10,
    })
    assert created.status_code == 201

    finished = wait_for_job(client, created.json()["job_id"])
    assert finished["status"] == "completed"
    assert finished["created_count"] == 1
    kol = client.get("/kols", params={"country": "GB"}).json()[0]
    assert kol["platform_account_id"] == "UC-acceptance"
    assert kol["score_summary"]["commercial_completeness"] > 0

    compared = client.post("/comparisons", json={"kol_ids": [kol["id"]]})
    assert compared.status_code == 200
    comparison = compared.json()["items"][0]
    assert comparison["score_records"]
    assert any(record["evidence"] for record in comparison["score_records"])

    exported = client.get("/exports/kols.xlsx", params={"country": "GB"})
    assert exported.status_code == 200
    rows = list(load_workbook(BytesIO(exported.content), read_only=True).active.values)
    assert len(rows) == 2
    assert rows[1][rows[0].index("Country")] == "GB"
    assert rows[1][rows[0].index("KOL")] == "British EV Lab"
