import sys
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from app.collectors.base import CollectionError
from app.collectors.reddit import RedditCollector, _default_fetch as reddit_default_fetch
from app.collectors.tiktok import TikTokDatasetCollector, _default_fetch as tiktok_default_fetch
from app.collectors.youtube import YouTubeCollector, _default_search


def test_youtube_collector_normalizes_search_items():
    def fake_search(keyword, limit):
        return [
            {
                "channel": "UK EV Reviews",
                "channel_id": "UC123",
                "channel_url": "https://www.youtube.com/@ukev",
                "uploader_id": "@ukev",
                "title": "BYD Seal UK review",
                "description": "Chinese EV tested in Britain",
                "view_count": 10000,
                "like_count": 600,
                "comment_count": 80,
                "channel_follower_count": 120000,
                "webpage_url": "https://www.youtube.com/watch?v=abc",
            }
        ]

    collector = YouTubeCollector(search_func=fake_search)
    profiles = collector.collect(
        keywords=["BYD"],
        languages=["en"],
        markets=["UK"],
        limit=5,
    )

    assert len(profiles) == 1
    assert profiles[0].platform == "YouTube"
    assert profiles[0].handle == "@ukev"
    assert profiles[0].platform_account_id == "UC123"
    assert profiles[0].country_hint == "GB"
    assert profiles[0].language_hint == "en"
    assert "automotive" in profiles[0].content_categories
    assert "ev" in profiles[0].content_categories
    assert "car_review" in profiles[0].content_categories
    assert profiles[0].average_engagement_rate == 0.068


def test_youtube_collector_does_not_overstate_language_or_categories():
    def fake_search(keyword, limit):
        return [
            {
                "channel": "Daily Notes",
                "channel_id": "UC999",
                "channel_url": "https://www.youtube.com/@daily",
                "uploader_id": "@daily",
                "title": "Cafes and city walks",
                "description": "Weekend routine",
                "view_count": 1000,
                "like_count": 20,
                "comment_count": 5,
                "webpage_url": "https://www.youtube.com/watch?v=daily",
            }
        ]

    collector = YouTubeCollector(search_func=fake_search)
    profiles = collector.collect(
        keywords=["BYD"],
        languages=["en"],
        markets=["UK"],
        limit=5,
    )

    assert profiles[0].language_hint is None
    assert profiles[0].content_categories == "youtube_channel"


def test_youtube_collector_does_not_read_ev_from_review_word():
    def fake_search(keyword, limit):
        return [
            {
                "channel": "Makeup Notes",
                "channel_id": "UC998",
                "channel_url": "https://www.youtube.com/@makeup",
                "uploader_id": "@makeup",
                "title": "Makeup review",
                "description": "Weekend routine",
                "view_count": 1000,
                "like_count": 20,
                "comment_count": 5,
                "webpage_url": "https://www.youtube.com/watch?v=makeup",
            }
        ]

    collector = YouTubeCollector(search_func=fake_search)
    profiles = collector.collect(
        keywords=["BYD"],
        languages=["en"],
        markets=["UK"],
        limit=5,
    )

    assert profiles[0].language_hint == "en"
    assert profiles[0].content_categories == "youtube_channel"


def test_youtube_collector_infers_german_language_from_content():
    def fake_search(keyword, limit):
        return [
            {
                "channel": "Autobahn EV",
                "channel_id": "UCDE",
                "channel_url": "https://www.youtube.com/@autobahnev",
                "uploader_id": "@autobahnev",
                "title": "BYD auf der Autobahn",
                "description": "Deutschland electric car review",
                "view_count": 1000,
                "like_count": 20,
                "comment_count": 5,
                "webpage_url": "https://www.youtube.com/watch?v=de",
            }
        ]

    collector = YouTubeCollector(search_func=fake_search)
    profiles = collector.collect(
        keywords=["BYD"],
        languages=["en"],
        markets=["DE"],
        limit=5,
    )

    assert profiles[0].country_hint == "DE"
    assert profiles[0].language_hint == "de"


def test_youtube_collector_infers_french_market_and_language():
    def fake_search(keyword, limit):
        return [{
            "channel": "Essais Auto Paris",
            "channel_id": "UCFR",
            "title": "Essai BYD en France",
            "description": "Voiture électrique, avis en français",
        }]

    profile = YouTubeCollector(search_func=fake_search).collect(
        keywords=["BYD"], languages=["fr"], markets=["FR"], limit=5
    )[0]

    assert profile.country_hint == "FR"
    assert profile.language_hint == "fr"


