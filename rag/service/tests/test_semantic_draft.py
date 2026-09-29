from __future__ import annotations

import httpx
import pytest
import time
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.main import create_app
from app.models import RagDocumentMapping
from app.query import (
    Evidence, SemanticDraft, SemanticDraftError, aggregate_semantic_source, assess_semantic_draft, build_prd_output,
    deterministic_semantic_draft, format_evidence_context, format_semantic_evidence_context, parse_semantic_draft,
    parse_semantic_draft_partial, safe_semantic_draft, semantic_field_metadata,
    structured_semantic_draft, validate_semantic_draft,
)
from conftest import API_KEY, AUTH, base_envelope, consumer_payload


def _c_evidence() -> list[Evidence]:
    return [Evidence("c-1", "c_current", "[business_date] 2026-08-05\nrisk_status: open", 0.9, 1)]


def _b_evidence() -> list[Evidence]:
    return [Evidence("b-1", "b_business", "effective_at: 2026-08-05T08:00:00+00:00\ntitle: policy", 0.9, 1)]


def _kol_evidence() -> list[Evidence]:
    return [Evidence("kol-1", "kol", "published_at: 2026-08-05\ntitle: creator post", 0.9, 1)]


def _draft(**overrides) -> SemanticDraft:
    values = {
        "summary": "C端风险信号与B端法规影响需要分别复核。",
        "consumer_signal": "C端证据显示风险状态为 open。",
        "business_impact": "B端证据记录了法规影响。",
        "kol_impact": None,
        "actions": ["复核当前证据对应的原始数据。"],
    }
    values.update(overrides)
    return SemanticDraft(**values)


@pytest.mark.parametrize("raw", [
    '{"summary":"结论","consumer_signal":"C","business_impact":null,"kol_impact":null,"actions":["核查"]}',
    '```json\n{"summary":"结论","consumer_signal":"C","business_impact":null,"kol_impact":null,"actions":["核查"]}\n```',
    '模型输出如下： {"summary":"结论","consumer_signal":"C","business_impact":null,"kol_impact":null,"actions":["核查"]} 谢谢',
])
def test_parse_semantic_draft_accepts_json_fences_and_surrounding_text(raw):
    draft = parse_semantic_draft(raw)
    assert draft.summary == "结论" and draft.actions == ["核查"]


def test_parse_semantic_draft_unwraps_single_domain_keyed_sentence():
    draft = parse_semantic_draft(
        '{"summary":"结论","consumer_signal":{"c_current":"消费者反馈整体偏正面。"},'
        '"business_impact":null,"kol_impact":null,"actions":["核查"]}'
    )
    assert draft.consumer_signal == "消费者反馈整体偏正面。"


@pytest.mark.parametrize("raw", [
    '{}',
    '{"summary":"结论","consumer_signal":null,"business_impact":null,"kol_impact":null,"actions":"核查"}',
    '{"summary":"结论","consumer_signal":null,"business_impact":null,"kol_impact":null,"actions":[],"extra":1}',
    '{"summary":"","consumer_signal":null,"business_impact":null,"kol_impact":null,"actions":[]}',
])
def test_parse_semantic_draft_rejects_missing_wrong_or_extra_fields(raw):
    with pytest.raises(SemanticDraftError):
        parse_semantic_draft(raw)


@pytest.mark.parametrize("field, value", [
    ("summary", "c_current"),
    ("consumer_signal", "c_current"),
    ("business_impact", "b_business"),
    ("kol_impact", "kol"),
])
def test_domain_labels_are_not_accepted_as_semantic_answers(field, value):
    draft = _draft(**{field: value})
    with pytest.raises(SemanticDraftError, match="placeholder"):
        validate_semantic_draft(
            draft,
            _c_evidence() + _b_evidence() + _kol_evidence(),
            ["c_current", "b_business", "kol"],
        )


def test_domain_validation_requires_evidence_and_prevents_cross_domain_copying():
    with pytest.raises(SemanticDraftError, match="without_evidence"):
        validate_semantic_draft(_draft(business_impact="B端证据记录了法规影响。"), _c_evidence(), ["c_current"])
    with pytest.raises(SemanticDraftError, match="missing"):
        validate_semantic_draft(_draft(business_impact=None), _c_evidence() + _b_evidence(), ["c_current", "b_business"])
    with pytest.raises(SemanticDraftError, match="action_domain_mismatch"):
        validate_semantic_draft(
            _draft(consumer_signal=None, business_impact="B端证据记录了法规影响。", actions=["复核消费者反馈。"]),
            _b_evidence(),
            ["b_business"],
        )
    with pytest.raises(SemanticDraftError, match="copies_summary"):
        validate_semantic_draft(_draft(consumer_signal="同一结论", business_impact="另一条结论", summary="同一结论"), _c_evidence() + _b_evidence(), ["c_current", "b_business"])
    valid = validate_semantic_draft(_draft(), _c_evidence() + _b_evidence(), ["c_current", "b_business"])
    assert valid.kol_impact is None


