from copy import deepcopy
import time

import pytest
from sqlalchemy import func, select
from fastapi.testclient import TestClient

import app.ingestion as ingestion_module
from app.config import Settings
from app.main import OllamaModelUnavailable, _answer_is_unusable, _maxkb_error_code, _ollama_evidence_answer, create_app
from app.adapters.maxkb import MaxKBError
from app.models import IngestionEvent, KnowledgeRecord, RagDocumentMapping, RagSyncTask
from app.query import _external_document_id
from app.retrieval_text import encoding_corruption
from app.text_quality import TextQualityError, find_text_quality_issues
from conftest import AUTH, base_envelope, business_payload, consumer_payload, kol_cooperation_payload, kol_payload


def post(client, path, body):
    return client.post(path, headers=AUTH, json=body)


def test_maxkb_hit_uses_parent_document_id_over_chunk_id():
    hit = {"id": "chunk-1", "document_id": "document-1", "similarity": 0.8}
    assert _external_document_id(hit) == "document-1"


def test_encoding_corruption_detection_rejects_mojibake_but_allows_normal_text():
    assert encoding_corruption("品牌：Tesla；风险状态：正常") is False
    assert encoding_corruption("品牌：????????????????") is True
    assert encoding_corruption("品牌：�") is True


def test_text_quality_checks_nested_payload_without_rejecting_normal_question_marks():
    assert find_text_quality_issues({"title": "What?", "items": ["正常文本"]}) == []
    issues = find_text_quality_issues({"result": {"summary": "??????"}})
    assert issues and issues[0].path == "payload.result.summary"
    with pytest.raises(TextQualityError):
        from app.text_quality import validate_text_quality
        validate_text_quality({"summary": "坏\ufffd文本"})


def test_unusable_answer_detects_replacement_and_question_mark_corruption():
    assert _answer_is_unusable("结论：�") is True
    assert _answer_is_unusable("??????????") is True
    assert _answer_is_unusable("根据证据，风险正常。") is False


def test_ingestion_rejects_corrupt_text_before_persisting(client):
    body = base_envelope("C", "consumer_journey_sentiment", "corrupt", consumer_payload(), push_id="corrupt")
    body["payload"]["brand"] = "????????"
    response = post(client, "/api/v1/ingestion/c", body)
    assert response.status_code == 422
    assert response.json()["error_code"] == "text_quality_invalid"
    assert client.get("/api/v1/records", headers=AUTH).json()["total"] == 0


def test_ollama_missing_model_is_actionable(monkeypatch):
    class Response:
        status_code = 404
        text = "model 'missing-model' not found"

        def raise_for_status(self):
            import httpx
            raise httpx.HTTPStatusError("not found", request=None, response=self)

    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: Response())
    settings = Settings(
        database_url="sqlite:///:memory:", api_key="test", adapter="fake", fake_mode="success",
        ollama_text_model="missing-model",
    )
    with pytest.raises(OllamaModelUnavailable, match="missing-model"):
        _ollama_evidence_answer(settings, "问题", "证据")


def test_maxkb_missing_model_is_classified_for_observability():
    assert _maxkb_error_code(MaxKBError("model 'missing-model' not installed")) == "maxkb_model_unavailable"
    assert _maxkb_error_code(MaxKBError("MaxKB HTTP 502: upstream unavailable")) == "maxkb_chat_failed"


def test_ollama_model_config_is_trimmed_and_empty_is_rejected(monkeypatch):
    monkeypatch.setenv("RAG_HUB_OLLAMA_TEXT_MODEL", " qwen2.5:7b ")
    from app.config import get_settings
    assert get_settings().ollama_text_model == "qwen2.5:7b"


