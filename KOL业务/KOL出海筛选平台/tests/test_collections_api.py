from sqlalchemy import select

from app.collectors.base import CollectedProfile, CollectionError
from app.models import Kol


class EmptyCollector:
    platform = "youtube"

    def collect(self, *, keywords, languages, markets, limit):
        return []


def install_fake_collectors(client):
    client.app.state.collection_collectors = {"youtube": EmptyCollector()}


def test_create_collection_job_uses_defaults(client):
    install_fake_collectors(client)

    response = client.post("/collections", json={})

    assert response.status_code == 201
    payload = response.json()
    assert payload["job_id"] >= 1
    assert payload["status"] in {"queued", "running", "completed", "partial_failed"}


def test_collection_status_returns_counts_and_logs(client):
    install_fake_collectors(client)

    created = client.post(
        "/collections",
        json={
            "keywords": ["BYD", "Chinese EV"],
            "languages": ["en"],
            "markets": ["GB"],
            "limit_per_platform": 5,
        },
    )

    response = client.get(f"/collections/{created.json()['job_id']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == created.json()["job_id"]
    assert payload["platforms"] == ["youtube"]
    assert "created_count" in payload
    assert "updated_count" in payload
    assert "skipped_count" in payload
    assert "failed_count" in payload
    assert isinstance(payload["logs"], list)


def test_collection_is_always_youtube(client):
    install_fake_collectors(client)
    response = client.post("/collections", json={
        "keywords": ["BYD", "electric car review"],
        "markets": ["GB", "FR"],
        "languages": ["en", "fr"],
        "limit_per_platform": 20,
    })

    assert response.status_code == 201
    status = client.get(f"/collections/{response.json()['job_id']}").json()
    assert status["platforms"] == ["youtube"]
    assert status["markets"] == ["GB", "FR"]


def test_collection_accepts_youtube_reddit_and_tiktok(client):
    client.app.state.collection_collectors = {
        platform: EmptyCollector() for platform in ("youtube", "reddit", "tiktok")
    }
    response = client.post(
        "/collections",
        json={
            "keywords": ["BYD"],
            "platforms": ["youtube", "reddit", "tiktok"],
        },
    )

    assert response.status_code == 201
    status = client.get(f"/collections/{response.json()['job_id']}").json()
    assert status["platforms"] == ["youtube", "reddit", "tiktok"]


def test_collection_status_404_for_missing_job(client):
    response = client.get("/collections/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Collection job not found"


def test_collection_job_runs_only_youtube(client):
    class GoodCollector:
        platform = "youtube"

        def collect(self, *, keywords, languages, markets, limit):
            return [
                CollectedProfile(
                    platform="YouTube",
                    handle="@ukev",
                    platform_account_id="channel-ok",
                    name="UK EV Reviews",
                    profile_url="https://www.youtube.com/@ukev",
                    country_hint="GB",
                    language_hint="en",
                    content_text="BYD electric car review in the UK",
                    content_categories="automotive,ev,car_review",
                    followers=120000,
                    average_engagement_rate=None,
                    evidence=["matched keyword: BYD", "matched market: UK"],
                    source_url="https://www.youtube.com/watch?v=ok",
                )
            ]

    client.app.state.collection_collectors = {"youtube": GoodCollector()}

    created = client.post(
        "/collections",
        json={
            "keywords": ["BYD"],
            "languages": ["en"],
            "markets": ["GB"],
            "limit_per_platform": 5,
        },
    )
    status = client.get(f"/collections/{created.json()['job_id']}").json()

    with client.app.state.session_factory() as session:
        kol = session.scalar(select(Kol).where(Kol.platform_account_id == "channel-ok"))

    assert status["status"] == "completed"
    assert status["created_count"] == 1
    assert status["failed_count"] == 0
    assert kol is not None


def test_collection_uses_configured_key_and_keeps_public_result_on_failure(
    client, monkeypatch
):
    class Credentials:
        def get_youtube_api_key(self):
            return "collection-secret"

    class PublicCollector:
        platform = "youtube"

        def collect(self, *, keywords, languages, markets, limit):
            return [
                CollectedProfile(
                    platform="YouTube", handle="@safe", platform_account_id="UCsafe",
                    name="Public Name", profile_url=None, country_hint="GB",
                    language_hint="en", content_text="British electric car review",
                    content_categories="automotive", followers=50,
                    average_engagement_rate=None,
                )
            ]

    def fail(channel_id, api_key):
        assert channel_id == "UCsafe"
        assert api_key == "collection-secret"
        raise CollectionError("must not be exposed: collection-secret")

    client.app.state.collection_collectors = {"youtube": PublicCollector()}
    client.app.state.credential_store = Credentials()
    monkeypatch.setattr("app.services.collection.enhance_youtube_channel", fail)

    created = client.post("/collections", json={"markets": ["GB"], "languages": ["en"]})
    status = client.get(f"/collections/{created.json()['job_id']}").json()

    assert status["created_count"] == 1
    assert status["failed_count"] == 0
    assert any(log["level"] == "warning" for log in status["logs"])
    assert "collection-secret" not in str(status)


def test_collection_persists_enhanced_engagement_as_fraction(client, monkeypatch):
    class Credentials:
        def get_youtube_api_key(self):
            return "configured"

    class Collector:
        platform = "youtube"

        def collect(self, **kwargs):
            return [CollectedProfile(
                platform="YouTube", handle="@rate", platform_account_id="UCrate",
                name="Rate", profile_url=None, country_hint="GB", language_hint="en",
                content_text="British electric car review", content_categories="automotive",
                followers=10, average_engagement_rate=None,
            )]

    monkeypatch.setattr(
        "app.services.collection.enhance_youtube_channel",
        lambda channel_id, api_key: {
            "subscriber_count": 1000, "average_views": 200.0,
            "err_percent": 4.0, "average_engagement_rate": 0.04,
        },
    )
    client.app.state.collection_collectors = {"youtube": Collector()}
    client.app.state.credential_store = Credentials()

    client.post("/collections", json={"markets": ["GB"], "languages": ["en"]})
    item = client.get("/kols?keyword=@rate").json()[0]

    assert item["followers"] == 1000
    assert item["average_engagement_rate"] == 0.04
def test_collection_deduplicates_url_variant_before_handle(client):
    existing = client.post("/kols", json={
        "platform": "YouTube", "country": "GB", "handle": "@Original",
        "profile_url": "https://www.youtube.com/@SameChannel/",
    })
    assert existing.status_code == 201

    class UrlVariantCollector:
        platform = "youtube"
        def collect(self, *, keywords, languages, markets, limit):
            return [CollectedProfile(
                platform="YouTube", handle="@different", platform_account_id=None,
                name="Updated", profile_url="http://youtube.com/@samechannel?view=1",
                country_hint="GB", language_hint="en", content_text="BYD electric car review UK",
                content_categories="automotive,ev", followers=999,
                average_engagement_rate=None, evidence=["BYD", "UK"], source_url=None,
            )]
    client.app.state.collection_collectors = {"youtube": UrlVariantCollector()}
    job = client.post("/collections", json={"keywords": ["BYD"], "markets": ["GB"], "languages": ["en"], "limit_per_platform": 1}).json()
    finished = client.get(f"/collections/{job['job_id']}").json()
    assert finished["updated_count"] == 1
    assert len(client.get("/kols").json()) == 1