def test_youtube_collector_dedupes_channels_and_respects_limit():
    def fake_search(keyword, limit):
        return [
            {
                "channel": "UK EV Reviews",
                "channel_id": "UC123",
                "channel_url": "https://www.youtube.com/@ukev",
                "uploader_id": "@ukev",
                "title": f"{keyword} first review",
                "description": "EV launch in Britain",
                "view_count": 1000,
                "like_count": 50,
                "comment_count": 10,
                "channel_follower_count": 120000,
                "webpage_url": "https://www.youtube.com/watch?v=abc",
            },
            {
                "channel": "UK EV Reviews",
                "channel_id": "UC123",
                "channel_url": "https://www.youtube.com/@ukev",
                "uploader_id": "@ukev",
                "title": f"{keyword} second review",
                "description": "Another EV launch in the UK",
                "view_count": 2000,
                "like_count": 70,
                "comment_count": 20,
                "channel_follower_count": 120000,
                "webpage_url": "https://www.youtube.com/watch?v=def",
            },
        ]

    collector = YouTubeCollector(search_func=fake_search)
    profiles = collector.collect(
        keywords=["BYD", "NIO"],
        languages=["en"],
        markets=["UK"],
        limit=1,
    )

    assert len(profiles) == 1
    assert profiles[0].platform_account_id == "UC123"


def test_youtube_collector_returns_empty_for_zero_limit():
    def fake_search(keyword, limit):
        return [
            {
                "channel": "UK EV Reviews",
                "channel_id": "UC123",
                "title": "BYD UK review",
            }
        ]

    collector = YouTubeCollector(search_func=fake_search)

    assert collector.collect(keywords=["BYD"], languages=["en"], markets=["UK"], limit=0) == []


def test_youtube_default_search_uses_flat_public_metadata(monkeypatch):
    captured = {}

    class FakeYoutubeDL:
        def __init__(self, options):
            captured["options"] = options

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def extract_info(self, query, download):
            captured["query"] = query
            captured["download"] = download
            return {"entries": [{"title": "BYD UK review"}, None, "bad"]}

    monkeypatch.setitem(
        sys.modules,
        "yt_dlp",
        SimpleNamespace(YoutubeDL=FakeYoutubeDL),
    )

    results = _default_search("BYD UK review", 1)

    assert results == [{"title": "BYD UK review"}]
    assert captured["query"] == "ytsearch1:BYD UK review"
    assert captured["download"] is False
    assert captured["options"]["extract_flat"] is True
    assert captured["options"]["ignoreerrors"] is True


def test_reddit_collector_aggregates_authors():
    def fake_fetch(keyword, limit):
        return [
            {
                "author": "evdriver",
                "subreddit": "electricvehicles",
                "title": "BYD in Germany",
                "selftext": "Autobahn range discussion",
                "score": 42,
                "num_comments": 8,
                "permalink": "/r/electricvehicles/comments/abc/byd/",
            },
            {
                "author": "evdriver",
                "subreddit": "cars",
                "title": "Chinese EV UK launch",
                "selftext": "",
                "score": 30,
                "num_comments": 5,
                "permalink": "/r/cars/comments/def/chinese_ev/",
            },
        ]

    collector = RedditCollector(fetch_func=fake_fetch)
    profiles = collector.collect(
        keywords=["BYD"],
        languages=["en"],
        markets=["UK", "DE"],
        limit=10,
    )

    assert len(profiles) == 1
    assert profiles[0].platform == "Reddit"
    assert profiles[0].handle == "u/evdriver"
    assert profiles[0].platform_account_id == "evdriver"
    assert "community_discussion" in profiles[0].content_categories
    assert profiles[0].language_hint == "de"
    assert profiles[0].average_engagement_rate is not None


def test_reddit_collector_skips_deleted_authors():
    def fake_fetch(keyword, limit):
        return [
            {
                "author": "[deleted]",
                "subreddit": "cars",
                "title": "BYD thread",
                "selftext": "",
                "score": 10,
                "num_comments": 2,
                "permalink": "/r/cars/comments/abc/byd/",
            },
            {
                "author": None,
                "subreddit": "electricvehicles",
                "title": "UK launch",
                "selftext": "",
                "score": 8,
                "num_comments": 1,
                "permalink": "/r/electricvehicles/comments/def/uk_launch/",
            },
        ]

    collector = RedditCollector(fetch_func=fake_fetch)
    profiles = collector.collect(
        keywords=["BYD"],
        languages=["en"],
        markets=["UK"],
        limit=10,
    )

    assert profiles == []


