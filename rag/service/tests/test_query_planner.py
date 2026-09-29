from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.main import create_app
from app.models import RagDocumentMapping
from app.query import _deduplicate_hits, evaluate_evidence, filter_effective_evidence
from app.query_planner import canonicalize_entity_value, plan_query, score_candidate, select_auxiliary_target
from conftest import API_KEY, AUTH, base_envelope, business_payload, consumer_payload


def _record(*, brand="Tesla", model="Model Y", region="EU", topic=None, target=None, text="risk_status: open"):
    payload = {"brand": brand, "vehicle_model": model, "region": region}
    if topic:
        payload.update({"title": topic, "tags": [topic]})
    return SimpleNamespace(payload_json=payload, retrieval_text=text, business_date=None, target_knowledge_base=target)


def _active_client(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'planner.db'}", api_key=API_KEY,
        adapter="fake", fake_mode="success", auto_sync_on_ingest=False,
        rag_query_planner_mode="active",
    )
    return TestClient(create_app(settings))


def _indexed_record(client, *, brand="Tesla", model="Model Y"):
    payload = consumer_payload("recall_risk")
    payload.update(brand=brand, vehicle_model=model)
    response = client.post(
        "/api/v1/ingestion/c", headers=AUTH,
        json=base_envelope("C", "consumer_recall_risk", f"{brand}-{model}", payload, push_id=f"{brand}-{model}"),
    )
    assert response.status_code == 201
    client.post("/api/v1/maintenance/sync-tasks/process-pending", headers=AUTH, json={"operator": "test"})
    with client.app.state.session_factory() as db:
        return db.scalar(select(RagDocumentMapping).where(RagDocumentMapping.record_id == response.json()["record_id"]))


def _indexed_business_record(client, *, title="General Safety Regulation 通用安全法规"):
    payload = business_payload()
    payload.update(title=title, published_summary=title, tags=[title])
    response = client.post(
        "/api/v1/ingestion/b", headers=AUTH,
        json=base_envelope("B", "business_policy", title, payload, push_id=title),
    )
    assert response.status_code == 201
    client.post("/api/v1/maintenance/sync-tasks/process-pending", headers=AUTH, json={"operator": "test"})
    with client.app.state.session_factory() as db:
        return db.scalar(select(RagDocumentMapping).where(RagDocumentMapping.record_id == response.json()["record_id"]))


def test_plan_keeps_original_chinese_question_and_maps_entities_and_fields():
    question = "特斯拉 Model-Y 在欧盟的通用安全法规风险状态和走势如何？"
    plan = plan_query(question, targets=["c_current"])
    assert plan.original_question == question
    assert plan.normalized_entities == {
        "brand": "Tesla", "vehicle_model": "Model Y", "region": "EU",
        "regulation_topic": "General Safety Regulation",
    }
    assert {"risk_status", "trend_direction"}.issubset(plan.requested_fields)
    assert plan.entity_confidence["brand"] >= 0.85


def test_c_side_vehicle_aliases_normalize_legacy_spellings_without_topic_taxonomy():
    plan = plan_query("VW ID_4 在德国的消费者风险状态如何？", targets=["c_current"])
    assert plan.normalized_entities["brand"] == "Volkswagen"
    assert plan.normalized_entities["vehicle_model"] == "ID.4"
    assert plan.normalized_entities["region"] == "Germany"
    topic_plan = plan_query("充电慢和冬季续航下降的消费者反馈", targets=["c_current"])
    assert "regulation_topic" not in topic_plan.normalized_entities
    assert topic_plan.requested_fields == frozenset()


def test_b_side_regulation_registry_aliases_are_available_on_demand():
    cases = {
        "AFIR 替代燃料基础设施法规的要求是什么？": "AFIR",
        "UNECE R156 软件更新管理要求是什么？": "UNECE R156",
        "CBAM 碳边境调节机制对汽车材料有什么影响？": "CBAM",
        "欧盟二氧化碳排放标准有哪些要求？": "EU CO2 Standards",
        "Foreign Subsidies Regulation 外国补贴条例是什么？": "Foreign Subsidies Regulation",
        "Euro NCAP 2026 安全评估协议是什么？": "Euro NCAP",
    }
    for question, expected in cases.items():
        plan = plan_query(question, targets=["b_business"])
        assert plan.normalized_entities["regulation_topic"] == expected


