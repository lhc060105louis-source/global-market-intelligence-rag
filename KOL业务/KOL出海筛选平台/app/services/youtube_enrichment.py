from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from app.collectors.base import CollectionError

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"


class YouTubeEnhancementError(RuntimeError):
    pass


def _request(resource: str, api_key: str, **params: object) -> dict[str, Any]:
    failed = False
    try:
        response = httpx.get(
            f"{YOUTUBE_API}/{resource}",
            params={**params, "key": api_key},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("unexpected response")
        return payload
    except Exception:
        failed = True
    if failed:
        raise YouTubeEnhancementError("YouTube enhancement request failed")


def validate_youtube_api_key(api_key: str) -> bool:
    try:
        payload = _request(
            "channels", api_key, part="id", id="UC_x5XG1OV2P6uZZ5FSM9Ttw"
        )
        return bool(payload.get("items"))
    except YouTubeEnhancementError:
        return False


def enhance_youtube_channel(channel_id: str, api_key: str) -> dict[str, int | float]:
    channel_payload = _request(
        "channels", api_key, part="statistics,contentDetails", id=channel_id
    )
    items = channel_payload.get("items") or []
    if not items:
        raise YouTubeEnhancementError("YouTube channel was not found")
    channel = items[0]
    subscribers = int(channel.get("statistics", {}).get("subscriberCount", 0))
    uploads = channel.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
    playlist = _request(
        "playlistItems", api_key, part="contentDetails", playlistId=uploads, maxResults=10
    )
    video_ids = [
        item.get("contentDetails", {}).get("videoId")
        for item in playlist.get("items", [])
    ]
    video_ids = [item for item in video_ids if item]
    stats_payload = _request(
        "videos", api_key, part="statistics", id=",".join(video_ids)
    ) if video_ids else {"items": []}
    stats = [item.get("statistics", {}) for item in stats_payload.get("items", [])]
    average_views = sum(int(item.get("viewCount", 0)) for item in stats) / len(stats) if stats else 0.0
    interactions = sum(
        int(item.get("likeCount", 0)) + int(item.get("commentCount", 0))
        for item in stats
    )
    engagement_rate = interactions / subscribers if subscribers else 0.0
    return {
        "subscriber_count": subscribers,
        "average_views": average_views,
        "err_percent": engagement_rate * 100,
        "average_engagement_rate": engagement_rate,
    }


def enhance_public_youtube_result(
    public_result: dict[str, Any],
    api_key: str,
    log: Callable[[str], None],
) -> dict[str, Any]:
    result = dict(public_result)
    channel_id = str(result.get("channel_id") or result.get("id") or "").strip()
    if not channel_id:
        return result
    try:
        result.update(enhance_youtube_channel(channel_id, api_key))
    except YouTubeEnhancementError:
        log("YouTube API enhancement failed; public results were retained.")
    return result


def youtube_lookup_url(
    *,
    profile_url: str | None,
    handle: str | None,
    platform_account_id: str | None,
) -> str | None:
    url = (profile_url or "").strip()
    if "youtube.com/" in url or "youtu.be/" in url:
        return url

    account_id = (platform_account_id or "").strip()
    if account_id.startswith("UC"):
        return f"https://www.youtube.com/channel/{account_id}"

    normalized_handle = (handle or "").strip()
    if normalized_handle:
        if not normalized_handle.startswith("@"):
            normalized_handle = f"@{normalized_handle}"
        return f"https://www.youtube.com/{normalized_handle}"

    return None


def fetch_youtube_channel_metadata(url: str) -> dict[str, Any]:
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise CollectionError("yt-dlp is not installed") from exc

    options = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
        "playlistend": 1,
        "ignoreerrors": True,
        "noplaylist": False,
    }
    try:
        with YoutubeDL(options) as ydl:
            result = ydl.extract_info(url, download=False) or {}
    except Exception as exc:  # pragma: no cover - network/runtime dependent
        raise CollectionError(str(exc)) from exc

    return result if isinstance(result, dict) else {}