def test_build_prd_output_keeps_domains_separate_and_deduplicates_nonempty_dates():
    evidence = _c_evidence() + [Evidence("c-2", "c_current", "[business_date] \n[business_date] 2026-08-05", 0.8, 1)] + _b_evidence()
    output = build_prd_output(draft=_draft(), evidence=evidence, selected=["c_current", "b_business"])
    assert output["C端消费者信号"] == "C端证据显示风险状态为 open。"
    assert output["B端商业影响"] == "B端证据记录了法规影响。"
    assert output["KOL传播与合作影响"] is None
    assert output["数据时间"] == ["2026-08-05", "2026-08-05T08:00:00+00:00"]


def test_safe_draft_never_copies_a_single_answer_to_other_domains():
    draft = safe_semantic_draft(_c_evidence())
    assert draft.consumer_signal is not None
    assert draft.business_impact is None and draft.kol_impact is None
    assert draft.actions
    assert all("消费者" in action or "C 端" in action for action in draft.actions)


def test_deterministic_b_only_draft_has_no_consumer_action():
    draft = safe_semantic_draft(_b_evidence())
    assert draft.consumer_signal is None and draft.kol_impact is None
    assert draft.business_impact is not None
    assert draft.actions
    assert all("消费者" not in action and "评论" not in action and "情绪" not in action for action in draft.actions)


def test_multi_domain_safe_draft_keeps_fallback_messages_distinct():
    draft = safe_semantic_draft(_c_evidence() + _b_evidence())
    assert draft.consumer_signal != draft.business_impact
    output = build_prd_output(draft=draft, evidence=_c_evidence() + _b_evidence(), selected=["c_current", "b_business"])
    assert output["C端消费者信号"] != output["B端商业影响"]


def test_deterministic_structured_answer_is_not_copied_across_multiple_domains():
    draft = structured_semantic_draft("涉及品牌有 Tesla。", _c_evidence() + _b_evidence())
    assert draft.summary == "涉及品牌有 Tesla。"
    assert draft.consumer_signal is None and draft.business_impact is None and draft.kol_impact is None


def test_evidence_context_marks_domains_without_raw_hit_metadata():
    context = format_evidence_context(_c_evidence() + _b_evidence(), max_chars=1000)
    assert "[证据域: c_current]" in context and "[C1]" in context
    assert "[证据域: b_business]" in context and "[B1]" in context


def test_semantic_context_keeps_present_domains_and_omits_verbose_nested_metrics():
    evidence = [
        Evidence(
            "c-large", "c_current",
            "dimension: journey_sentiment\nbrand: Tesla\nvehicle_model: Model Y\n"
            "result: {\"positive_ratio\":0.8,\"journey_curve\":\"" + "x" * 5000 + "\"}",
            0.9, 1,
        ),
        _b_evidence()[0],
        _kol_evidence()[0],
    ]
    context = format_semantic_evidence_context(evidence, max_chars=1200)

    assert "## C端消费者证据" in context
    assert "## B端商业证据" in context
    assert "## KOL传播与合作证据" in context
    assert "[C1]" in context and "[B1]" in context and "[KOL1]" in context
    assert "journey_curve" not in context


def test_semantic_context_limits_each_domain_to_top_three_records():
    evidence = [
        Evidence(f"c-{index}", "c_current", f"dimension: test_{index}\nbrand: Tesla", 1.0 - index / 10, 1)
        for index in range(1, 5)
    ] + _b_evidence() + _kol_evidence()
    context = format_semantic_evidence_context(evidence, max_chars=10000)

    assert "维度=test_1" in context and "维度=test_3" in context
    assert "维度=test_4" not in context
    assert "## B端商业证据" in context and "## KOL传播与合作证据" in context


def test_partial_parser_accepts_explicit_ui_aliases_and_action_string():
    parsed = parse_semantic_draft_partial(
        '{"综合结论":"跨域证据显示需要分别复核。",'
        '"C端消费者信号":{"c_current":"消费者反馈显示风险状态为 open。"},'
        '"B端商业影响":null,"KOL传播与合作影响":null,'
        '"文字行动建议":"复核消费者证据；确认统计口径。","ignored":"不应展示"}'
    )
    assert parsed.summary == "跨域证据显示需要分别复核。"
    assert parsed.consumer_signal == "消费者反馈显示风险状态为 open。"
    assert parsed.actions == ["复核消费者证据", "确认统计口径。"]
    assert "ignored" not in parsed.present_fields


