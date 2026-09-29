from sqlalchemy import select

from app.collectors.base import CollectedProfile
from app.models import Kol, ScoreRecord
from app.services.collection import (
    CollectionCounters,
    build_auto_scores,
    persist_collected_profiles,
)


def test_persist_collected_profile_creates_kol_and_scores(client):
    app = client.app
    profile = CollectedProfile(
        platform="YouTube",
        handle="@ukev",
        platform_account_id="channel-1",
        name="UK EV Reviews",
        profile_url="https://www.youtube.com/@ukev",
        country_hint="UK",
        language_hint="en",
        content_text="BYD electric car review in the UK",
        content_categories="automotive,ev,car_review",
        followers=120000,
        average_engagement_rate=0.034,
        evidence=["matched keyword: BYD", "matched market: UK"],
        source_url="https://www.youtube.com/watch?v=abc",
    )

    with app.state.session_factory() as session:
        counters = persist_collected_profiles(
            session=session,
            job_id=1,
            profiles=[profile],
            markets=["UK", "DE"],
            languages=["en", "de"],
        )
        kol = session.scalar(select(Kol).where(Kol.platform_account_id == "channel-1"))
        assert kol is not None
        records = list(
            session.scalars(select(ScoreRecord).where(ScoreRecord.kol_id == kol.id))
        )
        country = kol.country
        language = kol.language
        followers = kol.followers
        dimensions = {record.dimension for record in records}

    assert counters == CollectionCounters(total_found=1, created=1)
    assert country == "GB"
    assert language == "en"
    assert followers == 120000
    assert dimensions >= {
        "audience_fit",
        "content_relevance",
        "brand_fit",
        "interaction_quality",
    }


def test_persist_collected_profile_updates_existing_kol(client):
    app = client.app
    first = CollectedProfile(
        platform="YouTube",
        handle="@ukev",
        platform_account_id="channel-1",
        name="UK EV Reviews",
        profile_url="https://www.youtube.com/@ukev",
        country_hint="UK",
        language_hint="en",
        content_text="BYD electric car review in the UK",
        content_categories="automotive",
        followers=120000,
        average_engagement_rate=0.034,
        evidence=["matched market: UK"],
        source_url="https://www.youtube.com/watch?v=abc",
    )
    second = CollectedProfile(
        platform="YouTube",
        handle="@ukev",
        platform_account_id="channel-1",
        name="UK EV Reviews Updated",
        profile_url="https://www.youtube.com/@ukev",
        country_hint="UK",
        language_hint="en",
        content_text="NIO test drive in Britain",
        content_categories="automotive,ev",
        followers=150000,
        average_engagement_rate=0.05,
        evidence=["matched market: UK"],
        source_url="https://www.youtube.com/watch?v=xyz",
    )

    with app.state.session_factory() as session:
        first_counters = persist_collected_profiles(
            session=session,
            job_id=1,
            profiles=[first],
            markets=["UK", "DE"],
            languages=["en", "de"],
        )
        second_counters = persist_collected_profiles(
            session=session,
            job_id=1,
            profiles=[second],
            markets=["UK", "DE"],
            languages=["en", "de"],
        )
        kols = list(session.scalars(select(Kol)))
        assert len(kols) == 1
        kol = kols[0]
        followers = kol.followers
        name = kol.name

    assert first_counters == CollectionCounters(total_found=1, created=1)
    assert second_counters == CollectionCounters(total_found=1, updated=1)
    assert followers == 150000
    assert name == "UK EV Reviews Updated"


