"""Read real analysis_results for overview, six-dimensional insight, and crisis monitoring."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from source_pipeline import DEFAULT_DB_PATH, connect


NEGATIVE_LABEL_MARKERS = ("negative", "complaint")
HIGH_RISK_LABEL_MARKERS = ("high", "strongly_negative")
SIX_DIMENSIONS = {
    "journey_sentiment_curve": "Customer Journey Sentiment Curve",
    "nps_prediction": "NPS Estimate",
    "complaint_ranking": "Top Complaint Topics",
    "brand_attitude": "Brand Sentiment",
    "recall_warning": "Recall Alert",
    "rights_risk": "Consumer Rights Risk",
}


def is_negative(label: str) -> bool:
    lower = str(label or "").lower()
    return any(marker.lower() in lower for marker in NEGATIVE_LABEL_MARKERS)


def is_high_risk(event: dict[str, Any]) -> bool:
    label = str(event.get("sentiment_label") or "")
    lower = label.lower()
    if any(marker.lower() in lower for marker in HIGH_RISK_LABEL_MARKERS):
        return True
    return bool(event.get("recall_keyword_hit") or event.get("rights_keyword_hit") or event.get("risk_keywords"))


def add_filter(clauses: list[str], params: list[Any], field: str, value: Any) -> None:
    if value in (None, ""):
        return
    clauses.append(f"{field} = ?")
    params.append(value)


def analysis_events(
    conn,
    *,
    job_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    brand: str | None = None,
    model: str | None = None,
    region: str | None = None,
    channel: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    clauses = ["1 = 1"]
    params: list[Any] = []
    add_filter(clauses, params, "r.job_id", job_id)
    add_filter(clauses, params, "c.channel", channel)
    if start_date:
        clauses.append("a.published_date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("a.published_date <= ?")
        params.append(end_date)
    sql = f"""
        SELECT
            r.job_id,
            a.source,
            a.source_id,
            a.sentiment_label,
            a.published_date,
            a.result_json,
            a.analyzed_at
        FROM analysis_results a
        JOIN cleaned_items c ON c.id = a.cleaned_item_id
        JOIN raw_items r ON r.id = c.raw_item_id
        WHERE {' AND '.join(clauses)}
        ORDER BY a.id DESC
    """
    if limit:
        sql += " LIMIT ?"
        params.append(limit)

    events: list[dict[str, Any]] = []
    for row in conn.execute(sql, params):
        try:
            event = json.loads(row["result_json"] or "{}")
        except json.JSONDecodeError:
            event = {}
        if brand and str(event.get("brand") or "") != brand:
            continue
        if model and str(event.get("model") or "") != model:
            continue
        if region and str(event.get("region") or "") != region:
            continue
        event.setdefault("job_id", row["job_id"])
        event.setdefault("source", row["source"])
        event.setdefault("source_id", row["source_id"])
        event.setdefault("sentiment_label", row["sentiment_label"])
        event.setdefault("published_date", row["published_date"])
        event.setdefault("analyzed_at", row["analyzed_at"])
        events.append(event)
    return events


def top_counter(events: list[dict[str, Any]], field: str, limit: int = 8) -> list[dict[str, Any]]:
    counter = Counter(str(event.get(field) or "UNKNOWN") for event in events)
    return [{"name": key, "count": value} for key, value in counter.most_common(limit)]


def topic_names(event: dict[str, Any]) -> list[str]:
    topics = event.get("topics")
    if not isinstance(topics, list):
        return []
    names = []
    for item in topics:
        if isinstance(item, dict):
            names.append(str(item.get("name") or item.get("topic_id") or "unknown"))
    return names


def build_overview(events: list[dict[str, Any]]) -> dict[str, Any]:
    sentiment = Counter(str(event.get("sentiment_label") or "unknown") for event in events)
    high_risk = [event for event in events if is_high_risk(event)]
    topic_counter: Counter[str] = Counter()
    for event in events:
        topic_counter.update(topic_names(event))
    negative_count = sum(count for label, count in sentiment.items() if is_negative(label))
    dominant_sentiment = sentiment.most_common(1)[0][0] if sentiment else "None"
    top_complaint = topic_counter.most_common(1)[0] if topic_counter else ("None", 0)
    return {
        "total_results": len(events),
        "valid_signal_count": len(events),
        "analysis_completed_count": len(events),
        "high_risk_count": len(high_risk),
        "sentiment_distribution": dict(sentiment),
        "top_complaints": [{"name": key, "count": value} for key, value in topic_counter.most_common(8)],
        "top_models": top_counter(events, "model"),
        "top_regions": top_counter(events, "region"),
        "top_channels": top_counter(events, "channel"),
        "latest_high_risk_originals": traceable_events(high_risk, limit=10),
        "suggested_actions": suggested_actions(high_risk),
        "key_findings": {
            "dominant_sentiment": dominant_sentiment,
            "negative_count": negative_count,
            "negative_ratio": round(negative_count / len(events) * 100) if events else 0,
            "top_complaint": {"name": top_complaint[0], "count": top_complaint[1]},
            "top_model": top_counter(events, "model", limit=1)[0] if events else {"name": "None", "count": 0},
        },
    }


def build_six_dimensions(events: list[dict[str, Any]]) -> dict[str, Any]:
    from six_dimension_service import build_bucket_six_dimensions, combine_bucket_views

    return combine_bucket_views(build_bucket_six_dimensions(events))


def traceable_events(events: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    rows = []
    for event in events[:limit]:
        rows.append(
            {
                "job_id": event.get("job_id"),
                "source_id": event.get("source_id"),
                "source": event.get("source"),
                "source_url": event.get("source_url", ""),
                "published_at": event.get("published_at") or event.get("published_date"),
                "channel": event.get("channel"),
                "text": event.get("text", ""),
                "sentiment_label": event.get("sentiment_label"),
                "risk_keywords": event.get("risk_keywords", []),
                "brand": event.get("brand"),
                "model": event.get("model"),
                "region": event.get("region"),
            }
        )
    return rows


def suggested_actions(high_risk_events: list[dict[str, Any]]) -> list[str]:
    actions = []
    if any(event.get("recall_keyword_hit") for event in high_risk_events):
        actions.append("Review recall-related complaints and verify affected model batches.")
    if any(event.get("rights_keyword_hit") for event in high_risk_events):
        actions.append("Escalate consumer-rights complaints to legal and after-sales teams.")
    if high_risk_events:
        actions.append("Prioritize source tracebacks for the newest high-risk originals.")
    return actions


def build_crisis_monitoring(events: list[dict[str, Any]]) -> dict[str, Any]:
    high_risk = [event for event in events if is_high_risk(event)]
    by_date: dict[str, Counter[str]] = defaultdict(Counter)
    for event in events:
        date = str(event.get("published_date") or "unknown")
        by_date[date]["negative" if is_negative(str(event.get("sentiment_label") or "")) else "other"] += 1
        if is_high_risk(event):
            by_date[date]["high_risk"] += 1
    negative_count = sum(1 for event in events if is_negative(str(event.get("sentiment_label") or "")))
    recall_events = [event for event in high_risk if event.get("recall_keyword_hit")]
    rights_events = [event for event in high_risk if event.get("rights_keyword_hit")]
    negative_ratio = round(negative_count / len(events) * 100) if events else 0
    if high_risk:
        risk_level = "alert"
        risk_title = "High-Risk Signals Detected"
        risk_reason = f"Found {len(high_risk)} high-risk records. Review the original feedback first."
    elif negative_ratio >= 30:
        risk_level = "watch"
        risk_title = "Elevated Negative Feedback"
        risk_reason = f"Negative feedback accounts for {negative_ratio}%. Monitor the trend."
    else:
        risk_level = "normal"
        risk_title = "No Current Crisis Signals"
        risk_reason = "No high-risk, recall, or consumer-rights signals were found, and negative feedback remains within the usual range."
    daily_trend = [
        {
            "date": date,
            "total": sum(counter.get(key, 0) for key in ("negative", "other")),
            "negative": counter.get("negative", 0),
            "high_risk": counter.get("high_risk", 0),
        }
        for date, counter in sorted(by_date.items())
    ]
    return {
        "risk_level": risk_level,
        "risk_title": risk_title,
        "risk_reason": risk_reason,
        "summary": {
            "total": len(events),
            "negative_count": negative_count,
            "negative_ratio": negative_ratio,
            "high_risk_count": len(high_risk),
            "recall_count": len(recall_events),
            "rights_count": len(rights_events),
        },
        "daily_trend": daily_trend,
        "negative_trend": {date: dict(counter) for date, counter in sorted(by_date.items())},
        "active_recall_alerts": traceable_events(recall_events, limit=20),
        "active_rights_alerts": traceable_events(rights_events, limit=20),
        "alert_timeline": [
            {"date": date, **dict(counter)}
            for date, counter in sorted(by_date.items())
            if counter.get("high_risk")
        ],
        "high_risk_originals": traceable_events(high_risk, limit=20),
    }


def build_insight_payload(conn, **filters: Any) -> dict[str, Any]:
    events = analysis_events(conn, **filters)
    return {
        "filters": filters,
        "overview": build_overview(events),
        "six_dimensions": build_six_dimensions(events),
        "crisis_monitoring": build_crisis_monitoring(events),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read real VOC analysis results for downstream insight pages.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--job-id", type=int)
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--brand")
    parser.add_argument("--model")
    parser.add_argument("--region")
    parser.add_argument("--channel")
    parser.add_argument("--limit", type=int)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    conn = connect(args.db)
    try:
        payload = build_insight_payload(
            conn,
            job_id=args.job_id,
            start_date=args.start_date,
            end_date=args.end_date,
            brand=args.brand,
            model=args.model,
            region=args.region,
            channel=args.channel,
            limit=args.limit,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