def test_field_level_assessment_keeps_valid_domains_and_falls_back_only_invalid_field():
    evidence = _c_evidence() + _b_evidence() + _kol_evidence()
    fallback, _ = deterministic_semantic_draft(evidence)
    parsed = parse_semantic_draft_partial(
        '{"summary":"跨域证据显示需要分别复核。",'
        '"consumer_signal":"消费者反馈显示风险状态为 open。",'
        '"business_impact":{"unexpected":"不接受"},'
        '"kol_impact":"KOL 内容存在传播与合作影响。",'
        '"actions":["复核消费者证据"]}'
    )
    assessment = assess_semantic_draft(parsed, evidence, ["c_current", "b_business", "kol"], fallback)
    assert assessment.draft.summary == "跨域证据显示需要分别复核。"
    assert assessment.draft.consumer_signal == "消费者反馈显示风险状态为 open。"
    assert assessment.draft.business_impact == fallback.business_impact
    assert assessment.draft.kol_impact == "KOL 内容存在传播与合作影响。"
    assert assessment.field_sources == {
        "summary": "maxkb",
        "consumer_signal": "maxkb",
        "business_impact": "deterministic",
        "kol_impact": "maxkb",
        "actions": "maxkb",
    }


def test_semantic_field_metadata_returns_backend_owned_no_evidence_notices():
    metadata = semantic_field_metadata({
        "summary": "maxkb", "consumer_signal": "maxkb", "business_impact": "none",
        "kol_impact": "none", "actions": "maxkb",
    })
    assert metadata["business_impact"]["notice"].startswith("当前选定范围内没有可支持 B 端")
    assert metadata["kol_impact"]["notice"].startswith("当前选定范围内没有可支持 KOL")
    assert metadata["consumer_signal"]["notice"] is None


def test_valid_three_domain_draft_maps_each_card_to_its_own_llm_summary():
    evidence = _c_evidence() + _b_evidence() + _kol_evidence()
    fallback, _ = deterministic_semantic_draft(evidence)
    parsed = parse_semantic_draft_partial(
        '{"summary":"三端证据需要分别研判，当前结论仅覆盖已校验记录。",'
        '"consumer_signal":"消费者反馈显示风险状态为 open，当前需要结合已有记录观察后续变化。",'
        '"business_impact":"商业证据记录了政策条目，相关项目需要按生效时间核对影响范围。",'
        '"kol_impact":"KOL 证据记录了创作者内容，传播与合作影响需要结合当前合作状态复核。",'
        '"actions":["分别核对三端证据对应的原始记录。"]}'
    )
    assessment = assess_semantic_draft(parsed, evidence, ["c_current", "b_business", "kol"], fallback)
    output = build_prd_output(
        draft=assessment.draft, evidence=evidence, selected=["c_current", "b_business", "kol"],
    )

    assert aggregate_semantic_source(assessment.field_sources) == "maxkb"
    assert output["C端消费者信号"] == parsed.consumer_signal
    assert output["B端商业影响"] == parsed.business_impact
    assert output["KOL传播与合作影响"] == parsed.kol_impact
    assert output["综合结论"] == parsed.summary


def test_model_cannot_fill_a_domain_without_evidence():
    evidence = _c_evidence()
    fallback, _ = deterministic_semantic_draft(evidence)
    parsed = parse_semantic_draft_partial(
        '{"summary":"消费者证据需要复核。",'
        '"consumer_signal":"消费者反馈显示风险状态为 open。",'
        '"business_impact":null,'
        '"kol_impact":"KOL 内容传播影响明显。",'
        '"actions":["复核消费者证据。"]}'
    )
    assessment = assess_semantic_draft(parsed, evidence, ["c_current", "b_business", "kol"], fallback)

    assert assessment.draft.kol_impact is None
    assert assessment.field_sources["kol_impact"] == "none"
    assert semantic_field_metadata(assessment.field_sources)["kol_impact"]["notice"].startswith("当前选定范围内没有可支持 KOL")


def _semantic_client(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'semantic.db'}", api_key=API_KEY,
        adapter="fake", fake_mode="success", auto_sync_on_ingest=False,
        rag_query_planner_mode="active", rag_semantic_draft_mode="active",
        maxkb_applications={"cross_domain": "app-1"},
    )
    return TestClient(create_app(settings))