def test_query_surfaces_missing_ollama_model_instead_of_silent_empty_answer(client, monkeypatch):
    created = post(
        client,
        "/api/v1/ingestion/c",
        base_envelope("C", "consumer_journey_sentiment", "query-model", consumer_payload(), push_id="query-model"),
    ).json()
    post(client, "/api/v1/maintenance/sync-tasks/process-pending", {"operator": "tester"})
    with client.app.state.session_factory() as db:
        mapping = db.scalar(select(RagDocumentMapping).where(RagDocumentMapping.record_id == created["record_id"]))

    class SearchOnlyAdapter:
        def search(self, *, target, query, top_k, similarity):
            return [{"document_id": mapping.external_document_id, "similarity": 0.9}]

    client.app.state.adapter = SearchOnlyAdapter()
    monkeypatch.setattr(
        "app.main._ollama_evidence_answer",
        lambda *args, **kwargs: (_ for _ in ()).throw(OllamaModelUnavailable("missing-model", "model not found")),
    )
    response = post(client, "/api/v1/query", {"query": "这个车型的趋势如何"})
    assert response.status_code == 503
    assert response.json()["error_code"] == "ollama_model_unavailable"


def test_query_rejects_unreadable_ollama_answer(monkeypatch):
    from app.main import _answer_is_unusable
    assert _answer_is_unusable("???") is True


def test_query_preserves_structured_answer_without_calling_ollama(client, monkeypatch):
    created = post(
        client,
        "/api/v1/ingestion/c",
        base_envelope("C", "consumer_journey_sentiment", "query-structured", consumer_payload(), push_id="query-structured"),
    ).json()
    post(client, "/api/v1/maintenance/sync-tasks/process-pending", {"operator": "tester"})
    with client.app.state.session_factory() as db:
        mapping = db.scalar(select(RagDocumentMapping).where(RagDocumentMapping.record_id == created["record_id"]))

    class SearchOnlyAdapter:
        def search(self, *, target, query, top_k, similarity):
            return [{"document_id": mapping.external_document_id, "similarity": 0.9}]

    client.app.state.adapter = SearchOnlyAdapter()
    monkeypatch.setattr(
        "app.main._ollama_evidence_answer",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("structured query should not call Ollama")),
    )
    response = post(client, "/api/v1/query", {"query": "有哪些品牌"})
    assert response.status_code == 200
    assert response.json()["output"]["综合结论"].startswith("根据当前检索到的有效证据")


