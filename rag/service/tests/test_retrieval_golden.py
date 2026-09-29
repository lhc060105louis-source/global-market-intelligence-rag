from datetime import date, datetime, timezone

from app.models import KnowledgeRecord
from app.retrieval_text import generate_retrieval_text
from conftest import consumer_payload, kol_payload


def make_record(*, target, record_type, source, source_id, payload, business_date=None):
    return KnowledgeRecord(
        id="00000000-0000-0000-0000-000000000001",
        source_system=source,
        source_record_id=source_id,
        record_type=record_type,
        record_mode="snapshot" if business_date else "current",
        business_key="golden-key",
        source_version=3,
        status="active",
        effective_at=datetime(2026, 8, 5, 2, tzinfo=timezone.utc),
        source_updated_at=datetime(2026, 8, 5, 3, tzinfo=timezone.utc),
        business_date=business_date,
        is_mock=False,
        payload_json=payload,
        content_hash="hash",
        target_knowledge_base=target,
    )


def consumer_body():
    return """dimension: journey_sentiment
vehicle_model: Model A
brand: Example Motors
region: EU
journey_stage: ownership
channel: social
language: en
period: 2026-08-04T00:00:00+00:00 to 2026-08-04T23:59:59+00:00
business_date: 2026-08-05
signal_count: 42
emotion_distribution: {"angry":5,"satisfied":20}
result: {"granularity":"daily","negative_ratio":0.25,"neutral_ratio":0.2,"positive_ratio":0.55,"trend_direction":"up"}
trend: up
risk_status: """


def test_c_current_retrieval_golden():
    record = make_record(
        target="c_current", record_type="consumer_journey_sentiment", source="C",
        source_id="consumer-1", payload=consumer_payload(),
    )
    expected = f"""[record_id] {record.id}
[source] C
[record_type] consumer_journey_sentiment
[source_record_id] consumer-1
[source_version] 3
[business_date] 
[is_mock] false

{consumer_body()}"""
    assert generate_retrieval_text(record) == expected


def test_c_history_retrieval_golden():
    record = make_record(
        target="c_history", record_type="consumer_journey_sentiment", source="C",
        source_id="consumer-1", payload=consumer_payload(), business_date=date(2026, 8, 5),
    )
    expected = f"""[record_id] {record.id}
[source] C
[record_type] consumer_journey_sentiment
[source_record_id] consumer-1
[source_version] 3
[business_date] 2026-08-05
[is_mock] false

{consumer_body()}"""
    assert generate_retrieval_text(record) == expected


def test_kol_retrieval_golden():
    record = make_record(
        target="kol", record_type="kol_current_assessment", source="KOL",
        source_id="kol-source-1", payload=kol_payload(),
    )
    expected = f"""[record_id] {record.id}
[source] KOL
[record_type] kol_current_assessment
[source_record_id] kol-source-1
[source_version] 3
[business_date] 
[is_mock] false

kol_id: kol-1
display_name: Creator One
primary_platform: YouTube
audience_regions: ["EU"]
content_categories: ["auto"]
commercial_score: 88.5
commercial_dimensions: {{"reach":90}}
risk_score: 12.0
risk_level: low
risk_tags: []
cooperation_conclusion: recommended
source_version: 3
effective_at: 2026-08-05T02:00:00+00:00"""
    assert generate_retrieval_text(record) == expected