def _indexed_consumer(client):
    payload = consumer_payload("recall_risk")
    payload.update(brand="Tesla", vehicle_model="Model Y")
    created = client.post("/api/v1/ingestion/c", headers=AUTH, json=base_envelope(
        "C", "consumer_recall_risk", "semantic-c", payload, push_id="semantic-c",
    )).json()
    client.post("/api/v1/maintenance/sync-tasks/process-pending", headers=AUTH, json={"operator": "test"})
    with client.app.state.session_factory() as db:
        return db.scalar(select(RagDocumentMapping).where(RagDocumentMapping.record_id == created["record_id"]))


def test_active_semantic_prompt_only_uses_final_evidence_and_returns_c_domain(tmp_path, monkeypatch):
    with _semantic_client(tmp_path) as client:
        mapping = _indexed_consumer(client)
        prompts = []

        class Adapter:
            def search(self, **kwargs):
                return [
                    {"document_id": mapping.external_document_id, "similarity": 0.91},
                    {"document_id": "unmapped-filtered-hit", "similarity": 0.99},
                ]

            def chat(self, **kwargs):
                prompts.append(kwargs)
                return {"answer": '{"summary":"消费者风险需要复核。","consumer_signal":"C端风险状态为 open。","business_impact":null,"kol_impact":null,"actions":["核查原始评论。"]}'}

        client.app.state.adapter = Adapter()
        monkeypatch.setattr(
            "app.main._ollama_semantic_draft",
            lambda *args: (_ for _ in ()).throw(AssertionError("active mode must not call Ollama")),
        )
        response = client.post("/api/v1/query", headers=AUTH, json={"query": "Tesla Model Y 的风险状态如何？"})
        assert response.status_code == 200
        assert response.json()["query_meta"]["generation_source"] == "maxkb"
        assert response.json()["query_meta"]["generation_status"] == "ok"
        output = response.json()["output"]
        assert output["C端消费者信号"] == "C端风险状态为 open。"
        assert output["B端商业影响"] is None and output["KOL传播与合作影响"] is None
        assert response.json()["query_meta"]["semantic_fields"]["consumer_signal"]["source"] == "maxkb"
        assert response.json()["query_meta"]["semantic_fields"]["business_impact"]["source"] == "none"
        assert "[证据域: c_current]" in prompts[0]["query"]
        assert "unmapped-filtered-hit" not in prompts[0]["query"]


def test_active_semantic_call_is_used_even_when_structured_answer_exists(tmp_path):
    with _semantic_client(tmp_path) as client:
        mapping = _indexed_consumer(client)
        calls = []

        class Adapter:
            def search(self, **kwargs):
                return [{"document_id": mapping.external_document_id, "similarity": 0.91}]

            def chat(self, **kwargs):
                calls.append(kwargs)
                return {"answer": '{"summary":"LLM 汇总品牌证据。","consumer_signal":"消费者证据显示 Example Motors。",' \
                                '"business_impact":null,"kol_impact":null,"actions":["复核品牌字段。"]}'}

        client.app.state.adapter = Adapter()
        response = client.post("/api/v1/query", headers=AUTH, json={"query": "有哪些品牌"})
        assert response.status_code == 200
        assert len(calls) == 1
        assert response.json()["output"]["综合结论"] == "LLM 汇总品牌证据。"
        assert response.json()["query_meta"]["generation_source"] == "maxkb"


def test_active_semantic_parse_failure_uses_deterministic_fallback_without_ollama(tmp_path, monkeypatch):
    with _semantic_client(tmp_path) as client:
        mapping = _indexed_consumer(client)

        class Adapter:
            def search(self, **kwargs):
                return [{"document_id": mapping.external_document_id, "similarity": 0.91}]

            def chat(self, **kwargs):
                return {"answer": "not json"}

        client.app.state.adapter = Adapter()
        monkeypatch.setattr(
            "app.main._ollama_semantic_draft",
            lambda *args: (_ for _ in ()).throw(AssertionError("active mode must not call Ollama")),
        )
        response = client.post("/api/v1/query", headers=AUTH, json={"query": "Tesla Model Y 的风险状态如何？"})
        assert response.status_code == 200
        body = response.json()
        assert body["query_meta"]["generation_source"] == "deterministic"
        assert body["query_meta"]["generation_status"] == "degraded"
        assert body["query_meta"]["degraded_reason"] == "maxkb_schema_invalid"
        output = body["output"]
        assert output["综合结论"].startswith("证据兜底")
        assert output["C端消费者信号"].startswith("C端证据兜底")
        assert output["B端商业影响"] is None


