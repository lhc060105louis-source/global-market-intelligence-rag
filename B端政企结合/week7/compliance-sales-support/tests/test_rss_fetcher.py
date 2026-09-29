from types import SimpleNamespace
from urllib.error import URLError

import pytest

import rss_fetcher as rss
from db import get_session


def test_clean_and_normalize_entry():
    entry = {
        "title": "<b>Electric &amp; Bus</b>",
        "link": " https://example.test/item ",
        "summary": "<p>Clean&nbsp; mobility</p>",
    }
    item = rss.normalize_entry(entry, "Test")
    assert item["title"] == "Electric & Bus"
    assert item["link"] == "https://example.test/item"
    assert item["summary"] == "Clean mobility"
    assert item["published_at"] is None


def test_load_rss_retries_temporary_network_errors(monkeypatch):
    attempts = []

    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return b"<rss><channel><item><title>OK</title><link>https://example.test/ok</link></item></channel></rss>"

    def fake_urlopen(*args, **kwargs):
        attempts.append(1)
        if len(attempts) < 3:
            raise URLError("temporary")
        return Response()

    waits = []
    monkeypatch.setattr(rss, "urlopen", fake_urlopen)
    monkeypatch.setattr(rss.time, "sleep", waits.append)
    status, feed = rss.load_rss("https://example.test/feed")
    assert status == 200
    assert len(feed.entries) == 1
    assert len(attempts) == 3
    assert waits == [1, 2]


def test_load_rss_raises_after_retry_limit(monkeypatch):
    monkeypatch.setattr(rss, "urlopen", lambda *a, **k: (_ for _ in ()).throw(URLError("down")))
    monkeypatch.setattr(rss.time, "sleep", lambda _: None)
    with pytest.raises(URLError):
        rss.load_rss("https://example.test/feed", retries=2)


def test_scheduler_status_endpoint_is_safe_in_tests(client):
    response = client.get("/api/intelligence/scheduler")
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    assert data["active"] is False
    assert data["interval_minutes"] == 60


def test_shared_fetch_runner_records_scheduled_run(monkeypatch):
    import rss_scheduler
    from db import get_session
    from models import FetchLog

    class Result:
        returncode = 0

    monkeypatch.setattr(rss_scheduler.subprocess, "run", lambda *args, **kwargs: Result())
    result = rss_scheduler.run_fetch("scheduled")
    assert result["status"] == "ok"
    with get_session() as session:
        log = session.query(FetchLog).order_by(FetchLog.id.desc()).first()
        assert "scheduled" in log.sources


def test_save_item_uses_shared_model_and_deduplicates():
    item = {
        "source": "Test", "title": "Shared ORM", "link": "https://example.test/shared-orm",
        "summary": "test", "published_at": None,
    }
    with get_session() as session:
        assert rss.save_item(session, item) == "new"
        assert rss.save_item(session, item) == "duplicate"