def test_health_auth_and_validation(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["database"] == "ok"
    assert "request_id" in health.json()
    assert client.get("/api/v1/records").status_code == 401

    invalid = base_envelope("C", "consumer_journey_sentiment", "c-1", consumer_payload())
    invalid["source_version"] = "1"
    assert post(client, "/api/v1/ingestion/c", invalid).status_code == 422
    invalid["source_version"] = 1
    invalid["effective_at"] = "2026-08-05T10:00:00"
    assert post(client, "/api/v1/ingestion/c", invalid).status_code == 422


def test_three_system_minimum_ingestion(client):
    c = base_envelope("C", "consumer_journey_sentiment", "c-1", consumer_payload(), push_id="c")
    b = base_envelope("B", "business_policy", "entry-1", business_payload(), push_id="b")
    k = base_envelope("KOL", "kol_current_assessment", "kol-source-1", kol_payload(), push_id="k")
    assert post(client, "/api/v1/ingestion/c", c).status_code == 201
    assert post(client, "/api/v1/ingestion/b", b).status_code == 201
    assert post(client, "/api/v1/ingestion/kol", k).status_code == 201
    records = client.get("/api/v1/records", headers=AUTH).json()
    assert records["total"] == 3
    assert {item["target_knowledge_base"] for item in records["items"]} == {"c_current", "b_business", "kol"}


def test_record_event_and_sync_task_roll_back_together(client, monkeypatch):
    def fail_retrieval_text(_):
        raise RuntimeError("injected retrieval failure")

    monkeypatch.setattr(ingestion_module, "generate_retrieval_text", fail_retrieval_text)
    body = base_envelope("C", "consumer_journey_sentiment", "rollback", consumer_payload(), push_id="rollback")
    with pytest.raises(RuntimeError, match="injected retrieval failure"):
        post(client, "/api/v1/ingestion/c", body)
    with client.app.state.session_factory() as db:
        assert db.scalar(select(func.count(KnowledgeRecord.id))) == 0
        assert db.scalar(select(func.count(IngestionEvent.id))) == 0
        assert db.scalar(select(func.count(RagSyncTask.id))) == 0


@pytest.mark.parametrize("record_type,dimension", [
    ("consumer_journey_sentiment", "journey_sentiment"),
    ("consumer_nps_prediction", "nps_prediction"),
    ("consumer_key_complaints", "key_complaints"),
    ("consumer_brand_attitude", "brand_attitude"),
    ("consumer_recall_risk", "recall_risk"),
    ("consumer_legal_risk", "legal_risk"),
])
def test_all_consumer_result_contracts(client, record_type, dimension):
    payload = consumer_payload(dimension)
    payload["scope_id"] = f"scope-{dimension}"
    body = base_envelope("C", record_type, f"source-{dimension}", payload, push_id=dimension)
    assert post(client, "/api/v1/ingestion/c", body).status_code == 201


def test_kol_cooperation_contract(client):
    body = base_envelope("KOL", "kol_cooperation_result", "coop-source", kol_cooperation_payload())
    response = post(client, "/api/v1/ingestion/kol", body)
    assert response.status_code == 201
    record = client.get(f"/api/v1/records/{response.json()['record_id']}", headers=AUTH).json()["record"]
    assert record["business_key"] == "coop-1"
    assert "review_conclusion: Suitable for another campaign" in record["retrieval_text"]


def test_push_id_idempotency_and_conflict(client):
    body = base_envelope("C", "consumer_journey_sentiment", "c-1", consumer_payload())
    first = post(client, "/api/v1/ingestion/c", body)
    repeated = post(client, "/api/v1/ingestion/c", body)
    assert first.status_code == 201
    assert repeated.status_code == 200
    assert repeated.json()["decision"] == "created"
    changed = deepcopy(body)
    changed["payload"]["signal_count"] = 99
    conflict = post(client, "/api/v1/ingestion/c", changed)
    assert conflict.status_code == 409
    assert conflict.json()["error_code"] == "push_id_conflict"
    assert client.get("/api/v1/records", headers=AUTH).json()["total"] == 1


def test_semantically_equal_timezone_values_hash_identically(client):
    body = base_envelope("C", "consumer_journey_sentiment", "c-1", consumer_payload())
    assert post(client, "/api/v1/ingestion/c", body).status_code == 201
    equivalent = deepcopy(body)
    equivalent["payload"]["period_start"] = "2026-08-04T08:00:00+08:00"
    equivalent["payload"]["period_end"] = "2026-08-05T07:59:59+08:00"
    response = post(client, "/api/v1/ingestion/c", equivalent)
    assert response.status_code == 200
    assert response.json()["decision"] == "created"


def test_integer_version_rules(client):
    original = base_envelope("C", "consumer_journey_sentiment", "c-1", consumer_payload(), push_id="v1")
    assert post(client, "/api/v1/ingestion/c", original).json()["decision"] == "created"

    same = base_envelope("C", "consumer_journey_sentiment", "c-1", consumer_payload(), push_id="v1-same")
    assert post(client, "/api/v1/ingestion/c", same).json()["decision"] == "duplicate"
    conflict = deepcopy(same)
    conflict["push_id"] = "v1-conflict"
    conflict["payload"]["signal_count"] = 43
    assert post(client, "/api/v1/ingestion/c", conflict).status_code == 409

    newer = deepcopy(conflict)
    newer["push_id"] = "v10"
    newer["source_version"] = 10
    response = post(client, "/api/v1/ingestion/c", newer)
    assert response.status_code == 200
    assert response.json()["decision"] == "updated"
    older = deepcopy(original)
    older["push_id"] = "v2-late"
    older["source_version"] = 2
    assert post(client, "/api/v1/ingestion/c", older).json()["decision"] == "ignored_older_version"
    record = client.get(f"/api/v1/records/{response.json()['record_id']}", headers=AUTH).json()["record"]
    assert record["source_version"] == 10
    assert record["payload_json"]["signal_count"] == 43


def test_repeated_version_conflict_keeps_conflict_semantics(client):
    original = base_envelope("C", "consumer_journey_sentiment", "c-1", consumer_payload(), push_id="original")
    assert post(client, "/api/v1/ingestion/c", original).status_code == 201
    conflict = deepcopy(original)
    conflict["push_id"] = "conflict"
    conflict["payload"]["signal_count"] = 99
    assert post(client, "/api/v1/ingestion/c", conflict).status_code == 409
    repeated = post(client, "/api/v1/ingestion/c", conflict)
    assert repeated.status_code == 409
    assert repeated.json()["error_code"] == "version_conflict"


def test_b_requires_published_content(client):
    payload = business_payload()
    payload["publication_status"] = "draft"
    body = base_envelope("B", "business_policy", "entry-1", payload)
    assert post(client, "/api/v1/ingestion/b", body).status_code == 422


@pytest.mark.parametrize("path,body", [
    ("/api/v1/ingestion/b", base_envelope("B", "business_policy", "entry-1", business_payload(), event="risk_recovery")),
    ("/api/v1/ingestion/kol", base_envelope("KOL", "kol_current_assessment", "kol-1", kol_payload(), event="risk_recovery")),
])
def test_non_consumer_systems_cannot_emit_risk_recovery(client, path, body):
    assert post(client, path, body).status_code == 422


def test_business_entry_establishes_stable_source_mapping(client):
    first = base_envelope("B", "business_policy", "upstream-entry-a", business_payload(), push_id="b1")
    assert post(client, "/api/v1/ingestion/b", first).status_code == 201
    changed_source = deepcopy(first)
    changed_source.update(push_id="b2", source_record_id="upstream-entry-b", source_version=2)
    response = post(client, "/api/v1/ingestion/b", changed_source)
    assert response.status_code == 409
    assert response.json()["error_code"] == "source_record_conflict"


def test_current_and_snapshot_isolation(client):
    current = base_envelope("C", "consumer_journey_sentiment", "c-1", consumer_payload("journey_sentiment", "2026-08-05"), push_id="current-1")
    assert post(client, "/api/v1/ingestion/c", current).status_code == 201
    next_day = base_envelope("C", "consumer_journey_sentiment", "c-1", consumer_payload("journey_sentiment", "2026-08-06"), push_id="current-2", version=2)
    assert post(client, "/api/v1/ingestion/c", next_day).json()["decision"] == "updated"

    snap_old = base_envelope("C", "consumer_journey_sentiment", "c-1", consumer_payload("journey_sentiment", "2026-08-04"), push_id="snap-old", event="create_snapshot")
    snap_new = base_envelope("C", "consumer_journey_sentiment", "c-1", consumer_payload("journey_sentiment", "2026-08-05"), push_id="snap-new", event="create_snapshot")
    assert post(client, "/api/v1/ingestion/c", snap_old).status_code == 201
    assert post(client, "/api/v1/ingestion/c", snap_new).status_code == 201
    snap_newer_version = deepcopy(snap_old)
    snap_newer_version["push_id"] = "snap-old-v3"
    snap_newer_version["source_version"] = 3
    snap_newer_version["payload"]["signal_count"] = 50
    assert post(client, "/api/v1/ingestion/c", snap_newer_version).json()["decision"] == "updated"

    records = client.get("/api/v1/records", headers=AUTH).json()["items"]
    assert len(records) == 3
    current_record = next(item for item in records if item["record_mode"] == "current")
    assert current_record["payload_json"]["business_date"] == "2026-08-06"
    assert current_record["target_knowledge_base"] == "c_current"
    assert {item["target_knowledge_base"] for item in records if item["record_mode"] == "snapshot"} == {"c_history"}


def test_archive_and_restore_preserve_content(client):
    body = base_envelope("C", "consumer_journey_sentiment", "c-1", consumer_payload(), push_id="create")
    created = post(client, "/api/v1/ingestion/c", body).json()
    archive = deepcopy(body)
    archive.update(push_id="archive", source_version=2, event_type="archive")
    archived = post(client, "/api/v1/ingestion/c", archive)
    assert archived.json()["decision"] == "archived"
    record = client.get(f"/api/v1/records/{created['record_id']}", headers=AUTH).json()["record"]
    assert record["status"] == "archived"
    assert record["payload_json"]["signal_count"] == 42
    low_archive = deepcopy(archive)
    low_archive.update(push_id="archive-low", source_version=1)
    assert post(client, "/api/v1/ingestion/c", low_archive).json()["decision"] == "ignored_older_version"

    restore = deepcopy(body)
    restore.update(push_id="restore", source_version=3, event_type="restore")
    restore["payload"]["signal_count"] = 55
    restored = post(client, "/api/v1/ingestion/c", restore)
    assert restored.json()["decision"] == "restored"
    record = client.get(f"/api/v1/records/{created['record_id']}", headers=AUTH).json()["record"]
    assert record["status"] == "active"
    assert record["payload_json"]["signal_count"] == 55
    assert "signal_count: 55" in record["retrieval_text"]
    assert client.delete(f"/api/v1/records/{created['record_id']}", headers=AUTH).status_code == 405


def test_archived_record_cannot_be_reactivated_by_plain_update(client):
    body = base_envelope("C", "consumer_journey_sentiment", "c-1", consumer_payload(), push_id="create")
    created = post(client, "/api/v1/ingestion/c", body).json()
    archive = deepcopy(body)
    archive.update(push_id="archive", source_version=2, event_type="archive")
    assert post(client, "/api/v1/ingestion/c", archive).json()["decision"] == "archived"

    update = deepcopy(body)
    update.update(push_id="plain-update", source_version=3, event_type="update_current")
    update["payload"]["signal_count"] = 99
    response = post(client, "/api/v1/ingestion/c", update)
    assert response.status_code == 409
    assert response.json()["error_code"] == "invalid_transition"

    record = client.get(f"/api/v1/records/{created['record_id']}", headers=AUTH).json()["record"]
    assert record["status"] == "archived"
    assert record["source_version"] == 2
    assert record["payload_json"]["signal_count"] == 42


def test_archiving_risk_does_not_append_trend_point(client):
    body = base_envelope("C", "consumer_recall_risk", "risk-archive", consumer_payload("recall_risk"), push_id="risk-create")
    assert post(client, "/api/v1/ingestion/c", body).status_code == 201
    archive = deepcopy(body)
    archive.update(push_id="risk-archive", source_version=2, event_type="archive")
    assert post(client, "/api/v1/ingestion/c", archive).status_code == 200
    risk_id = client.get("/api/v1/risks", headers=AUTH).json()["items"][0]["id"]
    detail = client.get(f"/api/v1/risks/{risk_id}", headers=AUTH).json()["risk"]
    assert len(detail["episodes"][0]["trend_points"]) == 1


def test_risk_episode_lifecycle(client):
    payload = consumer_payload("recall_risk")
    first = base_envelope("C", "consumer_recall_risk", "risk-1", payload, push_id="risk-1")
    assert post(client, "/api/v1/ingestion/c", first).status_code == 201
    continued = deepcopy(first)
    continued.update(push_id="risk-2", source_version=2, effective_at="2026-08-06T10:00:00+08:00")
    continued["payload"]["result"]["hit_count"] = 15
    assert post(client, "/api/v1/ingestion/c", continued).json()["decision"] == "updated"
    repeated = post(client, "/api/v1/ingestion/c", continued)
    assert repeated.status_code == 200

    recovery = deepcopy(continued)
    recovery.update(push_id="risk-recovery", source_version=3, event_type="risk_recovery", effective_at="2026-08-07T10:00:00+08:00")
    recovery["payload"]["result"].update(threshold_exceeded=False, risk_status="recovered")
    assert post(client, "/api/v1/ingestion/c", recovery).json()["decision"] == "risk_recovered"
    retrigger = deepcopy(first)
    retrigger.update(push_id="risk-4", source_version=4, effective_at="2026-08-08T10:00:00+08:00")
    assert post(client, "/api/v1/ingestion/c", retrigger).json()["decision"] == "updated"

    risks = client.get("/api/v1/risks", headers=AUTH).json()
    detail = client.get(f"/api/v1/risks/{risks['items'][0]['id']}", headers=AUTH).json()["risk"]
    assert len(detail["episodes"]) == 2
    assert [item["status"] for item in detail["episodes"]] == ["recovered", "open"]
    assert len(detail["episodes"][0]["trend_points"]) == 2
    assert len(detail["episodes"][1]["trend_points"]) == 1


def test_risk_recovery_rejects_still_exceeded_payload(client):
    payload = consumer_payload("recall_risk")
    first = base_envelope("C", "consumer_recall_risk", "risk-1", payload, push_id="risk-1")
    assert post(client, "/api/v1/ingestion/c", first).status_code == 201
    invalid = deepcopy(first)
    invalid.update(push_id="bad-recovery", source_version=2, event_type="risk_recovery")
    response = post(client, "/api/v1/ingestion/c", invalid)
    assert response.status_code == 422
    assert response.json()["error_code"] == "invalid_risk_recovery"


def test_fake_adapter_success_mapping_and_summary(client):
    body = base_envelope("KOL", "kol_current_assessment", "kol-source", kol_payload())
    created = post(client, "/api/v1/ingestion/kol", body).json()
    processed = post(client, "/api/v1/maintenance/sync-tasks/process-pending", {"operator": "tester"})
    assert processed.json()["completed"] == 1
    tasks = client.get("/api/v1/maintenance/sync-tasks", headers=AUTH).json()["items"]
    assert tasks[0]["status"] == "completed"
    with client.app.state.session_factory() as db:
        mapping = db.scalar(select(RagDocumentMapping).where(RagDocumentMapping.record_id == created["record_id"]))
        assert mapping.external_document_id == f"fake-doc-{created['record_id']}"
        assert mapping.external_is_active is True
        assert mapping.mapped_source_version == 1
    summary = client.get("/api/v1/maintenance/sync-summary", headers=AUTH).json()["targets"]
    assert summary["kol"]["completed"] == 1
    assert set(summary) == {"c_current", "c_history", "b_business", "kol"}
    resync = post(client, f"/api/v1/maintenance/records/{created['record_id']}/resync", {"operator": "tester"})
    assert resync.json()["created"] is False


def test_auto_sync_kicks_dispatch_without_manual_process(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'auto.db'}",
        api_key=AUTH["X-API-Key"],
        adapter="fake",
        fake_mode="success",
        auto_sync_on_ingest=True,
        maxkb_sync_workers=2,
        maxkb_sync_batch_size=10,
        maxkb_sync_poll_interval_seconds=0.1,
    )
    with TestClient(create_app(settings)) as client:
        body = base_envelope("KOL", "kol_current_assessment", "kol-auto", kol_payload(), push_id="auto-kol")
        assert post(client, "/api/v1/ingestion/kol", body).status_code == 201

        deadline = time.time() + 3
        while time.time() < deadline:
            tasks = client.get("/api/v1/maintenance/sync-tasks", headers=AUTH).json()["items"]
            if tasks and tasks[0]["status"] == "completed":
                break
            time.sleep(0.05)
        assert client.get("/api/v1/maintenance/sync-tasks", headers=AUTH).json()["items"][0]["status"] == "completed"


