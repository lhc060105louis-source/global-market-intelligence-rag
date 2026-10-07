"""Exercise bounded Agent execution and approval against a real temporary database."""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import risk_investigation
from app.config import Settings
from app.coordination import stable_hash
from app.main import create_app
from app.models import (
    AgentRun, AssociationCandidate, CoordinationAuditEvent, CoordinationCase,
    CoordinationTask, DomainEvent, DomainEventRevision, KnowledgeRecord,
    RagDocumentMapping, RiskEpisode, RiskObject, RiskTrendPoint, utc_now,
)
from conftest import AUTH


BUSINESS_TABLES = (
    DomainEvent, DomainEventRevision, AssociationCandidate, CoordinationCase,
    CoordinationTask, CoordinationAuditEvent,
)


class SearchStub:
    def __init__(self):
        self.calls = []
        self.hits = {}

    def search(self, *, target, **kwargs):
        self.calls.append({"target": target, **kwargs})
        return self.hits.get(target, [])


def draft_for(evidence):
    return {
        "summary": "Review the supplied synthetic risk evidence.",
        "domain_impacts": {"C": "Synthetic consumer signal; impact requires review."},
        "evidence": [item["record_id"] for item in evidence],
        "evidence_gaps": [], "limitations": ["Synthetic test evidence."],
        "tasks": [{"owner_domain": "C", "task_type": "review_risk",
                   "expected_output_type": "assessment", "is_required": True}],
    }


@pytest.fixture
def investigation(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'investigation.db'}",
        api_key="test-key", adapter="maxkb", fake_mode="success",
        actor_api_keys={"test-key": "operator", "consumer-test-key": "C"},
        auto_sync_on_ingest=False,
    )
    app = create_app(settings)
    adapter = SearchStub()
    app.state.adapter = adapter
    state = SimpleNamespace(app=app, settings=settings, adapter=adapter, draft_calls=[])

    # Small local models may emit invalid proposals; the production fallback must recover.
    monkeypatch.setattr(risk_investigation, "_ollama_proposal", lambda *a, **kw: {"tool": "invalid"})

    def generate(settings, context, evidence, timeout):
        state.draft_calls.append({"evidence": evidence, "timeout": timeout})
        return draft_for(evidence)

    monkeypatch.setattr(risk_investigation, "_ollama_draft", generate)
    with TestClient(app, raise_server_exceptions=False) as client:
        state.client = client
        yield state


def add_record(db, *, source_id, target="c_current"):
    now = utc_now()
    payload = {"synthetic": True, "signal": source_id}
    record = KnowledgeRecord(
        source_system="C" if target.startswith("c_") else "B", source_record_id=source_id,
        record_type="synthetic_test", record_mode="current", business_key=source_id,
        source_version=1, status="active", effective_at=now, source_updated_at=now,
        is_mock=True, payload_json=payload, content_hash=stable_hash(payload),
        retrieval_text=f"Synthetic risk evidence {source_id}", target_knowledge_base=target,
    )
    db.add(record)
    db.flush()
    return record


def seed_risk(state, source_count=1):
    with state.app.state.session_factory() as db:
        risk = RiskObject(brand="Synthetic Motors", vehicle_model="Test Model",
                          part="battery", region="EU", risk_type="overheat")
        db.add(risk)
        db.flush()
        now = utc_now()
        episode = RiskEpisode(risk_object_id=risk.id, status="open", started_at=now,
                              current_value=12, threshold=10)
        db.add(episode)
        db.flush()
        ids = []
        for index in range(source_count):
            record = add_record(db, source_id=f"source-{index}")
            ids.append(record.id)
            db.add(RiskTrendPoint(
                episode_id=episode.id, source_record_id=record.id, source_version=1,
                business_time=now + timedelta(seconds=index), hit_value=12, threshold=10,
            ))
        db.commit()
        return risk.id, ids


def start(state, *, source_count=1):
    risk_id, ids = seed_risk(state, source_count)
    response = state.client.post("/api/v1/agent/risk-investigations", headers=AUTH, json={
        "risk_object_id": risk_id, "request_key": f"investigate-{risk_id}",
    })
    assert response.status_code == 202, response.text
    run_id = response.json()["run_id"]
    return get_run(state, run_id), ids


