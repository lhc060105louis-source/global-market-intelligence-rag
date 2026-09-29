from datetime import datetime, timezone

from app.coordination import stable_hash
from app.config import Settings
from app.main import create_app
from app.models import AssociationCandidate, CoordinationCase, CoordinationTask, DomainEvent
from conftest import AUTH, base_envelope, consumer_payload


def post(client, path, body):
    return client.post(path, headers=AUTH, json=body)


def make_event_body(record_id: str = "c-1"):
    return {
        "push_id": "demo-event-1",
        "source_domain": "C",
        "source_record_id": record_id,
        "source_knowledge_record_id": "",
        "event_type": "demo_signal",
        "source_record_version": 1,
        "subject": "Demonstration event",
        "severity": "medium",
        "occurred_at": "2026-08-05T10:00:00+00:00",
        "professional_status": "confirmed",
        "related_record_ids": [],
        "evidence_refs": [],
        "created_by": "c-system",
    }


def seed_record(client):
    response = post(client, "/api/v1/ingestion/c", base_envelope(
        "C", "consumer_journey_sentiment", "c-1", consumer_payload(), push_id="seed-c",
    ))
    assert response.status_code == 201
    return response.json()["record_id"]


def test_domain_event_idempotency_and_candidate_case_flow(client):
    record_id = seed_record(client)
    body = make_event_body()
    body["source_knowledge_record_id"] = record_id
    first = post(client, "/api/v1/domain-events", body)
    assert first.status_code == 201
    repeated = post(client, "/api/v1/domain-events", body)
    assert repeated.status_code == 200
    assert repeated.json()["decision"] == "duplicate"

    suggestion = post(client, "/api/v1/association-suggestions", {
        "source_event_id": first.json()["object_id"],
        "related_record_ids": [],
        "correlation_basis": ["entity"],
        "confidence_score": 0.8,
        "confidence_explanation": "same demo subject",
        "evidence_refs": [],
        "rule_version": "demo-1",
        "submitted_by": "c-system",
    })
    assert suggestion.status_code == 200 or suggestion.status_code == 201
    candidate_id = suggestion.json()["object_id"]
    decision = client.patch(f"/api/v1/association-candidates/{candidate_id}", headers=AUTH, json={
        "status": "accepted", "reason": "demo acceptance", "expected_object_version": 1, "actor_id": "operator",
    })
    assert decision.status_code == 200
    case = post(client, "/api/v1/coordination-cases", {
        "candidate_id": candidate_id, "scenario_type": "demo", "created_by": "operator",
        "execution_mode": "demo", "is_simulated": True,
    })
    assert case.status_code == 200 or case.status_code == 201
    detail = client.get(f"/api/v1/coordination-cases/{case.json()['object_id']}", headers=AUTH)
    assert detail.status_code == 200
    assert detail.json()["case"]["status"] == "triaging"


def test_task_dependency_rejects_unknown_task(client):
    record_id = seed_record(client)
    body = make_event_body()
    body["source_knowledge_record_id"] = record_id
    event = post(client, "/api/v1/domain-events", body).json()
    suggestion = post(client, "/api/v1/association-suggestions", {
        "source_event_id": event["object_id"], "correlation_basis": ["entity"],
        "confidence_score": 0.8, "confidence_explanation": "demo", "rule_version": "demo-1",
        "submitted_by": "c-system",
    }).json()
    candidate_id = suggestion["object_id"]
    client.patch(f"/api/v1/association-candidates/{candidate_id}", headers=AUTH, json={
        "status": "accepted", "reason": "demo", "expected_object_version": 1, "actor_id": "operator",
    })
    case = post(client, "/api/v1/coordination-cases", {"candidate_id": candidate_id, "scenario_type": "demo", "created_by": "operator"}).json()
    response = post(client, f"/api/v1/coordination-cases/{case['object_id']}/tasks", {
        "owner_domain": "C", "task_type": "demo", "depends_on": ["missing-task"],
        "expected_output_type": "demo", "created_by": "operator",
    })
    assert response.status_code == 422