def test_persist_collected_profile_normalizes_platform_for_dedupe(client):
    app = client.app
    first = CollectedProfile(
        platform="YouTube",
        handle="@ukev",
        platform_account_id="channel-1",
        name="UK EV Reviews",
        profile_url="https://www.youtube.com/@ukev",
        country_hint="UK",
        language_hint="en",
        content_text="BYD electric car review in the UK",
        content_categories="automotive",
        followers=120000,
        average_engagement_rate=None,
        evidence=["matched market: UK"],
        source_url=None,
    )
    second = CollectedProfile(
        platform="youtube",
        handle="@ukev",
        platform_account_id="channel-1",
        name="UK EV Reviews Lowercase",
        profile_url="https://www.youtube.com/@ukev",
        country_hint="UK",
        language_hint="en",
        content_text="BYD electric car review in the UK",
        content_categories="automotive",
        followers=125000,
        average_engagement_rate=None,
        evidence=["matched market: UK"],
        source_url=None,
    )

    with app.state.session_factory() as session:
        persist_collected_profiles(session, 1, [first], ["UK"], ["en"])
        counters = persist_collected_profiles(session, 2, [second], ["UK"], ["en"])
        kols = list(session.scalars(select(Kol)))
        platform = kols[0].platform
        followers = kols[0].followers
        score_source = session.scalar(
            select(ScoreRecord.source).where(ScoreRecord.kol_id == kols[0].id)
        )

    assert counters == CollectionCounters(total_found=1, updated=1)
    assert len(kols) == 1
    assert platform == "YouTube"
    assert followers == 125000
    assert score_source == "collection:2:youtube"


def test_persist_collected_profile_skips_missing_identity(client):
    app = client.app
    profile = CollectedProfile(
        platform="YouTube",
        handle=None,
        platform_account_id=None,
        name="Unknown",
        profile_url=None,
        country_hint="UK",
        language_hint="en",
        content_text="EV review UK",
        content_categories=None,
        followers=None,
        average_engagement_rate=None,
        evidence=["matched market: UK"],
        source_url=None,
    )

    with app.state.session_factory() as session:
        counters = persist_collected_profiles(
            session=session,
            job_id=1,
            profiles=[profile],
            markets=["UK", "DE"],
            languages=["en", "de"],
        )
        total_kols = len(list(session.scalars(select(Kol))))

    assert counters == CollectionCounters(total_found=1, skipped=1)
    assert total_kols == 0


def test_auto_scores_do_not_invent_content_or_brand_fit_without_topic_evidence():
    profile = CollectedProfile(
        platform="YouTube",
        handle="@londonlife",
        platform_account_id="channel-life",
        name="London Life",
        profile_url=None,
        country_hint="UK",
        language_hint="en",
        content_text="A weekend walk around London cafes",
        content_categories="lifestyle",
        followers=None,
        average_engagement_rate=None,
        evidence=["matched market: UK"],
        source_url=None,
    )

    scores = build_auto_scores(profile, "UK")

    assert ("commercial", "audience_fit") in scores
    assert ("commercial", "content_relevance") not in scores
    assert ("commercial", "brand_fit") not in scores


def test_auto_scores_use_word_boundaries_for_short_terms():
    for text in (
        "Makeup review in London",
        "5mg caffeine routine and cafe review",
        "Everyday productivity notes",
    ):
        profile = CollectedProfile(
            platform="YouTube",
            handle="@londonlife",
            platform_account_id="channel-life",
            name="London Life",
            profile_url=None,
            country_hint="UK",
            language_hint="en",
            content_text=text,
            content_categories="lifestyle",
            followers=None,
            average_engagement_rate=None,
            evidence=["matched market: UK"],
            source_url=None,
        )

        scores = build_auto_scores(profile, "UK")

        assert ("commercial", "audience_fit") in scores
        assert ("commercial", "content_relevance") not in scores
        assert ("commercial", "brand_fit") not in scores


def test_auto_scores_use_word_boundaries_for_risk_terms():
    profile = CollectedProfile(
        platform="YouTube",
        handle="@technotes",
        platform_account_id="channel-tech",
        name="Tech Notes",
        profile_url=None,
        country_hint="UK",
        language_hint="en",
        content_text="Nokia phone notes and a 5mg caffeine routine",
        content_categories="technology",
        followers=None,
        average_engagement_rate=None,
        evidence=["matched market: UK"],
        source_url=None,
    )

    scores = build_auto_scores(profile, "UK")

    assert ("risk", "competitor_conflict") not in scores