def test_active_semantic_timeout_does_not_call_ollama(tmp_path, monkeypatch):
    with _semantic_client(tmp_path) as client:
        mapping = _indexed_consumer(client)

        class Adapter:
            def search(self, **kwargs):
                return [{"document_id": mapping.external_document_id, "similarity": 0.91}]

            def chat(self, **kwargs):
                raise httpx.ReadTimeout("MaxKB timed out")

        client.app.state.adapter = Adapter()
        monkeypatch.setattr(
            "app.main._ollama_semantic_draft",
            lambda *args: (_ for _ in ()).throw(AssertionError("active mode must not call Ollama")),
        )
        response = client.post("/api/v1/query", headers=AUTH, json={"query": "Tesla Model Y 的风险状态如何？"})
        assert response.status_code == 200
        body = response.json()
        assert body["query_meta"]["generation_status"] == "degraded"
        assert body["query_meta"]["degraded_reason"] == "maxkb_timeout"
        assert body["query_meta"]["generation_source"] == "deterministic"
        assert body["evidence_count"] == 1


def test_active_budget_exhaustion_returns_structured_fallback_without_model_call(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'deadline.db'}", api_key=API_KEY,
        adapter="fake", fake_mode="success", auto_sync_on_ingest=False,
        rag_query_planner_mode="active", rag_semantic_draft_mode="active",
        rag_query_deadline_seconds=0.001,
        maxkb_applications={"cross_domain": "app-1"},
    )
    with TestClient(create_app(settings)) as client:
        mapping = _indexed_consumer(client)

        class Adapter:
            def search(self, **kwargs):
                time.sleep(0.15)
                return [{"document_id": mapping.external_document_id, "similarity": 0.91}]

            def chat(self, **kwargs):
                raise AssertionError("deadline-exceeded query must not call a model")

        client.app.state.adapter = Adapter()
        monkeypatch.setattr(
            "app.main._ollama_semantic_draft",
            lambda *args: (_ for _ in ()).throw(AssertionError("active mode must not call Ollama")),
        )
        response = client.post("/api/v1/query", headers=AUTH, json={"query": "Tesla Model Y 的风险状态如何？"})
        assert response.status_code == 200
        body = response.json()
        assert body["query_meta"]["generation_status"] == "degraded"
        assert body["query_meta"]["degraded_reason"] == "query_deadline_exceeded"
        assert body["query_meta"]["generation_source"] == "deterministic"
        assert body["output"]["综合结论"]
        assert body["evidence_count"] == 1


def test_shadow_semantic_generates_a_draft_without_changing_legacy_output(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'shadow.db'}", api_key=API_KEY,
        adapter="fake", fake_mode="success", auto_sync_on_ingest=False,
        rag_query_planner_mode="active", rag_semantic_draft_mode="shadow",
        maxkb_applications={"cross_domain": "app-1"},
    )
    with TestClient(create_app(settings)) as client:
        mapping = _indexed_consumer(client)
        calls = []

        class Adapter:
            def search(self, **kwargs):
                return [{"document_id": mapping.external_document_id, "similarity": 0.91}]

            def chat(self, **kwargs):
                calls.append(kwargs)
                return {"answer": '{"summary":"语义结论","consumer_signal":"语义C","business_impact":null,"kol_impact":null,"actions":["核查"]}'}

        client.app.state.adapter = Adapter()
        response = client.post("/api/v1/query", headers=AUTH, json={"query": "Tesla Model Y 的风险状态如何？"})
        assert response.status_code == 200
        assert calls and "[证据域: c_current]" in calls[0]["query"]
        # Shadow stays on the legacy response shape and does not surface the draft.
        assert response.json()["output"]["综合结论"] != "语义结论"


def test_no_evidence_does_not_call_semantic_model(tmp_path):
    with _semantic_client(tmp_path) as client:
        class Adapter:
            def search(self, **kwargs):
                return []

            def chat(self, **kwargs):
                raise AssertionError("no evidence must not call a model")

        client.app.state.adapter = Adapter()
        response = client.post("/api/v1/query", headers=AUTH, json={"query": "有哪些品牌"})
        assert response.status_code == 200
        assert response.json()["evidence_count"] == 0


def test_clarification_does_not_call_semantic_model(tmp_path):
    with _semantic_client(tmp_path) as client:
        class Adapter:
            def search(self, **kwargs):
                return []

            def chat(self, **kwargs):
                raise AssertionError("clarification must not call a model")

        client.app.state.adapter = Adapter()
        response = client.post("/api/v1/query", headers=AUTH, json={"query": "这款车最近有什么消费者风险？"})
        assert response.status_code == 200
        assert response.json()["clarification"]["required"] == ["brand", "vehicle_model"]