def test_entity_canonicalization_compares_question_aliases_to_payload_values():
    assert canonicalize_entity_value("brand", "特斯拉") == "Tesla"
    assert canonicalize_entity_value("brand", "Tesla") == "Tesla"
    assert canonicalize_entity_value("vehicle_model", "Model Y") == "Model Y"
    assert canonicalize_entity_value("vehicle_model", "Model-Y") == "Model Y"
    assert canonicalize_entity_value("brand", "UNKNOWN") is None


def test_field_aliases_include_required_consumer_fields():
    plan = plan_query("风险状态、走势、主要投诉和品牌口碑是什么？")
    assert {"risk_status", "trend_direction", "key_complaints", "brand_attitude"}.issubset(plan.requested_fields)


def test_high_confidence_subject_mismatch_filters_but_medium_only_downranks():
    plan = plan_query("Tesla Model Y 的风险状态", targets=["c_current"])
    high_score, high_filtered, _ = score_candidate(plan, _record(brand="Hyundai", model="Model Y"), 0.8)
    assert high_filtered is True
    medium_plan = replace(plan, entity_confidence={**plan.entity_confidence, "brand": 0.70})
    medium_score, medium_filtered, _ = score_candidate(medium_plan, _record(brand="Hyundai", model="Model Y"), 0.8)
    assert medium_filtered is False
    assert medium_score < high_score


def test_explicit_general_safety_regulation_does_not_accept_ai_act_evidence():
    plan = plan_query("通用安全法规的影响", targets=["b_business"])
    _, filtered, details = score_candidate(plan, _record(topic="AI Act"), 0.8)
    assert details["entity_matches"]["regulation_topic"] is False
    assert filtered is True
    _, filtered, details = score_candidate(plan, _record(topic="General Safety Regulation"), 0.8)
    assert details["entity_matches"]["regulation_topic"] is True
    assert filtered is False


def test_cross_domain_entities_only_filter_dimensions_present_in_each_record():
    plan = plan_query(
        "Tesla Model Y 在欧盟的通用安全法规对消费者和商业有什么影响？",
        targets=["c_current", "b_business"],
    )
    _, consumer_filtered, consumer_details = score_candidate(
        plan,
        _record(target="c_current"),
        0.8,
    )
    _, business_filtered, business_details = score_candidate(
        plan,
        _record(brand=None, model=None, topic="General Safety Regulation", target="b_business"),
        0.8,
    )
    assert consumer_filtered is False
    assert consumer_details["entity_matches"]["brand"] is True
    assert "regulation_topic" not in consumer_details["entity_matches"]
    assert business_filtered is False
    assert "brand" not in business_details["entity_matches"]
    assert business_details["entity_matches"]["regulation_topic"] is True


def test_cross_domain_regulation_mismatch_still_filters_business_record():
    plan = plan_query("Tesla Model Y 在欧盟的通用安全法规影响", targets=["c_current", "b_business"])
    _, filtered, details = score_candidate(
        plan,
        _record(brand=None, model=None, topic="AI Act", target="b_business"),
        0.8,
    )
    assert details["entity_matches"]["regulation_topic"] is False
    assert filtered is True


def test_parent_document_deduplication_keeps_only_the_best_chunk():
    hits = _deduplicate_hits([
        {"id": "chunk-1", "document_id": "parent-1", "similarity": 0.61},
        {"id": "chunk-2", "document_id": "parent-1", "similarity": 0.92},
        {"id": "chunk-3", "document_id": "parent-2", "similarity": 0.70},
    ])
    assert [(hit["document_id"], hit["similarity"]) for hit in hits] == [("parent-1", 0.92), ("parent-2", 0.70)]


def test_multiple_chunks_from_one_parent_produce_one_final_evidence(client):
    mapping = _indexed_record(client)
    hits = [
        {"id": "chunk-1", "document_id": mapping.external_document_id, "similarity": 0.61},
        {"id": "chunk-2", "document_id": mapping.external_document_id, "similarity": 0.92},
    ]
    with client.app.state.session_factory() as db:
        evidence = evaluate_evidence(db, hits, ["c_current"], plan=plan_query("Tesla Model Y 的风险状态", targets=["c_current"])).evidence
    assert len(evidence) == 1


