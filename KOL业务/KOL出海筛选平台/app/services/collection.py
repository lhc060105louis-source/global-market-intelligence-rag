from dataclasses import dataclass, replace
import re

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.collectors.base import CollectedProfile, CollectionCollector, CollectionError
from app.collectors.youtube import YouTubeCollector
from app.collectors.reddit import RedditCollector
from app.collectors.tiktok import TikTokDatasetCollector
from app.market import normalize_market
from app.identity import find_existing_kol as find_identity_match
from app.models import CollectionJob, CollectionJobLog, Kol, ScoreRecord
from app.schemas import DEFAULT_COLLECTION_KEYWORDS
from app.security import CredentialStore
from app.services.youtube_enrichment import enhance_youtube_channel
from app.services.importer import BASE_FIELDS, refresh_summary

DEFAULT_KEYWORDS = list(DEFAULT_COLLECTION_KEYWORDS)
SUPPORTED_PLATFORMS = {"youtube", "reddit", "tiktok"}
SUPPORTED_LANGUAGES = {"en", "fr", "de"}
SUPPORTED_MARKETS = {"GB", "FR", "DE"}
PLATFORM_LABELS = {
    "youtube": "YouTube",
    "reddit": "Reddit",
    "tiktok": "TikTok",
}

UK_TERMS = {
    "uk",
    "united kingdom",
    "britain",
    "british",
    "england",
    "london",
}
FR_TERMS = {"france", "french", "paris", "français", "française"}
DE_TERMS = {
    "germany",
    "german",
    "deutschland",
    "deutsch",
    "berlin",
    "munich",
}
BRAND_TERMS = {"byd", "nio", "xpeng", "mg electric", "mg", "zeekr"}
TOPIC_TERMS = {
    "automotive",
    "battery",
    "car review",
    "electric",
    "ev",
    "road test",
    "test drive",
    "vehicle",
}
CONTROVERSY_TERMS = {"controversy", "scandal", "fraud", "lawsuit", "backlash"}
COMPETITOR_TERMS = {
    "tesla",
    "volkswagen",
    "vw",
    "bmw",
    "mercedes",
    "audi",
    "hyundai",
    "kia",
}


@dataclass(frozen=True)
class CollectionCounters:
    total_found: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0

    def __add__(self, other: "CollectionCounters") -> "CollectionCounters":
        return CollectionCounters(
            total_found=self.total_found + other.total_found,
            created=self.created + other.created,
            updated=self.updated + other.updated,
            skipped=self.skipped + other.skipped,
            failed=self.failed + other.failed,
        )


def normalize_collection_request(payload: object) -> tuple[list[str], list[str], list[str], list[str]]:
    keywords = _normalized_keywords(_read_value(payload, "keywords")) or DEFAULT_KEYWORDS
    platforms = _normalized_platforms(_read_value(payload, "platforms")) or ["youtube"]
    languages = _normalized_languages(_read_value(payload, "languages")) or sorted(
        SUPPORTED_LANGUAGES
    )
    markets = _normalized_markets(_read_value(payload, "markets")) or sorted(
        SUPPORTED_MARKETS
    )
    return keywords, platforms, languages, markets


def validate_collection_options(
    platforms: list[str],
    languages: list[str],
    markets: list[str],
) -> None:
    unsupported_platforms = sorted(set(platforms) - SUPPORTED_PLATFORMS)
    unsupported_languages = sorted(set(languages) - SUPPORTED_LANGUAGES)
    unsupported_markets = sorted(set(markets) - SUPPORTED_MARKETS)
    if unsupported_platforms:
        raise ValueError(f"unsupported platforms: {', '.join(unsupported_platforms)}")
    if unsupported_languages:
        raise ValueError(f"unsupported languages: {', '.join(unsupported_languages)}")
    if unsupported_markets:
        raise ValueError(f"unsupported markets: {', '.join(unsupported_markets)}")