def test_old_source_version_evidence_is_resolved_after_record_update(client):
    old_payload = consumer_payload()
    old_payload["scope_id"] = "scope-history-test"
    update = base_envelope("C", "consumer_journey_sentiment", "c-history-test", old_payload,
                           push_id="seed-history-v1", version=1)
    assert post(client, "/api/v1/ingestion/c", update).status_code == 201
    record_id = post(client, "/api/v1/ingestion/c", update).json()["record_id"]
    update = base_envelope("C", "consumer_journey_sentiment", "c-history-test", old_payload,
                           push_id="seed-c-v2", version=2)
    update["payload"]["result"]["signal_count"] = 99
    assert post(client, "/api/v1/ingestion/c", update).status_code == 200

    old_value = old_payload["result"]
    evidence = {
        "record_id": record_id, "source_version": 1, "field_path": "payload.result",
        "excerpt_hash": stable_hash(old_value), "captured_at": "2026-08-05T10:00:00+00:00",
    }
    event_body = make_event_body("c-history-test")
    event_body.update({
        "push_id": "old-evidence-event", "source_knowledge_record_id": record_id,
        "source_record_version": 2, "evidence_refs": [evidence],
    })
    response = post(client, "/api/v1/domain-events", event_body)
    assert response.status_code == 201


def test_correction_and_retraction_push_ids_are_idempotent(client):
    payload = consumer_payload()
    payload["scope_id"] = "scope-correction-test"
    seeded = post(client, "/api/v1/ingestion/c", base_envelope(
        "C", "consumer_journey_sentiment", "c-correction-test", payload, push_id="seed-correction-test",
    ))
    assert seeded.status_code == 201
    record_id = seeded.json()["record_id"]
    body = make_event_body("c-correction-test")
    body["source_knowledge_record_id"] = record_id
    created = post(client, "/api/v1/domain-events", body).json()
    event_id = created["object_id"]
    correction = {
        **body, "push_id": "correction-1", "expected_event_version": 1,
        "expected_object_version": 1, "change_reason": "clarified subject",
        "subject": "Corrected demonstration event",
    }
    first = post(client, f"/api/v1/domain-events/{event_id}/correct", correction)
    assert first.status_code == 200
    repeated = post(client, f"/api/v1/domain-events/{event_id}/correct", correction)
    assert repeated.status_code == 200
    assert repeated.json()["decision"] == "duplicate"

    retract = {
        "push_id": "retract-1", "expected_event_version": 2,
        "expected_object_version": 2, "reason": "withdraw demo event", "actor_id": "operator",
    }
    first_retract = post(client, f"/api/v1/domain-events/{event_id}/retract", retract)
    assert first_retract.status_code == 200
    repeated_retract = post(client, f"/api/v1/domain-events/{event_id}/retract", retract)
    assert repeated_retract.status_code == 200
    assert repeated_retract.json()["decision"] == "duplicate"


def test_actor_key_is_bound_and_demo_mode_is_explicit(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'actor.db'}", api_key="operator-key", adapter="fake",
        fake_mode="success", demo_mode="off", actor_api_keys={
            "operator-key": "operator", "demo-key": "demo_driver",
        }, auto_sync_on_ingest=False,
    )
    from fastapi.testclient import TestClient
    with TestClient(create_app(settings)) as local_client:
        denied = local_client.get("/api/v1/records", headers={"X-API-Key": "demo-key", "X-Actor-Type": "demo_driver"})
        assert denied.status_code == 403
        forged = local_client.get("/api/v1/records", headers={"X-API-Key": "operator-key", "X-Actor-Type": "demo_driver"})
        assert forged.status_code == 403

    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'actor-on.db'}", api_key="operator-key", adapter="fake",
        fake_mode="success", demo_mode="on", actor_api_keys={"demo-key": "demo_driver"}, auto_sync_on_ingest=False,
    )
    with TestClient(create_app(settings)) as local_client:
        allowed = local_client.get("/api/v1/records", headers={"X-API-Key": "demo-key", "X-Actor-Type": "demo_driver"})
        assert allowed.status_code == 200


