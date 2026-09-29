from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class CollectedProfile:
    platform: str
    handle: str | None
    platform_account_id: str | None
    name: str | None
    profile_url: str | None
    country_hint: str | None
    language_hint: str | None
    content_text: str
    content_categories: str | None
    followers: int | None
    average_engagement_rate: float | None
    evidence: list[str] = field(default_factory=list)
    source_url: str | None = None


class CollectionError(RuntimeError):
    pass


class CollectionCollector(Protocol):
    platform: str

    def collect(
        self,
        *,
        keywords: list[str],
        languages: list[str],
        markets: list[str],
        limit: int,
    ) -> list[CollectedProfile]:
        raise NotImplementedError