def infer_market(profile: CollectedProfile, markets: list[str]) -> str | None:
    allowed_markets = [normalize_market(market) for market in markets]
    country_hint = normalize_market(profile.country_hint) if profile.country_hint else None
    if country_hint in allowed_markets:
        return country_hint
    text = _profile_text(profile)
    if "GB" in allowed_markets and any(term_matches(text, term) for term in UK_TERMS):
        return "GB"
    if "FR" in allowed_markets and any(term_matches(text, term) for term in FR_TERMS):
        return "FR"
    if "DE" in allowed_markets and any(term_matches(text, term) for term in DE_TERMS):
        return "DE"
    language_hint = profile.language_hint.strip().lower() if profile.language_hint else None
    if "DE" in allowed_markets and language_hint == "de":
        return "DE"
    if "FR" in allowed_markets and language_hint == "fr":
        return "FR"
    return None


def language_allowed(profile: CollectedProfile, languages: list[str]) -> bool:
    if not languages:
        return True
    if not profile.language_hint:
        return True
    return profile.language_hint.strip().lower() in {item.lower() for item in languages}


def topic_relevance(content_text: str) -> float | None:
    text = (content_text or "").casefold()
    if not text:
        return None

    topic_matches = sum(1 for term in TOPIC_TERMS if term_matches(text, term))
    brand_matches = sum(1 for term in BRAND_TERMS if term_matches(text, term))
    if topic_matches == 0 and brand_matches == 0:
        return None

    score = 50.0
    if any(term_matches(text, term) for term in {"ev", "electric", "battery"}):
        score += 20
    if any(
        term_matches(text, term)
        for term in {"car review", "test drive", "road test"}
    ):
        score += 15
    if brand_matches:
        score += 10
    return min(score, 100.0)


def has_brand_evidence(profile: CollectedProfile) -> bool:
    text = _profile_text(profile)
    return any(term_matches(text, term) for term in BRAND_TERMS)


def audience_fit(profile: CollectedProfile, country: str) -> float:
    country = normalize_market(country)
    text = _profile_text(profile)
    country_terms = {"GB": UK_TERMS, "FR": FR_TERMS, "DE": DE_TERMS}[country]
    score = 60.0
    if any(term_matches(text, term) for term in country_terms):
        score += 20
    if profile.country_hint:
        try:
            if normalize_market(profile.country_hint) == country:
                score += 10
        except ValueError:
            pass
    if profile.language_hint:
        language = profile.language_hint.strip().lower()
        if ((country == "GB" and language == "en") or
                (country == "FR" and language == "fr") or
                (country == "DE" and language == "de")):
            score += 10
    return min(score, 100.0)


def interaction_quality(profile: CollectedProfile) -> float | None:
    rate = profile.average_engagement_rate
    if rate is None:
        return None
    if not 0 <= rate <= 1:
        raise ValueError("average_engagement_rate must be between 0 and 1")
    if rate >= 0.06:
        return 88.0
    if rate >= 0.04:
        return 80.0
    if rate >= 0.025:
        return 72.0
    if rate >= 0.015:
        return 62.0
    return 50.0


def build_auto_scores(
    profile: CollectedProfile,
    country: str,
) -> dict[tuple[str, str], float]:
    scores: dict[tuple[str, str], float] = {}
    relevance = topic_relevance(profile.content_text)
    if relevance is not None:
        scores[("commercial", "content_relevance")] = relevance
        if has_brand_evidence(profile):
            scores[("commercial", "brand_fit")] = min(relevance, 90.0)
    scores[("commercial", "audience_fit")] = audience_fit(profile, country)

    interaction = interaction_quality(profile)
    if interaction is not None:
        scores[("commercial", "interaction_quality")] = interaction

    evidence = _profile_text(profile)
    if any(term_matches(evidence, term) for term in CONTROVERSY_TERMS):
        scores[("risk", "historical_controversy")] = 65.0
    if any(term_matches(evidence, term) for term in COMPETITOR_TERMS):
        scores[("risk", "competitor_conflict")] = 55.0
    return scores


def find_existing_kol(session: Session, profile: CollectedProfile) -> Kol | None:
    return find_identity_match(
        session, platform=normalize_platform_label(profile.platform),
        platform_account_id=profile.platform_account_id,
        profile_url=profile.profile_url, handle=profile.handle,
    )


def normalize_platform_label(platform: str) -> str:
    normalized = platform.strip().lower()
    return PLATFORM_LABELS.get(normalized, platform.strip())


