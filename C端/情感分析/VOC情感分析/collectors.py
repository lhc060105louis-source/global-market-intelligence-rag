#!/usr/bin/env python
"""Collectors for raw vehicle user reviews."""

from __future__ import annotations

import html
import json
import os
import re
import socket
import time
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from source_pipeline import guess_language, source_hash


DEFAULT_TIMEOUT_SECONDS = 20
YOUTUBE_API_RETRIES = 3
USER_AGENT = "VOCRealSourceCollector/1.0"
AUTOHOME_SOURCE = "vehicle_user_reviews:autohome_owner_reviews"
YOUTUBE_SOURCE = "vehicle_user_reviews:youtube_vehicle_comments"
AUTOHOME_OWNER_REVIEW_URLS = [
    "https://www.autohome.com.cn/",
]
DEFAULT_YOUTUBE_QUERIES = [
    "Tesla Model Y owner review",
    "BYD Seal owner review",
    "MG4 EV problems",
    "Hyundai Ioniq 5 owner review",
    "NIO EL6 review",
]
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
KOU_BEI_PATTERN = r"\u5171\d+\u7bc7\u53e3\u7891"
MODEL_YEAR_MARKER = "\u6b3e"
SOURCE_PLATFORM_AUTOHOME = "\u6c7d\u8f66\u4e4b\u5bb6\u8f66\u4e3b\u53e3\u7891"
SOURCE_PLATFORM_YOUTUBE = "YouTube vehicle comments"
VEHICLE_BRANDS = ("Tesla", "BYD", "MG", "Hyundai", "NIO", "Polestar", "BMW", "Mercedes", "Kia", "Volkswagen")
VEHICLE_COMMENT_TERMS = (
    "owner",
    "ownership",
    "drive",
    "driving",
    "road trip",
    "range",
    "battery",
    "charge",
    "charging",
    "charger",
    "efficiency",
    "miles",
    "km",
    "brake",
    "braking",
    "suspension",
    "steering",
    "wheel",
    "wheels",
    "tire",
    "tires",
    "tyre",
    "tyres",
    "noise",
    "wind noise",
    "tire noise",
    "tyre noise",
    "seat",
    "seats",
    "space",
    "interior",
    "trunk",
    "boot",
    "software",
    "app",
    "infotainment",
    "service",
    "dealer",
    "warranty",
    "repair",
    "owned",
    "owning",
    "bought",
    "buying",
    "autopilot",
    "phantom braking",
    "heat pump",
)
COMMENT_EXCLUDE_TERMS = (
    "referral",
    "using my link",
    "use my link",
    "save money",
    "discount code",
    "promo code",
    "ts.la/",
)


