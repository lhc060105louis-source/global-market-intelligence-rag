import pytest

from app.services.youtube_enrichment import (
    YouTubeEnhancementError,
    enhance_youtube_channel,
    enhance_public_youtube_result,
    validate_youtube_api_key,
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("request failed")

    def json(self):
        return self.payload


def test_validate_key_uses_minimal_channel_request(monkeypatch):
    calls = []

    def fake_get(url, *, params, timeout):
        calls.append((url, params, timeout))
        return FakeResponse({"items": [{"id": "UC_x5XG1OV2P6uZZ5FSM9Ttw"}]})

    monkeypatch.setattr("app.services.youtube_enrichment.httpx.get", fake_get)

    assert validate_youtube_api_key("secret") is True
    assert calls[0][1]["part"] == "id"


def test_enhancement_calculates_recent_video_metrics(monkeypatch):
    responses = iter(
        [
            FakeResponse(
                {
                    "items": [
                        {
                            "id": "UC123",
                            "statistics": {"subscriberCount": "1000"},
                            "contentDetails": {
                                "relatedPlaylists": {"uploads": "UU123"}
                            },
                        }
                    ]
                }
            ),
            FakeResponse(
                {"items": [{"contentDetails": {"videoId": "a"}}, {"contentDetails": {"videoId": "b"}}]}
            ),
            FakeResponse(
                {
                    "items": [
                        {"statistics": {"viewCount": "100", "likeCount": "10", "commentCount": "5"}},
                        {"statistics": {"viewCount": "300", "likeCount": "20", "commentCount": "5"}},
                    ]
                }
            ),
        ]
    )
    monkeypatch.setattr(
        "app.services.youtube_enrichment.httpx.get",
        lambda *args, **kwargs: next(responses),
    )

    result = enhance_youtube_channel("UC123", "secret")

    assert result == {
        "subscriber_count": 1000,
        "average_views": 200.0,
        "err_percent": 4.0,
        "average_engagement_rate": 0.04,
    }


def test_enhancement_failure_does_not_reveal_key(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("request failed for secret-key")

    monkeypatch.setattr("app.services.youtube_enrichment.httpx.get", fail)

    with pytest.raises(YouTubeEnhancementError) as exc_info:
        enhance_youtube_channel("UC123", "secret-key")

    assert "secret-key" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert "secret-key" not in repr(exc_info.value)


def test_enhancement_failure_preserves_public_result_and_logs(monkeypatch):
    public_result = {"channel_id": "UC123", "name": "Public result"}
    logs = []
    monkeypatch.setattr(
        "app.services.youtube_enrichment.enhance_youtube_channel",
        lambda *args: (_ for _ in ()).throw(YouTubeEnhancementError("failed")),
    )

    result = enhance_public_youtube_result(public_result, "secret", logs.append)

    assert result == public_result
    assert result is not public_result
    assert logs == ["YouTube API enhancement failed; public results were retained."]