def evidence_text(profile: CollectedProfile) -> str:
    evidence = "；".join(profile.evidence[:4])
    if evidence:
        return f"自动采集：{evidence}"
    return "自动采集：命中汽车出海相关公开内容。"


def searchable_profile_text(profile: CollectedProfile) -> str:
    parts = [
        profile.content_text,
        profile.content_categories,
        profile.country_hint,
        profile.language_hint,
        *profile.evidence,
    ]
    return " ".join(part for part in parts if part).casefold()


def term_matches(text: str, term: str) -> bool:
    escaped = re.escape(term.casefold())
    pattern = rf"(?<![a-z0-9]){escaped}(?![a-z0-9])"
    return re.search(pattern, text) is not None


def upsert_score_records(
    session: Session,
    kol: Kol,
    job_id: int,
    profile: CollectedProfile,
    country: str,
) -> None:
    scores = build_auto_scores(profile, country)
    evidence = evidence_text(profile)
    source = f"collection:{job_id}:{profile.platform.strip().lower()}"

    for (score_type, dimension), auto_score in scores.items():
        record = session.scalar(
            select(ScoreRecord).where(
                ScoreRecord.kol_id == kol.id,
                ScoreRecord.score_type == score_type,
                ScoreRecord.dimension == dimension,
            )
        )
        if record is None:
            record = ScoreRecord(
                kol_id=kol.id,
                score_type=score_type,
                dimension=dimension,
            )
            session.add(record)
        record.auto_score = auto_score
        record.evidence = evidence
        record.source = source


def persist_collected_profiles(
    session: Session,
    job_id: int,
    profiles: list[CollectedProfile],
    markets: list[str],
    languages: list[str],
) -> CollectionCounters:
    normalized_markets = _normalized_markets(markets)
    normalized_languages = _normalized_languages(languages)
    validate_collection_options([], normalized_languages, normalized_markets)

    counters = CollectionCounters(total_found=len(profiles))
    for profile in profiles:
        try:
            with session.begin_nested():
                result = _persist_one_profile(
                    session,
                    job_id,
                    profile,
                    normalized_markets,
                    normalized_languages,
                )
            counters += result
        except (SQLAlchemyError, TypeError, ValueError):
            counters += CollectionCounters(failed=1)

    session.commit()
    return counters


def default_collectors() -> dict[str, CollectionCollector]:
    return {
        "youtube": YouTubeCollector(),
        "reddit": RedditCollector(),
        "tiktok": TikTokDatasetCollector(),
    }


def add_collection_log(
    session: Session,
    job: CollectionJob,
    platform: str | None,
    level: str,
    message: str,
) -> None:
    session.add(
        CollectionJobLog(
            job_id=job.id,
            platform=platform,
            level=level,
            message=message,
        )
    )


