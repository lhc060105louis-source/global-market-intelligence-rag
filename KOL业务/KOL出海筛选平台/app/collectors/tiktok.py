from __future__ import annotations

import json
import re
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from app.collectors.base import CollectedProfile, CollectionError

TikTokFetchFunc = Callable[[int, int], list[dict[str, Any]]]

DATASET_ROWS_URL = "https://datasets-server.huggingface.co/rows"
DATASET_NAME = "Tikfly/tiktok-top-kol"
MAX_DATASET_ROWS_SCANNED = 250
_FETCH_CACHE: dict[tuple[int, int], list[dict[str, Any]]] = {}

REGION_TO_MARKET = {"GB": "UK", "UK": "UK", "DE": "DE"}
MARKET_TERMS = {
    "UK": (" uk ", "united kingdom", "britain", "british", "england", "london"),
    "DE": (" germany", " german", "deutschland", "deutsch", "berlin", "munich"),
}


def _default_fetch(offset: int, limit: int) -> list[dict[str, Any]]:
    normalized_offset = max(offset, 0)
    normalized_limit = max(limit, 1)
    cache_key = (normalized_offset, normalized_limit)
    query = urlencode(
        {
            "dataset": DATASET_NAME,
            "config": "default",
            "split": "train",
            "offset": normalized_offset,
            "length": normalized_limit,
        }
    )
    request = Request(
        f"{DATASET_ROWS_URL}?{query}",
        headers={"User-Agent": "KOLCollector/1.0"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 429:
            cached = _FETCH_CACHE.get(cache_key)
            if cached is not None:
                return cached
            raise CollectionError("TikTok 数据集接口限流，请稍后重试。") from exc
        raise CollectionError(f"TikTok dataset unavailable: {exc}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise CollectionError(f"TikTok dataset unavailable: {exc}") from exc

    rows = payload.get("rows", [])
    records: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("row"), dict):
            records.append(row["row"])
    _FETCH_CACHE[cache_key] = records
    return records


class TikTokDatasetCollector:
    platform = "tiktok"

    def __init__(self, fetch_func: TikTokFetchFunc | None = None) -> None:
        self.fetch_func = fetch_func or _default_fetch

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
        seen_handles: set[str] = set()
        page_size = min(max(limit * 10, 20), 50)
        max_scanned = MAX_DATASET_ROWS_SCANNED

        for offset in range(0, max_scanned, page_size):
            try:
                rows = self.fetch_func(offset, page_size)
            except CollectionError:
                if profiles:
                    return profiles
                raise
            if not rows:
                break
            for row in rows:
                profile = _row_to_profile(row, keywords, languages, markets)
                if profile is None or not profile.handle:
                    continue
                if profile.handle in seen_handles:
                    continue

                profiles.append(profile)
                seen_handles.add(profile.handle)
                if len(profiles) >= limit:
                    return profiles

        return profiles


def _row_to_profile(
    row: dict[str, Any],
    keywords: list[str],
    languages: list[str],
    markets: list[str],
) -> CollectedProfile | None:
    unique_id = _text(row.get("unique_id")).lstrip("@")
    if not unique_id:
        return None

    country_hint = _country_hint(row, markets)
    if country_hint is None:
        return None

    language_hint = _text(row.get("language")).lower() or None
    allowed_languages = {language.lower() for language in languages}
    if language_hint and allowed_languages and language_hint not in allowed_languages:
        return None

    content_text = " ".join(
        part
        for part in (
            _text(row.get("nickname")),
            unique_id,
            _text(row.get("signature")),
            _text(row.get("region")),
            language_hint or "",
        )
        if part
    )
    if keywords and not any(_term_matches(content_text, keyword) for keyword in keywords):
        return None

    followers = _int_or_none(row.get("follower_count"))
    total_likes = _int_or_none(row.get("total_favorited"))
    video_count = _int_or_none(row.get("aweme_count"))
    engagement_rate = _account_engagement_rate(total_likes, video_count, followers)

    evidence = ["source: Tikfly Hugging Face dataset"]
    if total_likes is not None:
        evidence.append(f"total likes: {total_likes}")
    if video_count is not None:
        evidence.append(f"video count: {video_count}")
    if row.get("verified") is True:
        evidence.append("verified account")

    return CollectedProfile(
        platform="TikTok",
        handle=f"@{unique_id}",
        platform_account_id=_text(row.get("uid")) or unique_id,
        name=_text(row.get("nickname")) or None,
        profile_url=f"https://www.tiktok.com/@{quote(unique_id)}",
        country_hint=country_hint,
        language_hint=language_hint,
        content_text=content_text,
        content_categories=_content_categories(content_text, row),
        followers=followers,
        average_engagement_rate=engagement_rate,
        evidence=evidence,
        source_url="https://huggingface.co/datasets/Tikfly/tiktok-top-kol",
    )


def _country_hint(row: dict[str, Any], markets: list[str]) -> str | None:
    allowed = {market.strip().upper() for market in markets}
    region = _text(row.get("region")).upper()
    mapped = REGION_TO_MARKET.get(region)
    if mapped in allowed:
        return mapped

    haystack = f" {_text(row.get('nickname'))} {_text(row.get('signature'))} ".casefold()
    for market, terms in MARKET_TERMS.items():
        if market in allowed and any(term in haystack for term in terms):
            return market
    return None


def _content_categories(text: str, row: dict[str, Any]) -> str:
    lowered = text.casefold()
    categories = ["tiktok_dataset"]
    if any(_term_matches(lowered, term) for term in ("automotive", "car", "vehicle")):
        categories.append("automotive")
    if any(
        _term_matches(lowered, term)
        for term in ("byd", "nio", "xpeng", "zeekr", "ev", "electric", "battery")
    ):
        categories.append("ev")
    if row.get("verified") is True:
        categories.append("verified")
    return ",".join(categories)


def _account_engagement_rate(
    total_likes: int | None,
    video_count: int | None,
    followers: int | None,
) -> float | None:
    if not total_likes or not video_count or not followers:
        return None
    if video_count <= 0 or followers <= 0:
        return None
    return round((total_likes / video_count) / followers, 4)


def _text(value: object) -> str:
    return str(value or "").strip()


def _int_or_none(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _term_matches(text: str, term: str) -> bool:
    normalized_term = term.strip().casefold()
    if not normalized_term:
        return False
    escaped = re.escape(normalized_term)
    pattern = rf"(?<![a-z0-9]){escaped}(?![a-z0-9])"
    return re.search(pattern, text.casefold()) is not None