class LinkTextExtractor(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.current_href = ""
        self.tokens: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            href = dict(attrs).get("href") or ""
            self.current_href = urljoin(self.base_url, href)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a":
            self.current_href = ""

    def handle_data(self, data: str) -> None:
        text = re.sub(r"\s+", " ", data or "").strip()
        if text:
            self.tokens.append((text, self.current_href))


def fetch_text(
    url: str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    retries: int = 0,
) -> str:
    """Fetch text, retrying only explicitly requested transient failures."""
    attempts = max(0, retries) + 1
    for attempt in range(attempts):
        request = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except HTTPError as exc:
            # Client errors (invalid key, quota, permissions, etc.) are not
            # transient and must be surfaced without spending more requests.
            if exc.code < 500 or attempt >= attempts - 1:
                raise
        except (URLError, TimeoutError, socket.timeout):
            if attempt >= attempts - 1:
                raise
        time.sleep(min(2.0, 0.5 * (2**attempt)))
    raise RuntimeError("Unreachable fetch retry state")


def fetch_json(url: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    retries = YOUTUBE_API_RETRIES if url.startswith(YOUTUBE_API_BASE + "/") else 0
    return json.loads(fetch_text(url, timeout=timeout, retries=retries))


def youtube_api_url(endpoint: str, params: dict[str, Any], api_key: str) -> str:
    query = urlencode({**params, "key": api_key})
    return f"{YOUTUBE_API_BASE}/{endpoint}?{query}"


def collect_youtube_vehicle_comments(
    queries: list[str] | None = None,
    limit: int = 50,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """Collect raw vehicle user comments from YouTube videos via YouTube Data API."""
    key = api_key or os.getenv("YOUTUBE_API_KEY", "").strip()
    if not key:
        raise RuntimeError("YOUTUBE_API_KEY is required for YouTube vehicle comment collection.")
    if limit <= 0:
        return []

    search_queries = queries or DEFAULT_YOUTUBE_QUERIES
    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    video_candidates: list[tuple[str, str, str]] = []
    per_query_video_limit = min(10, max(3, (limit + len(search_queries) - 1) // len(search_queries)))

    for query in search_queries:
        search_payload = fetch_json(
            youtube_api_url(
                "search",
                {
                    "part": "snippet",
                    "type": "video",
                    "order": "relevance",
                    "maxResults": per_query_video_limit,
                    "q": query,
                },
                key,
            )
        )
        for item in search_payload.get("items", []):
            video_id = str(item.get("id", {}).get("videoId") or "").strip()
            if not video_id:
                continue
            snippet = item.get("snippet") or {}
            video_title = str(snippet.get("title") or "").strip()
            video_candidates.append((query, video_id, video_title))

    # Fetch each video separately, then round-robin the buckets so one popular
    # comment section cannot consume the whole requested limit.
    comment_buckets: list[list[dict[str, Any]]] = []
    for query, video_id, video_title in video_candidates:
        comment_payload = fetch_json(
            youtube_api_url(
                "commentThreads",
                {
                    "part": "snippet",
                    "videoId": video_id,
                    "maxResults": min(20, max(1, limit)),
                    "order": "relevance",
                    "textFormat": "plainText",
                },
                key,
            )
        )
        bucket: list[dict[str, Any]] = []
        for thread in comment_payload.get("items", []):
            row = youtube_comment_thread_to_row(thread, query, video_id, video_title)
            if not row:
                continue
            source_id = row["source_id"]
            if source_id in seen_ids:
                continue
            seen_ids.add(source_id)
            bucket.append(row)
        if bucket:
            comment_buckets.append(bucket)

    for comment_index in range(limit):
        added_this_round = False
        for bucket in comment_buckets:
            if comment_index >= len(bucket):
                continue
            results.append(bucket[comment_index])
            added_this_round = True
            if len(results) >= limit:
                return results
        if not added_this_round:
            break
    return results


def youtube_comment_thread_to_row(
    thread: dict[str, Any],
    query: str,
    video_id: str,
    video_title: str,
) -> dict[str, Any] | None:
    top_comment = (thread.get("snippet") or {}).get("topLevelComment") or {}
    comment_id = str(top_comment.get("id") or thread.get("id") or "").strip()
    snippet = top_comment.get("snippet") or {}
    text = str(snippet.get("textDisplay") or snippet.get("textOriginal") or "").strip()
    if not comment_id or len(text) < 3:
        return None
    brand, model = infer_vehicle_context(" ".join([query, video_title, text]))
    if not is_vehicle_comment(text, brand, model):
        return None
    return {
        "source": YOUTUBE_SOURCE,
        "source_id": comment_id,
        "channel": "forum",
        "published_at": str(snippet.get("publishedAt") or "unknown"),
        "language": guess_language(text),
        "title": video_title or query,
        "text": text,
        "source_url": f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}",
        "raw": {
            "source_platform": SOURCE_PLATFORM_YOUTUBE,
            "query": query,
            "video_id": video_id,
            "video_title": video_title,
            "author": snippet.get("authorDisplayName") or "",
            "brand": brand,
            "model": model,
            "like_count": snippet.get("likeCount") or 0,
        },
    }


def infer_vehicle_context(text: str) -> tuple[str, str]:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    lower = normalized.lower()
    brand = ""
    for candidate in VEHICLE_BRANDS:
        if re.search(rf"(?<![a-z0-9]){re.escape(candidate.lower())}(?![a-z0-9])", lower):
            brand = candidate
            break
    model_patterns = (
        r"Model\s+[3YSX]",
        r"Seal(?:ion)?(?:\s+\d+)?",
        r"Atto\s+\d+",
        r"MG4(?:\s+EV)?",
        r"Ioniq\s+5",
        r"EL6",
        r"EV6",
        r"ID\.?\s*4",
        r"EX30",
    )
    for pattern in model_patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            model = match.group(0).strip()
            if not brand and model.lower().startswith("mg4"):
                brand = "MG"
            return brand, model
    return brand, ""


def is_vehicle_comment(text: str, brand: str = "", model: str = "") -> bool:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    lower = normalized.lower()
    if any(term in lower for term in COMMENT_EXCLUDE_TERMS):
        return False
    if model and re.search(rf"(?<![a-z0-9]){re.escape(model.lower())}(?![a-z0-9])", lower):
        return True
    return any(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", lower) for term in VEHICLE_COMMENT_TERMS)


def collect_autohome_owner_reviews(
    urls: list[str] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Collect raw vehicle-owner comments from Autohome public owner-review data."""
    review_urls = urls or AUTOHOME_OWNER_REVIEW_URLS
    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for url in review_urls:
        html_text = fetch_text(url)
        for parsed in parse_autohome_next_data_reviews(html_text):
            source_id = parsed["source_id"]
            if source_id in seen_ids:
                continue
            seen_ids.add(source_id)
            results.append(parsed)
            if len(results) >= limit:
                return results

        extractor = LinkTextExtractor(url)
        extractor.feed(html_text)
        for index, (token, _) in enumerate(extractor.tokens):
            if not re.search(KOU_BEI_PATTERN, token):
                continue
            parsed = parse_autohome_review_tokens(extractor.tokens, index)
            if not parsed:
                continue
            source_id = parsed["source_id"]
            if source_id in seen_ids:
                continue
            seen_ids.add(source_id)
            results.append(parsed)
            if len(results) >= limit:
                return results
    return results


def parse_autohome_next_data_reviews(html_text: str) -> list[dict[str, Any]]:
    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(?P<payload>.*?)</script>',
        html_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return []
    try:
        payload = json.loads(html.unescape(match.group("payload")))
    except json.JSONDecodeError:
        return []

    reviews: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    def visit(node: Any, model_hint: str = "") -> None:
        if isinstance(node, dict):
            model = str(node.get("seriesName") or model_hint or "").strip()
            content = str(node.get("content") or "").strip()
            user_name = str(node.get("userName") or "").strip()
            spec_name = str(node.get("specName") or "").strip()
            url = str(node.get("url") or "").strip()
            if content and user_name and (spec_name or model):
                review_id = str(node.get("id") or node.get("koubeiId") or "").strip()
                source_id = review_id or source_hash(AUTOHOME_SOURCE, model, user_name, spec_name, content)
                if source_id not in seen_ids:
                    seen_ids.add(source_id)
                    reviews.append(
                        {
                            "source": AUTOHOME_SOURCE,
                            "source_id": source_id,
                            "channel": "forum",
                            "published_at": "unknown",
                            "language": guess_language(content),
                            "title": " ".join(part for part in (model, spec_name, str(node.get("average") or "")) if part),
                            "text": content,
                            "source_url": url,
                            "raw": {
                                "source_platform": SOURCE_PLATFORM_AUTOHOME,
                                "author": user_name,
                                "model": model,
                                "model_ycode": spec_name,
                                "rating": node.get("average") or "",
                                "source_record": node,
                            },
                        }
                    )
            for value in node.values():
                visit(value, model)
        elif isinstance(node, list):
            for item in node:
                visit(item, model_hint)

    visit(payload)
    return reviews


def parse_autohome_review_tokens(tokens: list[tuple[str, str]], count_index: int) -> dict[str, Any] | None:
    model = previous_autohome_model(tokens, count_index)
    if not model:
        return None

    cursor = count_index + 1
    if cursor < len(tokens) and re.search(KOU_BEI_PATTERN, tokens[cursor][0]):
        cursor += 1
    if cursor >= len(tokens):
        return None

    author = tokens[cursor][0]
    cursor += 1
    spec = ""
    while cursor < len(tokens):
        text = tokens[cursor][0]
        if MODEL_YEAR_MARKER in text or model in text:
            spec = text
            cursor += 1
            break
        cursor += 1

    score = ""
    while cursor < len(tokens):
        text = tokens[cursor][0]
        if re.fullmatch(r"[0-5](?:\.\d{1,2})?", text):
            score = text
            cursor += 1
            break
        cursor += 1

    comment = ""
    source_url = ""
    while cursor < min(len(tokens), count_index + 20):
        text, href = tokens[cursor]
        if len(text) >= 12 and not re.search(r"\u5168\u90e8\u8bc4\u5206|" + KOU_BEI_PATTERN, text):
            comment = text
            source_url = href
            break
        cursor += 1
    if not comment:
        return None

    source_id = source_hash(AUTOHOME_SOURCE, model, author, spec, comment)
    return {
        "source": AUTOHOME_SOURCE,
        "source_id": source_id,
        "channel": "forum",
        "published_at": "unknown",
        "language": guess_language(comment),
        "title": " ".join(part for part in (model, spec, score) if part),
        "text": comment,
        "source_url": source_url,
        "raw": {
            "source_platform": SOURCE_PLATFORM_AUTOHOME,
            "author": author,
            "model": model,
            "model_ycode": spec,
            "rating": score,
        },
    }


def previous_autohome_model(tokens: list[tuple[str, str]], count_index: int) -> str:
    ignored = {
        "\u5168\u90e8\u8bc4\u5206",
        "\u53e3\u7891",
        "\u8bba\u575b",
        "\u56fe\u7247",
        "\u89c6\u9891",
        "\u7ecf\u9500\u5546",
    }
    for text, _ in reversed(tokens[max(0, count_index - 8):count_index]):
        if text in ignored or re.fullmatch(r"[0-5](?:\.\d{1,2})?\u5206?", text):
            continue
        if re.search(r"\u7bc7\u53e3\u7891|\u8bc4\u5206|\u66f4\u591a|\u8fdb\u5165", text):
            continue
        if 1 < len(text) <= 40:
            return text
    return ""