def test_fake_adapter_failure_and_processing_keep_record(client_factory):
    for mode, expected in [("failure", "failed"), ("processing", "processing")]:
        client = client_factory(mode)
        body = base_envelope("KOL", "kol_current_assessment", f"kol-{mode}", kol_payload(), push_id=mode)
        assert post(client, "/api/v1/ingestion/kol", body).status_code == 201
        post(client, "/api/v1/maintenance/sync-tasks/process-pending", {"operator": "tester"})
        tasks = client.get("/api/v1/maintenance/sync-tasks", headers=AUTH).json()["items"]
        assert tasks[0]["status"] == expected
        assert client.get("/api/v1/records", headers=AUTH).json()["total"] == 1
        if mode == "processing":
            post(client, "/api/v1/maintenance/sync-tasks/process-pending", {"operator": "tester"})
            timed_out = post(client, "/api/v1/maintenance/sync-tasks/process-pending", {"operator": "tester"})
            assert timed_out.json()["timed_out"] == 1
            tasks = client.get("/api/v1/maintenance/sync-tasks", headers=AUTH).json()["items"]
            assert tasks[0]["status"] == "timed_out"


def test_annotations_and_scoped_rebuild(client):
    c = post(client, "/api/v1/ingestion/c", base_envelope("C", "consumer_journey_sentiment", "c", consumer_payload(), push_id="c")).json()
    post(client, "/api/v1/ingestion/b", base_envelope("B", "business_policy", "entry-1", business_payload(), push_id="b"))
    before = client.get(f"/api/v1/records/{c['record_id']}", headers=AUTH).json()["record"]
    note = post(client, f"/api/v1/records/{c['record_id']}/annotations", {
        "annotation_type": "correction_feedback", "content": "Check the source window", "author": "analyst",
    })
    assert note.status_code == 201
    assert len(client.get(f"/api/v1/records/{c['record_id']}/annotations", headers=AUTH).json()["items"]) == 1
    after = client.get(f"/api/v1/records/{c['record_id']}", headers=AUTH).json()["record"]
    assert (after["source_version"], after["status"], after["payload_json"]) == (before["source_version"], before["status"], before["payload_json"])
    rebuilt = post(client, "/api/v1/maintenance/rebuild", {"operator": "tester", "source_system": "C"})
    assert rebuilt.json()["records_rebuilt"] == 1
    assert rebuilt.json()["tasks_queued"] == 1


