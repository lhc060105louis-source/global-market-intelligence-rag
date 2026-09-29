from __future__ import annotations

import re
from typing import Any, Callable

from app.collectors.base import CollectedProfile, CollectionError
from app.market import normalize_market

YouTubeSearchFunc = Callable[[str, int], list[dict[str, Any]]]

_COUNTRY_TERMS = {
    "GB": (" uk ", "britain", "british", "england", "london"),
    "FR": ("france", "french", "paris", "français", "française"),
    "DE": (" germany", " german", "deutschland", "berlin", "autobahn"),
}
_GERMAN_TERMS = ("deutschland", "deutsch", "germany", "german", "autobahn")
_ENGLISH_TERMS = (" uk ", "britain", "british", "england", "london", "review")
_FRENCH_TERMS = ("france", "french", "paris", "français", "française", "essai", "voiture")


def _infer_country(text: str, markets: list[str]) -> str | None:
    haystack = f" {text.lower()} "
    allowed_markets = {normalize_market(market) for market in markets}
    for country, terms in _COUNTRY_TERMS.items():
        if country not in allowed_markets:
            continue
        if any(term in haystack for term in terms):
            return country
    return None


def _infer_language(text: str) -> str | None:
    lowered = text.lower()
    if any(term in lowered for term in _FRENCH_TERMS):
        return "fr"
    if any(term in lowered for term in _GERMAN_TERMS):
        return "de"
    if any(character in lowered for character in ("ä", "ö", "ü", "ß")):
        return "de"
    if any(term in f" {lowered} " for term in _ENGLISH_TERMS):
        return "en"
    return None


def _content_categories(text: str) -> str:
    lowered = text.lower()
    categories = ["youtube_channel"]
    has_ev_or_brand = any(
        _term_matches(lowered, term)
        for term in ("ev", "electric", "battery", "byd", "nio", "xpeng")
    )
    has_vehicle_term = any(
        _term_matches(lowered, term)
        for term in ("automotive", "car", "vehicle", "road test", "test drive")
    )
    has_review_context = any(
        _term_matches(lowered, term) for term in ("review", "road test", "test drive")
    )
    if has_ev_or_brand or has_vehicle_term:
        categories.append("automotive")
    if has_ev_or_brand:
        categories.append("ev")
    if has_review_context and (has_ev_or_brand or has_vehicle_term):
        categories.append("car_review")
    return ",".join(categories)


def _term_matches(text: str, term: str) -> bool:
    escaped = re.escape(term.lower())
    pattern = rf"(?<![a-z0-9]){escaped}(?![a-z0-9])"
    return re.search(pattern, text) is not None


def _engagement_rate(item: dict[str, Any]) -> float | None:
    views = item.get("view_count")
    if not isinstance(views, (int, float)) or views <= 0:
        return None
    likes = item.get("like_count") or 0
    comments = item.get("comment_count") or 0
    return round((likes + comments) / views, 4)


def _default_search(keyword: str, limit: int) -> list[dict[str, Any]]:
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise CollectionError("yt-dlp is not installed") from exc

    query = f"ytsearch{max(limit, 1)}:{keyword}"
    options = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
        "ignoreerrors": True,
        "noplaylist": True,
    }
    try:
        with YoutubeDL(options) as ydl:
            result = ydl.extract_info(query, download=False) or {}
    except Exception as exc:  # pragma: no cover - network/runtime dependent
        raise CollectionError(str(exc)) from exc

    entries = result.get("entries")
    if isinstance(entries, list):
        return [entry for entry in entries if isinstance(entry, dict)]
    return []


class YouTubeCollector:
    platform = "youtube"

    def __init__(self, search_func: YouTubeSearchFunc | None = None) -> None:
        self.search_func = search_func or _default_search

    def collect(
        self,
        *,
        keywords: list[str],
        languages: list[str],
        markets: list[str],
        limit: int,
    ) -> list[CollectedProfile]:
        if limit <= 0:
            return []

        profiles: list[CollectedProfile] = []
        seen_accounts: set[str] = set()

        for keyword in keywords:
            for item in self.search_func(keyword, limit):
                channel_id = item.get("channel_id")
                handle = item.get("uploader_id")
                profile_url = item.get("channel_url")
                dedupe_key = str(
                    channel_id or handle or profile_url or item.get("webpage_url") or ""
                ).strip()
                if not dedupe_key or dedupe_key in seen_accounts:
                    continue

                title = str(item.get("title") or "").strip()
                description = str(item.get("description") or "").strip()
                channel = str(item.get("channel") or "").strip()
                content_text = " ".join(part for part in (title, description, channel) if part)
                country_hint = _infer_country(content_text, markets)
                evidence = [f"matched keyword: {keyword}"]
                if country_hint:
                    evidence.append(f"matched market: {country_hint}")

                profiles.append(
                    CollectedProfile(
                        platform="YouTube",
                        handle=str(handle).strip() if handle else None,
                        platform_account_id=str(channel_id).strip() if channel_id else None,
                        name=channel or None,
                        profile_url=str(profile_url).strip() if profile_url else None,
                        country_hint=country_hint,
                        language_hint=_infer_language(content_text),
                        content_text=content_text,
                        content_categories=_content_categories(content_text),
                        followers=item.get("channel_follower_count"),
                        average_engagement_rate=_engagement_rate(item),
                        evidence=evidence,
                        source_url=str(item.get("webpage_url")).strip()
                        if item.get("webpage_url")
                        else None,
                    )
                )
                seen_accounts.add(dedupe_key)
                if len(profiles) >= limit:
                    return profiles

        return profiles