def test_simulation_metadata_survives_correction_and_retraction(client):
    payload = consumer_payload()
    payload["scope_id"] = "scope-simulation-metadata"
    seeded = post(client, "/api/v1/ingestion/c", base_envelope(
        "C", "consumer_journey_sentiment", "c-simulation-metadata", payload, push_id="seed-simulation-metadata",
    ))
    record_id = seeded.json()["record_id"]
    body = make_event_body("c-simulation-metadata")
    body.update({"source_knowledge_record_id": record_id, "execution_mode": "demo", "is_simulated": True})
    created = post(client, "/api/v1/domain-events", body)
    assert created.status_code == 201
    event_id = created.json()["object_id"]
    assert created.json()["is_simulated"] is True
    correction = {**body, "push_id": "simulation-correction", "expected_event_version": 1,
                  "expected_object_version": 1, "change_reason": "demo correction"}
    corrected = post(client, f"/api/v1/domain-events/{event_id}/correct", correction)
    assert corrected.status_code == 200
    assert corrected.json()["is_simulated"] is True
    retract = {"push_id": "simulation-retract", "expected_event_version": 2,
               "expected_object_version": 2, "reason": "demo withdrawal", "actor_id": "operator"}
    withdrawn = post(client, f"/api/v1/domain-events/{event_id}/retract", retract)
    assert withdrawn.status_code == 200
    assert withdrawn.json()["revision"]["is_simulated"] is True