def test_primary_search_uses_original_chinese_question_in_shadow_mode(client, monkeypatch):
    mapping = _indexed_record(client)
    calls = []

    class Adapter:
        def search(self, **kwargs):
            calls.append(kwargs)
            return [{"document_id": mapping.external_document_id, "similarity": 0.91}]

    client.app.state.adapter = Adapter()
    monkeypatch.setattr("app.main._ollama_evidence_answer", lambda *args: "依据证据回答。")
    question = "特斯拉 Model Y 的风险状态如何？"
    response = client.post("/api/v1/query", headers=AUTH, json={"query": question})
    assert response.status_code == 200
    assert [(call["query"], call["top_k"], call["similarity"]) for call in calls] == [(question, 5, 0.6)]


def test_shadow_keeps_legacy_evidence_even_when_planner_would_filter(client):
    mapping = _indexed_record(client, brand="Hyundai", model="Model Y")
    hits = [{"document_id": mapping.external_document_id, "similarity": 0.91}]
    with client.app.state.session_factory() as db:
        legacy = filter_effective_evidence(db, hits, ["c_current"])
        planned = evaluate_evidence(db, hits, ["c_current"], plan=plan_query("Tesla Model Y 的风险状态", targets=["c_current"]))
    assert len(legacy) == 1
    assert planned.evidence == []