def test_reddit_collector_does_not_default_unknown_language_to_english():
    def fake_fetch(keyword, limit):
        return [
            {
                "author": "dailywalker",
                "subreddit": "citywalks",
                "title": "Cafe notes",
                "selftext": "Weekend routine",
                "score": 3,
                "num_comments": 1,
                "permalink": "/r/citywalks/comments/abc/cafe/",
            }
        ]

    collector = RedditCollector(fetch_func=fake_fetch)
    profiles = collector.collect(
        keywords=["BYD"],
        languages=["en"],
        markets=["UK"],
        limit=10,
    )

    assert profiles[0].language_hint is None


def test_reddit_collector_returns_empty_for_zero_limit():
    def fake_fetch(keyword, limit):
        return [
            {
                "author": "evdriver",
                "subreddit": "electricvehicles",
                "title": "BYD in Germany",
                "selftext": "",
                "score": 42,
                "num_comments": 8,
                "permalink": "/r/electricvehicles/comments/abc/byd/",
            }
        ]

    collector = RedditCollector(fetch_func=fake_fetch)

    assert collector.collect(keywords=["BYD"], languages=["en"], markets=["DE"], limit=0) == []


def test_reddit_default_fetch_wraps_malformed_json(monkeypatch):
    class BrokenResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b"not-json"

    def fake_urlopen(request, timeout):
        return BrokenResponse()

    monkeypatch.setattr("app.collectors.reddit.urlopen", fake_urlopen)

    with pytest.raises(CollectionError):
        reddit_default_fetch("BYD", 1)