def run_collection_job(
    session_factory,
    job_id: int,
    collectors: dict[str, CollectionCollector] | None = None,
    credential_store=None,
) -> None:
    collectors = collectors or default_collectors()
    credential_store = credential_store or CredentialStore()
    with session_factory() as session:
        job = session.get(CollectionJob, job_id)
        if job is None:
            return
        job.status = "running"
        session.commit()

        total = CollectionCounters()
        failed_platforms = 0
        for platform in job.platforms:
            collector = collectors.get(platform)
            if collector is None:
                failed_platforms += 1
                total += CollectionCounters(failed=1)
                add_collection_log(session, job, platform, "error", "平台暂不支持。")
                session.commit()
                continue
            try:
                profiles = collector.collect(
                    keywords=job.keywords,
                    languages=job.languages,
                    markets=job.markets,
                    limit=job.limit_per_platform,
                )
                api_key = None
                if platform == "youtube":
                    try:
                        api_key = credential_store.get_youtube_api_key()
                    except Exception:
                        add_collection_log(
                            session, job, platform, "warning",
                            "YouTube API enhancement unavailable; public results were retained.",
                        )
                if platform == "youtube" and api_key:
                    enhanced_profiles = []
                    for profile in profiles:
                        if not profile.platform_account_id:
                            enhanced_profiles.append(profile)
                            continue
                        try:
                            metrics = enhance_youtube_channel(
                                profile.platform_account_id, api_key
                            )
                            profile = replace(
                                profile,
                                followers=int(metrics["subscriber_count"]),
                                average_engagement_rate=float(
                                    metrics["average_engagement_rate"]
                                ),
                            )
                        except Exception:
                            add_collection_log(
                                session, job, platform, "warning",
                                "YouTube API enhancement failed; public results were retained.",
                            )
                        enhanced_profiles.append(profile)
                    profiles = enhanced_profiles
                counters = persist_collected_profiles(
                    session=session,
                    job_id=job.id,
                    profiles=profiles,
                    markets=job.markets,
                    languages=job.languages,
                )
                total += counters
                add_collection_log(
                    session,
                    job,
                    platform,
                    "info",
                    (
                        f"发现 {counters.total_found} 条，新增 {counters.created} 条，"
                        f"更新 {counters.updated} 条，跳过 {counters.skipped} 条。"
                    ),
                )
                session.commit()
            except CollectionError as exc:
                failed_platforms += 1
                total += CollectionCounters(failed=1)
                add_collection_log(session, job, platform, "error", str(exc))
                session.commit()
            except Exception as exc:
                session.rollback()
                failed_platforms += 1
                total += CollectionCounters(failed=1)
                add_collection_log(
                    session,
                    job,
                    platform,
                    "error",
                    f"采集失败：{exc.__class__.__name__}",
                )
                session.commit()

        job.total_found = total.total_found
        job.created_count = total.created
        job.updated_count = total.updated
        job.skipped_count = total.skipped
        job.failed_count = total.failed
        if failed_platforms == 0:
            job.status = "completed"
        elif failed_platforms < len(job.platforms):
            job.status = "partial_failed"
        else:
            job.status = "failed"
        session.commit()


def _persist_one_profile(
    session: Session,
    job_id: int,
    profile: CollectedProfile,
    normalized_markets: list[str],
    normalized_languages: list[str],
) -> CollectionCounters:
    if not profile.handle and not profile.platform_account_id:
        return CollectionCounters(skipped=1)
    if not language_allowed(profile, normalized_languages):
        return CollectionCounters(skipped=1)

    country = infer_market(profile, normalized_markets)
    if country is None:
        return CollectionCounters(skipped=1)

    kol = find_existing_kol(session, profile)
    is_created = kol is None
    values = {
        "name": profile.name,
        "platform": normalize_platform_label(profile.platform),
        "platform_account_id": profile.platform_account_id,
        "handle": profile.handle,
        "profile_url": profile.profile_url,
        "country": country,
        "language": profile.language_hint.strip().lower() if profile.language_hint else None,
        "content_categories": profile.content_categories,
        "followers": profile.followers,
        "average_engagement_rate": profile.average_engagement_rate,
        "audience_country_ratio": None,
    }
    if kol is None:
        kol = Kol(**{key: values[key] for key in BASE_FIELDS})
        session.add(kol)
        session.flush()
    else:
        for key in BASE_FIELDS:
            value = values[key]
            if value is not None:
                setattr(kol, key, value)

    upsert_score_records(session, kol, job_id, profile, country)
    session.flush()
    refresh_summary(session, kol)

    return CollectionCounters(
        created=1 if is_created else 0,
        updated=0 if is_created else 1,
    )


def _read_value(payload: object, name: str) -> object:
    if isinstance(payload, dict):
        return payload.get(name)
    return getattr(payload, name, None)


def _normalized_platforms(values: object) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    return list(
        dict.fromkeys(
            str(value).strip().lower()
            for value in values
            if str(value).strip()
        )
    )


def _normalized_keywords(values: object) -> list[str]:
    if not values:
        return []
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result


def _normalized_platforms(values: object) -> list[str]:
    if not values:
        return []
    result: list[str] = []
    for value in values:
        text = str(value).strip().lower()
        if text and text not in result:
            result.append(text)
    return result


def _normalized_languages(values: object) -> list[str]:
    if not values:
        return []
    result: list[str] = []
    for value in values:
        text = str(value).strip().lower()
        if text and text not in result:
            result.append(text)
    return result


def _normalized_markets(values: object) -> list[str]:
    if not values:
        return []
    result: list[str] = []
    for value in values:
        text = normalize_market(str(value))
        if text and text not in result:
            result.append(text)
    return result


def _profile_text(profile: CollectedProfile) -> str:
    return searchable_profile_text(profile)