def test_rebuild_requires_source_or_target_scope(client):
    response = post(client, "/api/v1/maintenance/rebuild", {"operator": "tester"})
    assert response.status_code == 422


def test_stale_sync_task_never_sends_newer_record_as_old_version(client):
    first = base_envelope("C", "consumer_journey_sentiment", "c-1", consumer_payload(), push_id="v1")
    created = post(client, "/api/v1/ingestion/c", first).json()
    second = deepcopy(first)
    second.update(push_id="v2", source_version=2)
    second["payload"]["signal_count"] = 50
    assert post(client, "/api/v1/ingestion/c", second).status_code == 200
    processed = post(client, "/api/v1/maintenance/sync-tasks/process-pending", {"operator": "tester"})
    assert processed.json()["completed"] == 2
    tasks = client.get("/api/v1/maintenance/sync-tasks", headers=AUTH).json()["items"]
    assert {task["status"] for task in tasks} == {"completed"}
    record = client.get(f"/api/v1/records/{created['record_id']}", headers=AUTH).json()["record"]
    assert "[source_version] 2" in record["retrieval_text"]


def test_framework_404_and_405_include_request_id(client):
    missing = client.get("/does-not-exist", headers=AUTH)
    assert missing.status_code == 404
    assert "request_id" in missing.json()
    method = client.delete("/api/v1/records/not-present", headers=AUTH)
    assert method.status_code == 405
    assert "request_id" in method.json()


def test_retrieval_text_golden_shape(client):
    body = base_envelope("B", "business_policy", "entry-1", business_payload())
    created = post(client, "/api/v1/ingestion/b", body).json()
    record = client.get(f"/api/v1/records/{created['record_id']}", headers=AUTH).json()["record"]
    expected = f"""[record_id] {created['record_id']}
[source] B
[record_type] business_policy
[source_record_id] entry-1
[source_version] 1
[business_date] 
[is_mock] false

entry_type: policy
title: EU battery policy
published_summary: The approved policy summary.
regions: [\"EU\"]
tags: [\"battery\"]
related_entities: [{{\"stable_id\":\"ec\",\"standard_name\":\"EC\",\"type\":\"regulator\"}}]
business_impact: Reporting changes
recommended_action: Review reporting
external_sources: [{{\"name\":\"Official source\",\"url\":\"https://example.com/policy\"}}]
source_version: 1
effective_at: 2026-08-05T02:00:00+00:00"""
    assert record["retrieval_text"] == expected