def test_persist_collected_profile_supports_france_with_evidence(client):
    app = client.app
    profile = CollectedProfile(
        platform="YouTube",
        handle="@francev",
        platform_account_id="channel-fr",
        name="France EV Reviews",
        profile_url="https://www.youtube.com/@francev",
        country_hint="FR",
        language_hint="fr",
        content_text="Essai BYD en France",
        content_categories="automotive,ev",
        followers=80000,
        average_engagement_rate=0.04,
        evidence=["matched keyword: BYD"],
        source_url="https://www.youtube.com/watch?v=fr1",
    )

    with app.state.session_factory() as session:
        counters = persist_collected_profiles(
            session=session,
            job_id=1,
            profiles=[profile],
            markets=["FR"],
            languages=["fr"],
        )
        total_kols = len(list(session.scalars(select(Kol))))

    assert counters == CollectionCounters(total_found=1, created=1)
    assert total_kols == 1


def test_persist_collected_profile_allows_unknown_language_with_market_evidence(client):
    app = client.app
    profile = CollectedProfile(
        platform="YouTube",
        handle="@berlinev",
        platform_account_id="channel-de",
        name="Berlin EV Reviews",
        profile_url="https://www.youtube.com/@berlinev",
        country_hint="DE",
        language_hint=None,
        content_text="BYD electric car review on the Autobahn",
        content_categories="automotive,ev",
        followers=90000,
        average_engagement_rate=None,
        evidence=["matched market: DE"],
        source_url="https://www.youtube.com/watch?v=de1",
    )

    with app.state.session_factory() as session:
        counters = persist_collected_profiles(
            session=session,
            job_id=1,
            profiles=[profile],
            markets=["UK", "DE"],
            languages=["en", "de"],
        )
        kol = session.scalar(select(Kol).where(Kol.platform_account_id == "channel-de"))
        country = kol.country if kol else None
        language = kol.language if kol else "missing"

    assert counters == CollectionCounters(total_found=1, created=1)
    assert country == "DE"
    assert language is None


def test_persist_collected_profile_infers_germany_from_german_language(client):
    app = client.app
    profile = CollectedProfile(
        platform="YouTube",
        handle="@deev",
        platform_account_id="channel-language-de",
        name="Deutsch EV",
        profile_url="https://www.youtube.com/@deev",
        country_hint=None,
        language_hint="de",
        content_text="BYD electric car review",
        content_categories="automotive,ev",
        followers=50000,
        average_engagement_rate=None,
        evidence=["matched keyword: BYD"],
        source_url=None,
    )

    with app.state.session_factory() as session:
        counters = persist_collected_profiles(
            session=session,
            job_id=1,
            profiles=[profile],
            markets=["DE"],
            languages=["de"],
        )
        kol = session.scalar(
            select(Kol).where(Kol.platform_account_id == "channel-language-de")
        )
        country = kol.country if kol else None

    assert counters == CollectionCounters(total_found=1, created=1)
    assert country == "DE"


def test_persist_collected_profiles_keeps_successful_rows_when_later_row_fails(client):
    app = client.app
    good = CollectedProfile(
        platform="YouTube",
        handle="@ukev",
        platform_account_id="channel-1",
        name="UK EV Reviews",
        profile_url="https://www.youtube.com/@ukev",
        country_hint="UK",
        language_hint="en",
        content_text="BYD electric car review in the UK",
        content_categories="automotive,ev",
        followers=120000,
        average_engagement_rate=None,
        evidence=["matched market: UK"],
        source_url=None,
    )
    bad = CollectedProfile(
        platform="YouTube",
        handle="@bad",
        platform_account_id="channel-bad",
        name="Bad Score",
        profile_url=None,
        country_hint="UK",
        language_hint="en",
        content_text="BYD electric car review in the UK",
        content_categories="automotive,ev",
        followers=None,
        average_engagement_rate=2,
        evidence=["matched market: UK"],
        source_url=None,
    )

    with app.state.session_factory() as session:
        counters = persist_collected_profiles(
            session,
            1,
            [good, bad],
            ["UK"],
            ["en"],
        )
        kols = list(session.scalars(select(Kol).order_by(Kol.id)))

    assert counters == CollectionCounters(total_found=2, created=1, failed=1)
    assert len(kols) == 1
    assert kols[0].platform_account_id == "channel-1"
