"""Read completed KOL assessments and publish them to the formal RAG Hub.

The KOL application remains the source of truth.  This module only reads its
loopback API, maps the existing assessment result to the formal ingestion
envelope, and posts that envelope to ``rag/service``.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


JsonObject = dict[str, Any]
GetJson = Callable[[str, float, str], Any]
PostJson = Callable[[str, JsonObject, float, str], JsonObject]


class KOLSourceError(RuntimeError):
    """The KOL source or formal RAG Hub could not be reached."""


class SkipKOLRecord(ValueError):
    """The KOL record is not a completed, evidence-ready assessment."""


@dataclass(frozen=True)
class KOLAdapterConfig:
    kol_base_url: str
    rag_base_url: str
    rag_api_key: str
    timeout_seconds: float = 15.0
    kol_session_token: str = ""
    is_mock: bool = False

    def normalized(self) -> "KOLAdapterConfig":
        if not self.rag_api_key:
            raise KOLSourceError("RAG_HUB_API_KEY is required")
        if self.timeout_seconds <= 0:
            raise KOLSourceError("KOL_SOURCE_TIMEOUT_SECONDS must be greater than zero")
        return KOLAdapterConfig(
            kol_base_url=self.kol_base_url.rstrip("/"),
            rag_base_url=self.rag_base_url.rstrip("/"),
            rag_api_key=self.rag_api_key,
            timeout_seconds=self.timeout_seconds,
            kol_session_token=self.kol_session_token,
            is_mock=self.is_mock,
        )


COUNTRY_ALIASES = {
    "GB": "UK",
    "UK": "UK",
    "UNITED KINGDOM": "UK",
    "英国": "UK",
    "DE": "DE",
    "GERMANY": "DE",
    "DEUTSCHLAND": "DE",
    "德国": "DE",
    "FR": "FR",
    "FRANCE": "FR",
    "法国": "FR",
    "EU": "EU",
    "EUROPEAN UNION": "EU",
    "欧盟": "EU",
    "EU全域": "EU",
}


def normalize_region(value: Any) -> str:
    text = str(value or "").strip()
    return COUNTRY_ALIASES.get(text.upper(), text or "UNKNOWN")


def split_categories(value: Any) -> list[str]:
    candidates = value if isinstance(value, list) else re.split(r"[,，;；/|\n]+", str(value or ""))
    result: list[str] = []
    for candidate in candidates:
        text = str(candidate).strip()
        if text and text not in result:
            result.append(text)
    return result


def cooperation_conclusion(commercial_score: float, risk_score: float) -> str:
    """Reuse the recommendation matrix shown by the KOL platform UI."""

    commercial = "high" if commercial_score >= 80 else "medium" if commercial_score >= 65 else "low"
    risk = "low" if risk_score <= 30 else "medium" if risk_score <= 60 else "high"
    actions = {
        "high:low": "强烈推荐合作，优先推进签约",
        "high:medium": "高价值但需管控风险，合同中加强约束条款",
        "high:high": "高价值但高风险，进入法务复核流程后再决策",
        "medium:low": "稳健合作对象，正常推进",
        "medium:medium": "可考虑合作，关注内容专业度提升",
        "low:high": "不建议合作，直接排除",
    }
    return actions.get(f"{commercial}:{risk}", "综合评估后决策")


def _aware_utc(value: Any, fallback: datetime) -> datetime:
    if not value:
        return fallback
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return fallback
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _final_scores(detail: JsonObject, score_type: str) -> dict[str, float]:
    dimensions: dict[str, float] = {}
    for record in detail.get("score_records") or []:
        if record.get("score_type") != score_type or record.get("final_score") is None:
            continue
        dimensions[str(record.get("dimension") or "unknown")] = float(record["final_score"])
    return dimensions


def _source_url(detail: JsonObject, kol_base_url: str) -> str:
    profile = str(detail.get("profile_url") or "").strip()
    return profile if profile.startswith(("http://", "https://")) else f"{kol_base_url.rstrip('/')}/"


def build_assessment_envelope(
    detail: JsonObject,
    kol_base_url: str,
    *,
    now: datetime | None = None,
    is_mock: bool = False,
) -> JsonObject:
    if detail.get("deleted_at"):
        raise SkipKOLRecord("record is archived")
    summary = detail.get("score_summary") or {}
    if summary.get("commercial_status") != "ready" or summary.get("risk_status") != "ready":
        raise SkipKOLRecord("commercial and risk assessments must both be ready")
    if summary.get("commercial_score") is None or summary.get("risk_score") is None:
        raise SkipKOLRecord("commercial_score and risk_score are required")
    if not summary.get("risk_level"):
        raise SkipKOLRecord("risk_level is required")
    sync_id = str(detail.get("sync_id") or "").strip()
    if not sync_id:
        raise SkipKOLRecord("stable sync_id is required")

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    updated_at = max(
        _aware_utc(detail.get("assessment_updated_at"), current),
        _aware_utc(detail.get("workflow_updated_at"), current),
    )
    commercial_score = float(summary["commercial_score"])
    risk_score = float(summary["risk_score"])
    payload: JsonObject = {
        "kol_id": sync_id,
        "display_name": str(
            detail.get("name") or detail.get("handle") or detail.get("platform_account_id") or sync_id
        ).strip(),
        "primary_platform": str(detail.get("platform") or "UNKNOWN").strip(),
        "content_categories": split_categories(detail.get("content_categories")),
        "audience_regions": [normalize_region(detail.get("country"))],
        "commercial_score": commercial_score,
        "commercial_dimensions": _final_scores(detail, "commercial"),
        "risk_score": risk_score,
        "risk_level": str(summary["risk_level"]),
        "risk_tags": [str(flag).strip() for flag in detail.get("flags") or [] if str(flag).strip()],
        "cooperation_conclusion": cooperation_conclusion(commercial_score, risk_score),
    }
    source_record_id = f"kol:{sync_id}:assessment"
    version = max(int(detail.get("version") or 1), 1)
    push_seed = json.dumps(
        {
            "source_record_id": source_record_id,
            "source_version": version,
            "is_mock": is_mock,
            "payload": payload,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "source_system": "KOL",
        "source_record_id": source_record_id,
        "record_type": "kol_current_assessment",
        "event_type": "update_current",
        "source_version": version,
        "effective_at": updated_at.isoformat(),
        "source_updated_at": updated_at.isoformat(),
        "source_url": _source_url(detail, kol_base_url),
        "push_id": "kol-" + hashlib.sha256(push_seed.encode("utf-8")).hexdigest(),
        "is_mock": is_mock,
        "payload": payload,
    }


def _get_json(url: str, timeout: float, session_token: str = "") -> Any:
    headers = {"Accept": "application/json"}
    if session_token:
        headers["X-KOL-Session"] = session_token
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise KOLSourceError(f"KOL source rejected the request: HTTP {exc.code}: {body}") from exc
    except (URLError, TimeoutError) as exc:
        raise KOLSourceError(f"KOL source is unavailable: {exc}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KOLSourceError("KOL source returned invalid JSON") from exc


def _post_json(url: str, body: JsonObject, timeout: float, api_key: str) -> JsonObject:
    request = Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")[:500]
        raise KOLSourceError(f"RAG Hub rejected KOL data: HTTP {exc.code}: {response_body}") from exc
    except (URLError, TimeoutError) as exc:
        raise KOLSourceError(f"RAG Hub is unavailable: {exc}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KOLSourceError("RAG Hub returned invalid JSON") from exc


def sync_kol_assessments(
    config: KOLAdapterConfig,
    *,
    dry_run: bool = False,
    get_json: GetJson | None = None,
    post_json: PostJson | None = None,
) -> JsonObject:
    config = config.normalized()
    get_json = get_json or _get_json
    post_json = post_json or _post_json
    rows = get_json(f"{config.kol_base_url}/kols", config.timeout_seconds, config.kol_session_token)
    if not isinstance(rows, list):
        raise KOLSourceError("KOL /kols response must be a JSON list")

    report: JsonObject = {
        "source_count": len(rows),
        "ready_count": 0,
        "pushed_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "dry_run": dry_run,
        "items": [],
    }
    for row in rows:
        kol_id = row.get("id") if isinstance(row, dict) else None
        if kol_id is None:
            report["failed_count"] += 1
            report["items"].append({"kol_id": None, "status": "failed", "reason": "numeric id is missing"})
            continue
        try:
            detail_url = urljoin(f"{config.kol_base_url}/", f"kols/{kol_id}")
            detail = get_json(detail_url, config.timeout_seconds, config.kol_session_token)
            if not isinstance(detail, dict):
                raise KOLSourceError("KOL detail response must be a JSON object")
            envelope = build_assessment_envelope(
                detail,
                config.kol_base_url,
                is_mock=config.is_mock,
            )
            report["ready_count"] += 1
            if dry_run:
                report["items"].append({
                    "kol_id": envelope["payload"]["kol_id"],
                    "status": "ready",
                    "record_type": envelope["record_type"],
                    "is_mock": envelope["is_mock"],
                })
                continue
            response = post_json(
                f"{config.rag_base_url}/api/v1/ingestion/kol",
                envelope,
                config.timeout_seconds,
                config.rag_api_key,
            )
            report["pushed_count"] += 1
            report["items"].append({
                "kol_id": envelope["payload"]["kol_id"],
                "status": "pushed",
                "is_mock": envelope["is_mock"],
                "rag_record_id": response.get("record_id"),
                "decision": response.get("decision"),
                "sync_status": response.get("sync_status"),
            })
        except SkipKOLRecord as exc:
            report["skipped_count"] += 1
            report["items"].append({"kol_id": kol_id, "status": "skipped", "reason": str(exc)})
        except KOLSourceError as exc:
            report["failed_count"] += 1
            report["items"].append({"kol_id": kol_id, "status": "failed", "reason": str(exc)})
    return report