def test_reddit_default_fetch_explains_public_403(monkeypatch):
    def fake_urlopen(request, timeout):
        raise HTTPError(
            url=request.full_url,
            code=403,
            msg="Blocked",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("app.collectors.reddit.urlopen", fake_urlopen)

    with pytest.raises(CollectionError, match="reddit public search is blocked"):
        reddit_default_fetch("BYD", 1)


def test_tiktok_dataset_collector_maps_uk_creator_metrics():
    def fake_fetch(offset, limit):
        if offset > 0:
            return []
        return [
            {
                "uid": "123",
                "unique_id": "ukevtok",
                "nickname": "UK EV Tok",
                "signature": "BYD UK electric car reviews",
                "region": "GB",
                "language": "en",
                "verified": True,
                "aweme_count": 25,
                "total_favorited": 250000,
                "follower_count": 100000,
            }
        ]

    collector = TikTokDatasetCollector(fetch_func=fake_fetch)
    profiles = collector.collect(
        keywords=["BYD"],
        languages=["en"],
        markets=["UK"],
        limit=10,
    )

    assert len(profiles) == 1
    assert profiles[0].platform == "TikTok"
    assert profiles[0].handle == "@ukevtok"
    assert profiles[0].platform_account_id == "123"
    assert profiles[0].profile_url == "https://www.tiktok.com/@ukevtok"
    assert profiles[0].country_hint == "UK"
    assert profiles[0].language_hint == "en"
    assert profiles[0].followers == 100000
    assert profiles[0].average_engagement_rate == 0.1
    assert "tiktok_dataset" in profiles[0].content_categories
    assert "total likes: 250000" in profiles[0].evidence


def test_tiktok_dataset_collector_filters_language_market_and_keywords():
    def fake_fetch(offset, limit):
        if offset > 0:
            return []
        return [
            {
                "uid": "de-ok",
                "unique_id": "auto_de",
                "nickname": "Auto Deutschland",
                "signature": "BYD Deutschland EV",
                "region": "DE",
                "language": "de",
                "aweme_count": 10,
                "total_favorited": 5000,
                "follower_count": 20000,
            },
            {
                "uid": "uk-no-keyword",
                "unique_id": "fashion_uk",
                "nickname": "London Style",
                "signature": "fashion notes",
                "region": "GB",
                "language": "en",
                "aweme_count": 5,
                "total_favorited": 1000,
                "follower_count": 10000,
            },
            {
                "uid": "us-wrong-market",
                "unique_id": "byd_us",
                "nickname": "BYD US",
                "signature": "BYD electric cars",
                "region": "US",
                "language": "en",
                "aweme_count": 5,
                "total_favorited": 1000,
                "follower_count": 10000,
            },
        ]

    collector = TikTokDatasetCollector(fetch_func=fake_fetch)
    profiles = collector.collect(
        keywords=["BYD"],
        languages=["de"],
        markets=["DE"],
        limit=10,
    )

    assert [profile.handle for profile in profiles] == ["@auto_de"]


def test_tiktok_dataset_collector_paginates_until_match():
    calls = []

    def fake_fetch(offset, limit):
        calls.append(offset)
        if offset == 0:
            return [
                {
                    "uid": "us-first",
                    "unique_id": "byd_us",
                    "nickname": "BYD US",
                    "signature": "BYD electric cars",
                    "region": "US",
                    "language": "en",
                    "follower_count": 10000,
                }
            ]
        return [
            {
                "uid": "uk-second",
                "unique_id": "byd_uk",
                "nickname": "BYD UK",
                "signature": "BYD electric cars in Britain",
                "region": "GB",
                "language": "en",
                "follower_count": 20000,
            }
        ]

    collector = TikTokDatasetCollector(fetch_func=fake_fetch)
    profiles = collector.collect(
        keywords=["BYD"],
        languages=["en"],
        markets=["UK"],
        limit=1,
    )

    assert [profile.handle for profile in profiles] == ["@byd_uk"]
    assert calls == [0, 20]


def test_tiktok_dataset_collector_keeps_profiles_found_before_rate_limit():
    def fake_fetch(offset, limit):
        if offset == 0:
            return [
                {
                    "uid": "uk-first",
                    "unique_id": "byd_uk",
                    "nickname": "BYD UK",
                    "signature": "electric cars in Britain",
                    "region": "GB",
                    "language": "en",
                    "follower_count": 20000,
                }
            ]
        raise CollectionError("TikTok 数据集接口限流，请稍后重试。")

    collector = TikTokDatasetCollector(fetch_func=fake_fetch)
    profiles = collector.collect(
        keywords=["BYD UK"],
        languages=["en"],
        markets=["UK"],
        limit=2,
    )

    assert [profile.handle for profile in profiles] == ["@byd_uk"]


def test_tiktok_dataset_collector_caps_dataset_scan_depth():
    calls = []

    def fake_fetch(offset, limit):
        calls.append(offset)
        return [
            {
                "uid": f"us-{offset}",
                "unique_id": f"byd_us_{offset}",
                "nickname": "BYD US",
                "signature": "BYD electric cars",
                "region": "US",
                "language": "en",
            }
        ]

    collector = TikTokDatasetCollector(fetch_func=fake_fetch)
    profiles = collector.collect(
        keywords=["BYD"],
        languages=["en"],
        markets=["UK"],
        limit=30,
    )

    assert profiles == []
    assert calls == list(range(0, 250, 50))


def test_tiktok_dataset_collector_returns_empty_for_zero_limit():
    collector = TikTokDatasetCollector(fetch_func=lambda offset, limit: [{"unique_id": "x"}])

    assert collector.collect(keywords=["BYD"], languages=["en"], markets=["UK"], limit=0) == []


def test_tiktok_default_fetch_uses_cached_rows_when_rate_limited(monkeypatch):
    responses = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return self.payload

    def fake_urlopen(request, timeout):
        responses.append(request.full_url)
        if len(responses) == 1:
            return FakeResponse(
                b'{"rows":[{"row":{"unique_id":"cached_byd","region":"GB","language":"en"}}]}'
            )
        raise HTTPError(
            url=request.full_url,
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("app.collectors.tiktok.urlopen", fake_urlopen)

    assert tiktok_default_fetch(0, 10)[0]["unique_id"] == "cached_byd"
    assert tiktok_default_fetch(0, 10)[0]["unique_id"] == "cached_byd"


def test_tiktok_default_fetch_explains_rate_limit_without_cache(monkeypatch):
    def fake_urlopen(request, timeout):
        raise HTTPError(
            url=request.full_url,
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("app.collectors.tiktok.urlopen", fake_urlopen)

    with pytest.raises(CollectionError, match="TikTok 数据集接口限流"):
        tiktok_default_fetch(0, 11)