def get_run(state, run_id):
    response = state.client.get(f"/api/v1/agent/risk-investigations/{run_id}", headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()["run"]


def decision(state, run, value="approve", *, headers=AUTH):
    return state.client.post(f"/api/v1/agent/risk-investigations/{run['id']}/decision", headers=headers, json={
        "decision": value, "expected_object_version": run["object_version"],
        "reason": "Synthetic workflow reviewed.",
    })


def business_counts(state):
    with state.app.state.session_factory() as db:
        return {table.__name__: db.scalar(select(func.count()).select_from(table)) for table in BUSINESS_TABLES}


def assert_no_business_records(state):
    assert set(business_counts(state).values()) == {0}


@pytest.mark.parametrize("source_count", [2, 6, 12])
def test_fallback_reserves_synthesis_with_multiple_sources(investigation, source_count):
    run, ids = start(investigation, source_count=source_count)
    assert run["status"] == "awaiting_approval", run
    assert len(investigation.draft_calls) == 1
    assert len(run["tool_trace"]) == 6
    assert run["tool_trace"][-1]["tool"] == "finish_investigation"
    assert {item["record_id"] for item in run["draft"]["evidence"]}.issubset(ids)
    assert len(run["draft"]["evidence"]) == min(source_count, 3)
    searched = {call["target"] for call in investigation.adapter.calls}
    assert len(searched) == max(0, 5 - source_count)
    gaps = run["draft"]["evidence_gaps"]
    for target in sorted(risk_investigation.TARGETS):
        message = (f"{target}: search returned no validated evidence." if target in searched
                   else f"{target}: not searched within the investigation tool budget.")
        assert message in gaps
    assert_no_business_records(investigation)


def test_authenticated_approval_creates_records_once_and_retry_reuses_them(investigation):
    run, _ = start(investigation)
    assert run["status"] == "awaiting_approval"
    assert_no_business_records(investigation)
    unauthenticated = decision(investigation, run, headers={})
    assert unauthenticated.status_code == 401
    forbidden = decision(investigation, run, headers={"X-API-Key": "consumer-test-key"})
    assert forbidden.status_code == 403
    assert_no_business_records(investigation)
    first = decision(investigation, run)
    assert first.status_code == 200, first.text
    approved = first.json()["run"]
    assert approved["status"] == "approved"
    counts = business_counts(investigation)
    assert all(counts[table.__name__] == 1 for table in BUSINESS_TABLES[:-1])
    assert counts["CoordinationAuditEvent"] > 0
    with investigation.app.state.session_factory() as db:
        task = db.scalar(select(CoordinationTask))
        assert task.case_id == approved["case_id"]
        assert task.status == "proposed"
        assert task.execution_mode == "real"
        case = db.get(CoordinationCase, approved["case_id"])
        assert case.trigger_event_ids == [approved["event_id"]]
        assert case.association_candidate_ids == [approved["candidate_id"]]
    # Retry uses the original version as an ordinary network retry would.
    retry = decision(investigation, run)
    assert retry.status_code == 200
    assert retry.json()["run"] == approved
    assert business_counts(investigation) == counts


def test_rejection_and_retry_do_not_create_coordination_records(investigation):
    run, _ = start(investigation)
    rejected = decision(investigation, run, "reject")
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["run"]["status"] == "rejected"
    counts = business_counts(investigation)
    assert all(counts[table.__name__] == 0 for table in BUSINESS_TABLES[:-1])
    retry = decision(investigation, run, "reject")
    assert retry.status_code == 200
    assert business_counts(investigation) == counts
    assert decision(investigation, run).status_code == 409


@pytest.mark.parametrize("change", ["version", "payload", "inactive"])
def test_changed_evidence_makes_approval_stale_without_business_writes(investigation, change):
    run, ids = start(investigation)
    with investigation.app.state.session_factory() as db:
        record = db.get(KnowledgeRecord, ids[0])
        if change == "version":
            record.source_version += 1
        elif change == "payload":
            record.payload_json = {"synthetic": True, "signal": "changed"}
        else:
            record.status = "retracted"
        db.commit()
    response = decision(investigation, run)
    assert response.status_code == 200, response.text
    assert response.json()["run"]["status"] == "stale"
    assert_no_business_records(investigation)


def test_approval_failure_rolls_back_all_writes_and_allows_retry(investigation, monkeypatch):
    run, _ = start(investigation)
    original_audit = risk_investigation.audit

    def failing_audit(db, **kwargs):
        if kwargs["aggregate_type"] == "coordination_task":
            # Event, revision, candidate, case and task have already been flushed.
            assert db.scalar(select(func.count()).select_from(CoordinationTask)) == 1
            raise ValueError("synthetic_approval_failure")
        return original_audit(db, **kwargs)

    monkeypatch.setattr(risk_investigation, "audit", failing_audit)
    failed = decision(investigation, run)
    assert failed.status_code == 422, failed.text
    persisted = get_run(investigation, run["id"])
    assert persisted["status"] == "awaiting_approval"
    assert persisted["object_version"] == run["object_version"]
    assert_no_business_records(investigation)
    monkeypatch.setattr(risk_investigation, "audit", original_audit)
    retried = decision(investigation, run)
    assert retried.status_code == 200
    assert retried.json()["run"]["status"] == "approved"


def test_no_evidence_run_cannot_be_approved(investigation, monkeypatch):
    monkeypatch.setattr(risk_investigation, "_ollama_proposal", lambda *a, **kw: {
        "tool": "finish_investigation", "arguments": {"draft": draft_for([])},
    })
    run, _ = start(investigation)
    assert run["status"] == "no_evidence"
    assert run["draft"] is None
    assert decision(investigation, run).status_code == 409
    assert_no_business_records(investigation)


def test_partial_run_with_upstream_failure_cannot_be_approved(investigation):
    def fail_search(**kwargs):
        raise risk_investigation.MaxKBError("synthetic search failure")

    investigation.adapter.search = fail_search
    run, _ = start(investigation)
    assert run["status"] == "failed"
    assert run["error_code"] == "search_upstream_error"
    assert run["tool_trace"][0]["tool"] == "get_record"
    assert run["draft"] is None
    assert decision(investigation, run).status_code == 409
    assert_no_business_records(investigation)


def test_changed_retrieved_evidence_prevents_approval(investigation):
    with investigation.app.state.session_factory() as db:
        record = add_record(db, source_id="business-evidence", target="b_business")
        record_id = record.id
        db.add(RagDocumentMapping(
            record_id=record.id, target_knowledge_base="b_business", mapped_source_version=1,
            external_document_id="synthetic-business-document", external_is_active=True,
        ))
        db.commit()
    investigation.adapter.hits["b_business"] = [
        {"document_id": "synthetic-business-document", "similarity": 0.9},
        {"document_id": "unmapped-fabricated-document", "similarity": 1.0},
    ]
    run, source_ids = start(investigation)
    assert run["status"] == "awaiting_approval"
    assert {item["record_id"] for item in run["draft"]["evidence"]} == set(source_ids + [record_id])
    assert not any(gap.startswith("b_business:") for gap in run["draft"]["evidence_gaps"])
    with investigation.app.state.session_factory() as db:
        db.get(KnowledgeRecord, record_id).source_version += 1
        db.commit()
    approved = decision(investigation, run)
    assert approved.status_code == 200, approved.text
    assert approved.json()["run"]["status"] == "stale"
    assert_no_business_records(investigation)


def test_final_generation_cannot_persist_after_deadline(investigation, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(risk_investigation.time, "monotonic", lambda: clock[0])

    def late_draft(settings, context, evidence, timeout):
        clock[0] += settings.rag_query_deadline_seconds + 1
        return draft_for(evidence)

    monkeypatch.setattr(risk_investigation, "_ollama_draft", late_draft)
    run, _ = start(investigation)
    assert run["status"] == "failed"
    assert run["error_code"] == "query_deadline_exceeded"
    assert run["draft"] is None
    assert_no_business_records(investigation)


def test_reserved_synthesis_survives_valid_planner_reads(investigation, monkeypatch):
    def valid_read(settings, context, evidence, budget, timeout, **kwargs):
        # A valid planner can keep choosing source reads beyond the fallback's limit.
        known = {item["record_id"] for item in evidence}
        return {"tool": "get_record", "arguments": {
            "record_id": next(item["record_id"] for item in context["sources"] if item["record_id"] not in known),
        }}

    monkeypatch.setattr(risk_investigation, "_ollama_proposal", valid_read)
    run, _ = start(investigation, source_count=6)
    assert run["status"] == "awaiting_approval"
    assert [item["tool"] for item in run["tool_trace"]] == ["get_record"] * 5 + ["finish_investigation"]
    assert len(investigation.draft_calls) == 1
    assert_no_business_records(investigation)


def test_capacity_limit_rejects_run_and_releases_slots(investigation):
    risk_id, ids = seed_risk(investigation)
    with investigation.app.state.session_factory() as db:
        episode = db.scalar(select(RiskEpisode).where(RiskEpisode.risk_object_id == risk_id))
        run = AgentRun(request_key="capacity-test-run", risk_object_id=risk_id,
                       episode_id=episode.id, source_versions_json={ids[0]: 1}, initiated_by="operator")
        db.add(run)
        db.commit()
        run_id = run.id
    slots = risk_investigation._AGENT_SLOTS
    assert slots.acquire(blocking=False)
    assert slots.acquire(blocking=False)
    try:
        risk_investigation.run_risk_investigation(
            run_id, session_factory=investigation.app.state.session_factory,
            adapter=investigation.adapter, settings=investigation.settings,
        )
    finally:
        slots.release()
        slots.release()
    persisted = get_run(investigation, run_id)
    assert persisted["status"] == "failed"
    assert persisted["error_code"] == "agent_capacity_reached"
    assert persisted["tool_trace"] == []
    assert_no_business_records(investigation)
    response = investigation.client.post("/api/v1/agent/risk-investigations", headers=AUTH, json={
        "risk_object_id": risk_id, "request_key": "after-capacity-release",
    })
    assert response.status_code == 202
    assert get_run(investigation, response.json()["run_id"])["status"] == "awaiting_approval"


def test_unread_source_version_change_makes_approval_stale(investigation):
    run, ids = start(investigation, source_count=6)
    assert run["status"] == "awaiting_approval"
    assert ids[0] not in {item["record_id"] for item in run["draft"]["evidence"]}
    with investigation.app.state.session_factory() as db:
        db.get(KnowledgeRecord, ids[0]).source_version += 1
        db.commit()
    response = decision(investigation, run)
    assert response.status_code == 200, response.text
    assert response.json()["run"]["status"] == "stale"
    assert_no_business_records(investigation)


def test_risk_source_snapshot_change_makes_approval_stale(investigation):
    run, _ = start(investigation)
    with investigation.app.state.session_factory() as db:
        db.scalar(select(RiskTrendPoint)).source_version += 1
        db.commit()
    response = decision(investigation, run)
    assert response.status_code == 200
    assert response.json()["run"]["status"] == "stale"
    assert response.json()["run"]["error_code"] == "risk_source_changed"
    assert_no_business_records(investigation)


def test_model_gap_limit_cannot_hide_unsearched_domains(investigation, monkeypatch):
    def full_gap_draft(settings, context, evidence, timeout):
        draft = draft_for(evidence)
        draft["evidence_gaps"] = [f"Model gap {index}" for index in range(20)]
        return draft

    monkeypatch.setattr(risk_investigation, "_ollama_draft", full_gap_draft)
    run, _ = start(investigation, source_count=6)
    assert run["status"] == "awaiting_approval"
    assert len(run["draft"]["evidence_gaps"]) == 20
    for target in risk_investigation.TARGETS:
        assert f"{target}: not searched within the investigation tool budget." in run["draft"]["evidence_gaps"]
    assert_no_business_records(investigation)