def test_shadow_mode_keeps_the_same_visible_output_as_off(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main._ollama_evidence_answer", lambda *args: "依据证据回答。")
    outputs = []
    for mode in ("off", "shadow"):
        settings = Settings(
            database_url=f"sqlite:///{tmp_path / f'{mode}.db'}", api_key=API_KEY,
            adapter="fake", fake_mode="success", auto_sync_on_ingest=False,
            rag_query_planner_mode=mode,
        )
        with TestClient(create_app(settings)) as client:
            mapping = _indexed_record(client, brand="Hyundai", model="Model Y")

            class Adapter:
                def search(self, **kwargs):
                    return [{"document_id": mapping.external_document_id, "similarity": 0.91}]

            client.app.state.adapter = Adapter()
            response = client.post("/api/v1/query", headers=AUTH, json={"query": "Tesla Model Y 的风险状态如何？"})
            assert response.status_code == 200
            body = response.json()
            visible = {key: value for key, value in body.items() if key != "request_id"}
            visible["output"]["简化证据"] = [
                {key: value for key, value in source.items() if key != "record_id"}
                for source in visible["output"]["简化证据"]
            ]
            outputs.append(visible)
    assert outputs[0] == outputs[1]


def test_active_normal_hit_does_not_fallback_and_never_replaces_primary_query(tmp_path, monkeypatch):
    with _active_client(tmp_path) as client:
        mapping = _indexed_record(client)
        calls = []

        class Adapter:
            def search(self, **kwargs):
                calls.append(kwargs)
                return [{"document_id": mapping.external_document_id, "similarity": 0.91}]

        client.app.state.adapter = Adapter()
        monkeypatch.setattr("app.main._ollama_evidence_answer", lambda *args: "依据证据回答。")
        question = "特斯拉 Model Y 的风险状态如何？"
        assert client.post("/api/v1/query", headers=AUTH, json={"query": question}).status_code == 200
        assert [call["query"] for call in calls] == [question]


def test_active_fallback_runs_at_most_once_with_deterministic_auxiliary_query(tmp_path):
    with _active_client(tmp_path) as client:
        calls = []

        class Adapter:
            def search(self, **kwargs):
                calls.append(kwargs)
                return []

        client.app.state.adapter = Adapter()
        question = "特斯拉 Model Y 的风险状态如何？"
        response = client.post("/api/v1/query", headers=AUTH, json={"query": question})
        assert response.status_code == 200
        assert [call["query"] for call in calls] == [question, "Tesla Model Y risk status"]
        assert calls[1]["top_k"] == 15 and calls[1]["similarity"] == 0.35


def test_auxiliary_target_is_selected_once_for_a_cross_domain_miss(tmp_path):
    with _active_client(tmp_path) as client:
        calls = []

        class Adapter:
            def search(self, **kwargs):
                calls.append(kwargs)
                return []

        client.app.state.adapter = Adapter()
        question = "Tesla Model Y 的风险状态如何？"
        response = client.post(
            "/api/v1/query",
            headers=AUTH,
            json={"query": question, "domains": ["c", "b", "kol"]},
        )
        assert response.status_code == 200
        assert len(calls) == 4
        assert [call["target"] for call in calls[:3]] == ["c_current", "b_business", "kol"]
        assert calls[3]["target"] == "c_current"
        assert calls[3]["query"] == "Tesla Model Y risk status"
        assert select_auxiliary_target(plan_query(question, targets=["c_current", "b_business", "kol"]), ["c_current", "b_business", "kol"]) == "c_current"


def test_auxiliary_target_prefers_the_explicit_domain_without_evidence():
    plan = plan_query(
        "Tesla Model Y 的消费者和商业影响？",
        targets=["c_current", "b_business", "kol"],
    )
    assert select_auxiliary_target(
        plan,
        ["c_current", "b_business", "kol"],
        missing_targets=["b_business"],
    ) == "b_business"


def test_active_missing_c_subject_returns_clarification_without_other_brand_evidence(tmp_path):
    with _active_client(tmp_path) as client:
        mapping = _indexed_record(client, brand="Hyundai", model="Ioniq 5")

        class Adapter:
            def search(self, **kwargs):
                return [{"document_id": mapping.external_document_id, "similarity": 0.95}]

        client.app.state.adapter = Adapter()
        response = client.post("/api/v1/query", headers=AUTH, json={"query": "这款车最近有什么消费者风险？"})
        assert response.status_code == 200
        assert response.json()["evidence_count"] == 0
        assert response.json()["clarification"]["required"] == ["brand", "vehicle_model"]


def test_active_global_query_keeps_c_subject_and_b_topic_evidence(tmp_path, monkeypatch):
    with _active_client(tmp_path) as client:
        consumer_mapping = _indexed_record(client, brand="Tesla", model="Model Y")
        business_mapping = _indexed_business_record(client)

        class Adapter:
            def search(self, **kwargs):
                if kwargs["target"] == "c_current":
                    return [{"document_id": consumer_mapping.external_document_id, "similarity": 0.8}]
                return [{"document_id": business_mapping.external_document_id, "similarity": 0.8}]

        client.app.state.adapter = Adapter()
        monkeypatch.setattr("app.main._ollama_evidence_answer", lambda *args: "依据证据回答。")
        response = client.post(
            "/api/v1/query",
            headers=AUTH,
            json={
                "query": "Tesla Model Y 在欧盟的通用安全法规对消费者和商业有什么影响？",
                "domains": ["c", "b"],
            },
        )
        assert response.status_code == 200
        assert response.json()["evidence_count"] == 2
        assert {item["target_knowledge_base"] for item in response.json()["output"]["简化证据"]} == {"c_current", "b_business"}


def test_all_domains_without_kol_evidence_does_not_retry_kol(tmp_path):
    with _active_client(tmp_path) as client:
        consumer_mapping = _indexed_record(client, brand="Tesla", model="Model Y")
        business_mapping = _indexed_business_record(client)
        calls = []

        class Adapter:
            def search(self, **kwargs):
                calls.append(kwargs)
                if kwargs["target"] == "c_current":
                    return [{"document_id": consumer_mapping.external_document_id, "similarity": 0.8}]
                if kwargs["target"] == "b_business":
                    return [{"document_id": business_mapping.external_document_id, "similarity": 0.8}]
                return []

        client.app.state.adapter = Adapter()
        response = client.post(
            "/api/v1/query",
            headers=AUTH,
            json={
                "query": "Tesla Model Y 的消费者和商业影响？",
                "domains": ["c", "b", "kol"],
            },
        )
        assert response.status_code == 200
        assert response.json()["evidence_count"] == 2
        assert [call["target"] for call in calls] == ["c_current", "b_business", "kol"]
        assert [call["query"] for call in calls] == ["Tesla Model Y 的消费者和商业影响？"] * 3


def test_broad_structured_question_does_not_bind_to_a_brand():
    plan = plan_query("有哪些品牌", targets=["c_current"])
    assert plan.broad_query is True
    assert "brand" not in plan.normalized_entities
    assert plan.clarification_required is False
