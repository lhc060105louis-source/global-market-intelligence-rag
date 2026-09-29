from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.collectors.base import CollectedProfile, CollectionError

RedditFetchFunc = Callable[[str, int], list[dict[str, Any]]]

_COUNTRY_TERMS = {
    "UK": (" uk ", "britain", "british", "england", "london"),
    "DE": (" germany", " german", "deutschland", "berlin", "autobahn"),
}
_GERMAN_TERMS = ("deutschland", "deutsch", "germany", "german", "autobahn")
_ENGLISH_TERMS = (" uk ", "britain", "british", "england", "london")


def _default_fetch(keyword: str, limit: int) -> list[dict[str, Any]]:
    query = urlencode({"q": keyword, "limit": max(limit, 1), "sort": "relevance"})
    request = Request(
        f"https://www.reddit.com/search.json?{query}",
        headers={"User-Agent": "KOLCollector/1.0"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 403:
            raise CollectionError("reddit public search is blocked (HTTP 403)") from exc
        raise CollectionError(f"reddit public search failed (HTTP {exc.code})") from exc
    except (OSError, JSONDecodeError) as exc:
        raise CollectionError(str(exc)) from exc

    children = payload.get("data", {}).get("children", [])
    posts: list[dict[str, Any]] = []
    for child in children:
        if isinstance(child, dict) and isinstance(child.get("data"), dict):
            posts.append(child["data"])
    return posts


def _infer_country(text: str, markets: list[str]) -> str | None:
    haystack = f" {text.lower()} "
    allowed_markets = {market.strip().upper() for market in markets}
    for country, terms in _COUNTRY_TERMS.items():
        if country not in allowed_markets:
            continue
        if any(term in haystack for term in terms):
            return country
    return None


def _infer_language(text: str) -> str | None:
    lowered = text.lower()
    if any(term in lowered for term in _GERMAN_TERMS):
        return "de"
    if any(character in lowered for character in ("ä", "ö", "ü", "ß")):
        return "de"
    if any(term in f" {lowered} " for term in _ENGLISH_TERMS):
        return "en"
    return None


class RedditCollector:
    platform = "reddit"

    def __init__(self, fetch_func: RedditFetchFunc | None = None) -> None:
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

        grouped: dict[str, dict[str, Any]] = {}

        for keyword in keywords:
            for post in self.fetch_func(keyword, limit):
                author = post.get("author")
                if not author or author == "[deleted]":
                    continue

                author_key = str(author).strip()
                if not author_key or author_key == "[deleted]":
                    continue

                aggregate = grouped.setdefault(
                    author_key,
                    {
                        "keywords": set(),
                        "titles": [],
                        "selftexts": [],
                        "subreddits": set(),
                        "score": 0,
                        "comments": 0,
                        "posts": 0,
                        "source_url": None,
                    },
                )
                aggregate["keywords"].add(keyword)
                if post.get("title"):
                    aggregate["titles"].append(str(post["title"]).strip())
                if post.get("selftext"):
                    aggregate["selftexts"].append(str(post["selftext"]).strip())
                if post.get("subreddit"):
                    aggregate["subreddits"].add(str(post["subreddit"]).strip())
                aggregate["score"] += int(post.get("score") or 0)
                aggregate["comments"] += int(post.get("num_comments") or 0)
                aggregate["posts"] += 1

                permalink = post.get("permalink")
                if permalink and not aggregate["source_url"]:
                    aggregate["source_url"] = f"https://www.reddit.com{permalink}"

        profiles: list[CollectedProfile] = []
        for author, aggregate in grouped.items():
            content_parts = [
                *aggregate["titles"],
                *aggregate["selftexts"],
                *sorted(aggregate["subreddits"]),
            ]
            content_text = " ".join(part for part in content_parts if part)
            country_hint = _infer_country(content_text, markets)
            total_interactions = aggregate["score"] + aggregate["comments"]
            average_engagement_rate = None
            if total_interactions > 0:
                average_engagement_rate = round(
                    aggregate["comments"] / total_interactions,
                    4,
                )

            evidence = [
                *(f"matched keyword: {keyword}" for keyword in sorted(aggregate["keywords"])),
                f"post count: {aggregate['posts']}",
            ]
            if country_hint:
                evidence.append(f"matched market: {country_hint}")

            profiles.append(
                CollectedProfile(
                    platform="Reddit",
                    handle=f"u/{author}",
                    platform_account_id=author,
                    name=author,
                    profile_url=f"https://www.reddit.com/user/{author}",
                    country_hint=country_hint,
                    language_hint=_infer_language(content_text),
                    content_text=content_text,
                    content_categories="community_discussion,reddit_author",
                    followers=None,
                    average_engagement_rate=average_engagement_rate,
                    evidence=evidence,
                    source_url=aggregate["source_url"],
                )
            )
            if len(profiles) >= limit:
                break

        return profiles
