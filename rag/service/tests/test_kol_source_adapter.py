from datetime import datetime, timezone

import pytest

from app.kol_source_adapter import (
    KOLAdapterConfig,
    SkipKOLRecord,
    build_assessment_envelope,
    cooperation_conclusion,
    sync_kol_assessments,
)
from conftest import AUTH


def ready_detail():
    return {
        "id": 7,
        "sync_id": "kol-sync-7",
        "version": 3,
        "deleted_at": None,
        "name": "AutoDeutsch",
        "handle": "@AutoDeutsch",
        "profile_url": "https://example.com/creator",
        "platform": "YouTube",
        "country": "GB",
        "content_categories": "Automotive, EV / test drives",
        "score_summary": {
            "commercial_score": 85.0,
            "commercial_status": "ready",
            "risk_score": 25.0,
            "risk_status": "ready",
            "risk_level": "low",
        },
        "score_records": [
            {"score_type": "commercial", "dimension": "audience_fit", "final_score": 90},
            {"score_type": "risk", "dimension": "fake_traffic", "final_score": 10},
        ],
        "flags": ["Ad disclosure is complete"],
        "assessment_updated_at": "2026-08-18T10:00:00",
        "workflow_updated_at": "2026-08-18T11:00:00+00:00",
    }


def test_build_assessment_envelope_uses_formal_contract_and_shared_country():
    body = build_assessment_envelope(
        ready_detail(),
        "http://127.0.0.1:8766",
        now=datetime(2026, 8, 19, tzinfo=timezone.utc),
        is_mock=True,
    )
    assert body["source_system"] == "KOL"
    assert body["record_type"] == "kol_current_assessment"
    assert body["source_version"] == 3
    assert body["is_mock"] is True
    assert body["payload"]["kol_id"] == "kol-sync-7"
    assert body["payload"]["audience_regions"] == ["UK"]
    assert body["payload"]["content_categories"] == ["Automotive", "EV", "test drives"]
    assert body["payload"]["commercial_dimensions"] == {"audience_fit": 90.0}
    assert body["payload"]["cooperation_conclusion"] == "Strong partnership candidate; prioritize contract signing."


def test_incomplete_assessment_is_not_exported():
    detail = ready_detail()
    detail["score_summary"]["risk_status"] = "insufficient"
    with pytest.raises(SkipKOLRecord, match="must both be ready"):
        build_assessment_envelope(detail, "http://127.0.0.1:8766")


def test_recommendation_reuses_kol_ui_matrix():
    assert cooperation_conclusion(72, 45) == "Partnership may be considered; focus on improving content expertise."
    assert cooperation_conclusion(60, 80) == "Partnership not recommended; exclude from consideration."


def test_dry_run_reads_details_without_posting():
    calls = []

    def get_json(url, timeout, token):
        calls.append(url)
        return [{"id": 7}] if url.endswith("/kols") else ready_detail()

    config = KOLAdapterConfig("http://127.0.0.1:8766", "http://127.0.0.1:8001", "test-key")
    report = sync_kol_assessments(config, dry_run=True, get_json=get_json)
    assert report["source_count"] == 1
    assert report["ready_count"] == 1
    assert report["pushed_count"] == 0
    assert report["items"][0]["status"] == "ready"
    assert calls == ["http://127.0.0.1:8766/kols", "http://127.0.0.1:8766/kols/7"]


def test_sync_posts_to_formal_rag_contract():
    posted = []

    def get_json(url, timeout, token):
        return [{"id": 7}] if url.endswith("/kols") else ready_detail()

    def post_json(url, body, timeout, api_key):
        posted.append((url, body, api_key))
        return {"record_id": "rag-kol-7", "decision": "created"}

    config = KOLAdapterConfig("http://127.0.0.1:8766", "http://127.0.0.1:8001", "test-key")
    report = sync_kol_assessments(config, get_json=get_json, post_json=post_json)
    assert report["pushed_count"] == 1
    assert posted[0][0].endswith("/api/v1/ingestion/kol")
    assert posted[0][1]["payload"]["kol_id"] == "kol-sync-7"
    assert posted[0][2] == "test-key"


def test_generated_envelope_is_accepted_by_formal_rag_endpoint(client):
    body = build_assessment_envelope(ready_detail(), "http://127.0.0.1:8766")
    response = client.post("/api/v1/ingestion/kol", json=body, headers=AUTH)
    assert response.status_code == 201
    records = client.get(
        "/api/v1/records?source_system=KOL&target_knowledge_base=kol",
        headers=AUTH,
    ).json()
    assert records["total"] == 1
    assert records["items"][0]["payload_json"]["kol_id"] == "kol-sync-7"