def test_complete_coordination_flow_runs_without_human_blocking(client):
    payload = consumer_payload()
    payload["scope_id"] = "scope-complete-flow"
    seeded = post(client, "/api/v1/ingestion/c", base_envelope(
        "C", "consumer_journey_sentiment", "c-complete-flow", payload, push_id="seed-complete-flow",
    ))
    record_id = seeded.json()["record_id"]
    event_body = make_event_body("c-complete-flow")
    event_body["source_knowledge_record_id"] = record_id
    event_body.update({"push_id": "complete-flow-event", "execution_mode": "demo", "is_simulated": True})
    event = post(client, "/api/v1/domain-events", event_body).json()
    candidate = post(client, "/api/v1/association-suggestions", {
        "source_event_id": event["object_id"], "correlation_basis": ["entity"],
        "confidence_score": 0.9, "confidence_explanation": "same simulated entity",
        "rule_version": "demo-flow-1", "submitted_by": "demo-driver",
    }).json()
    candidate_id = candidate["object_id"]
    decided = client.patch(f"/api/v1/association-candidates/{candidate_id}", headers=AUTH, json={
        "status": "accepted", "reason": "demo flow", "expected_object_version": 1, "actor_id": "operator",
    })
    assert decided.status_code == 200
    case = post(client, "/api/v1/coordination-cases", {
        "candidate_id": candidate_id, "scenario_type": "demo-flow", "created_by": "operator",
        "execution_mode": "demo", "is_simulated": True,
    }).json()
    case_id = case["object_id"]
    impact = post(client, "/api/v1/domain-impacts", {
        "case_id": case_id, "domain": "C", "assessment_status": "received",
        "impact_summary": "simulated consumer impact", "assessed_by": "demo-driver", "is_simulated": True,
    })
    assert impact.status_code == 200
    task = post(client, f"/api/v1/coordination-cases/{case_id}/tasks", {
        "owner_domain": "C", "task_type": "demo-response", "expected_output_type": "response",
        "execution_mode": "demo", "created_by": "operator",
    }).json()
    task_id = task["object_id"]
    for expected_version, status in ((1, "assigned"), (2, "accepted"), (3, "in_progress")):
        transitioned = client.patch(f"/api/v1/coordination-tasks/{task_id}", headers=AUTH, json={
            "status": status, "expected_object_version": expected_version, "actor_id": "operator", "reason": "demo flow",
        })
        assert transitioned.status_code == 200
    result = post(client, "/api/v1/execution-results", {
        "result_push_id": "complete-flow-result-1", "task_id": task_id, "result_payload": {"done": True}, "result_status": "auto_verified_simulation",
        "execution_mode": "demo", "actor_type": "system", "actor_id": "demo-rule-engine",
        "is_simulated": True, "verification_mode": "simulator", "verification_rule_version": "demo-1",
    })
    assert result.status_code == 200
    repeated_result = post(client, "/api/v1/execution-results", {
        "result_push_id": "complete-flow-result-1", "task_id": task_id, "result_payload": {"done": True}, "result_status": "auto_verified_simulation",
        "execution_mode": "demo", "actor_type": "system", "actor_id": "demo-rule-engine",
        "is_simulated": True, "verification_mode": "simulator", "verification_rule_version": "demo-1",
    })
    assert repeated_result.status_code == 200
    assert repeated_result.json()["decision"] == "duplicate"
    assert client.get(f"/api/v1/execution-results?task_id={task_id}", headers=AUTH).json()["items"][0]["result_push_id"] == "complete-flow-result-1"
    completed = client.post(f"/api/v1/coordination-tasks/{task_id}/complete", headers=AUTH)
    assert completed.status_code == 200
    inbox = client.get("/api/v1/coordination-tasks/inbox?owner_domain=C&status=completed", headers=AUTH)
    assert inbox.status_code == 200
    assert any(item["id"] == task_id for item in inbox.json()["items"])
    task_detail = client.get(f"/api/v1/coordination-tasks/{task_id}", headers=AUTH)
    assert task_detail.status_code == 200
    assert len(task_detail.json()["task"]["execution_results"]) == 1
    for expected_version, status in ((1, "confirmed"), (2, "in_progress"), (3, "monitoring")):
        transitioned = client.patch(f"/api/v1/coordination-cases/{case_id}/status", headers=AUTH, json={
            "status": status, "expected_object_version": expected_version, "actor_id": "operator", "reason": "demo flow",
        })
        assert transitioned.status_code == 200
    monitoring = post(client, f"/api/v1/coordination-cases/{case_id}/monitoring", {
        "snapshot_push_id": "complete-flow-monitoring-1", "case_id": case_id, "domain": "C", "metric_payload": {"resolved": True},
        "domain_judgement": "stable", "is_simulated": True, "submitted_by": "demo-driver",
    })
    assert monitoring.status_code == 200
    repeated_monitoring = post(client, f"/api/v1/coordination-cases/{case_id}/monitoring", {
        "snapshot_push_id": "complete-flow-monitoring-1", "case_id": case_id, "domain": "C", "metric_payload": {"resolved": True},
        "domain_judgement": "stable", "is_simulated": True, "submitted_by": "demo-driver",
    })
    assert repeated_monitoring.status_code == 200
    assert repeated_monitoring.json()["decision"] == "duplicate"
    monitoring_items = client.get(f"/api/v1/coordination-cases/{case_id}/monitoring?domain=C", headers=AUTH)
    assert monitoring_items.status_code == 200
    assert len(monitoring_items.json()["items"]) == 1
    close_decision = {
        "decision": "allow", "case_id": case_id, "scenario_type": "demo-flow",
        "rule_version": "demo-close-1", "evaluated_by": "demo-rule-engine", "evidence_refs": [],
    }
    resolved = client.patch(f"/api/v1/coordination-cases/{case_id}/status", headers=AUTH, json={
        "status": "resolved", "expected_object_version": 4, "actor_id": "operator", "reason": "demo resolved",
        "close_decision": close_decision,
    })
    assert resolved.status_code == 200
    retrospective = post(client, f"/api/v1/coordination-cases/{case_id}/retrospectives", {
        "case_id": case_id, "summary": "demo retrospective", "lessons": ["flow works"],
        "generated_by": "demo-driver", "is_simulated": True,
    })
    assert retrospective.status_code == 200
