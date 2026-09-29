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
        "summary": "Consumer risk signals and business regulatory impacts should be reviewed separately.",
        "consumer_signal": "Consumer evidence indicates that risk status is open.",
        "business_impact": "Business evidence documents regulatory impacts.",
        "kol_impact": None,
        "actions": ["Review the source data associated with the current evidence."],
    }
    values.update(overrides)
    return SemanticDraft(**values)


@pytest.mark.parametrize("raw", [
    '{"summary":"Conclusion","consumer_signal":"C","business_impact":null,"kol_impact":null,"actions":["Review"]}',
    '```json\n{"summary":"Conclusion","consumer_signal":"C","business_impact":null,"kol_impact":null,"actions":["Review"]}\n```',
    'Model output: {"summary":"Conclusion","consumer_signal":"C","business_impact":null,"kol_impact":null,"actions":["Review"]} Thank you',
])
def test_parse_semantic_draft_accepts_json_fences_and_surrounding_text(raw):
    draft = parse_semantic_draft(raw)
    assert draft.summary == "Conclusion" and draft.actions == ["Review"]


def test_parse_semantic_draft_unwraps_single_domain_keyed_sentence():
    draft = parse_semantic_draft(
    '{"summary":"Conclusion","consumer_signal":{"c_current":"Consumer feedback is generally positive."},'
    '"business_impact":null,"kol_impact":null,"actions":["Review"]}'
    )
    assert draft.consumer_signal == "Consumer feedback is generally positive."


@pytest.mark.parametrize("raw", [
    '{}',
    '{"summary":"Conclusion","consumer_signal":null,"business_impact":null,"kol_impact":null,"actions":"Review"}',
    '{"summary":"Conclusion","consumer_signal":null,"business_impact":null,"kol_impact":null,"actions":[],"extra":1}',
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
        validate_semantic_draft(_draft(business_impact="Business evidence documents regulatory impacts."), _c_evidence(), ["c_current"])
    with pytest.raises(SemanticDraftError, match="missing"):
        validate_semantic_draft(_draft(business_impact=None), _c_evidence() + _b_evidence(), ["c_current", "b_business"])
    with pytest.raises(SemanticDraftError, match="action_domain_mismatch"):
        validate_semantic_draft(
            _draft(consumer_signal=None, business_impact="Business evidence documents regulatory impacts.", actions=["Review consumer feedback."]),
            _b_evidence(),
            ["b_business"],
        )
    with pytest.raises(SemanticDraftError, match="copies_summary"):
        validate_semantic_draft(_draft(consumer_signal="Same conclusion", business_impact="Different conclusion", summary="Same conclusion"), _c_evidence() + _b_evidence(), ["c_current", "b_business"])
    valid = validate_semantic_draft(_draft(), _c_evidence() + _b_evidence(), ["c_current", "b_business"])
    assert valid.kol_impact is None


def test_build_prd_output_keeps_domains_separate_and_deduplicates_nonempty_dates():
    evidence = _c_evidence() + [Evidence("c-2", "c_current", "[business_date] \n[business_date] 2026-08-05", 0.8, 1)] + _b_evidence()
    output = build_prd_output(draft=_draft(), evidence=evidence, selected=["c_current", "b_business"])
    assert output["consumer_signal"] == "Consumer evidence indicates that risk status is open."
    assert output["business_impact"] == "Business evidence documents regulatory impacts."
    assert output["kol_impact"] is None
    assert output["data_time"] == ["2026-08-05", "2026-08-05T08:00:00+00:00"]


def test_safe_draft_never_copies_a_single_answer_to_other_domains():
    draft = safe_semantic_draft(_c_evidence())
    assert draft.consumer_signal is not None
    assert draft.business_impact is None and draft.kol_impact is None
    assert draft.actions
    assert all("consumer" in action for action in draft.actions)


def test_deterministic_b_only_draft_has_no_consumer_action():
    draft = safe_semantic_draft(_b_evidence())
    assert draft.consumer_signal is None and draft.kol_impact is None
    assert draft.business_impact is not None
    assert draft.actions
    assert all("consumer" not in action and "comments" not in action and "sentiment" not in action for action in draft.actions)


def test_multi_domain_safe_draft_keeps_fallback_messages_distinct():
    draft = safe_semantic_draft(_c_evidence() + _b_evidence())
    assert draft.consumer_signal != draft.business_impact
    output = build_prd_output(draft=draft, evidence=_c_evidence() + _b_evidence(), selected=["c_current", "b_business"])
    assert output["consumer_signal"] != output["business_impact"]


def test_deterministic_structured_answer_is_not_copied_across_multiple_domains():
    draft = structured_semantic_draft("The evidence includes brand Tesla.", _c_evidence() + _b_evidence())
    assert draft.summary == "The evidence includes brand Tesla."
    assert draft.consumer_signal is None and draft.business_impact is None and draft.kol_impact is None


def test_evidence_context_marks_domains_without_raw_hit_metadata():
    context = format_evidence_context(_c_evidence() + _b_evidence(), max_chars=1000)
    assert "[Evidence domain: c_current]" in context and "[C1]" in context
    assert "[Evidence domain: b_business]" in context and "[B1]" in context


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

    assert "## Consumer evidence" in context
    assert "## Business evidence" in context
    assert "## KOLcreator and partnership evidence" in context
    assert "[C1]" in context and "[B1]" in context and "[KOL1]" in context
    assert "journey_curve" not in context


def test_semantic_context_limits_each_domain_to_top_three_records():
    evidence = [
        Evidence(f"c-{index}", "c_current", f"dimension: test_{index}\nbrand: Tesla", 1.0 - index / 10, 1)
        for index in range(1, 5)
    ] + _b_evidence() + _kol_evidence()
    context = format_semantic_evidence_context(evidence, max_chars=10000)

    assert "Dimension=test_1" in context and "Dimension=test_3" in context
    assert "Dimension=test_4" not in context
    assert "## Business evidence" in context and "## Creator and partnership evidence" in context


def test_partial_parser_accepts_explicit_ui_aliases_and_action_string():
    parsed = parse_semantic_draft_partial(
    '{"summary":"Cross-domain evidence indicates separate reviews are needed.",'
        '"consumer_signal":{"c_current":"Consumer feedback indicates risk status: open."},'
        '"business_impact":null,"kol_impact":null,'
    '"action_recommendations":"Review consumer evidence; confirm the measurement methodology.","ignored":"Do not display"}'
    )
    assert parsed.summary == "Cross-domain evidence indicates separate reviews are needed."
    assert parsed.consumer_signal == "Consumer feedback indicates risk status: open."
    assert parsed.actions == ["Review consumer evidence", "Confirm the measurement methodology."]
    assert "ignored" not in parsed.present_fields


def test_field_level_assessment_keeps_valid_domains_and_falls_back_only_invalid_field():
    evidence = _c_evidence() + _b_evidence() + _kol_evidence()
    fallback, _ = deterministic_semantic_draft(evidence)
    parsed = parse_semantic_draft_partial(
    '{"summary":"Cross-domain evidence indicates separate reviews are needed.",'
        '"consumer_signal":"Consumer feedback indicates risk status: open.",'
    '"business_impact":{"unexpected":"Not accepted"},'
    '"kol_impact":"Creator content has reach and partnership impacts.",'
    '"actions":["Review consumer evidence"]}'
    )
    assessment = assess_semantic_draft(parsed, evidence, ["c_current", "b_business", "kol"], fallback)
    assert assessment.draft.summary == "Cross-domain evidence indicates separate reviews are needed."
    assert assessment.draft.consumer_signal == "Consumer feedback indicates risk status: open."
    assert assessment.draft.business_impact == fallback.business_impact
    assert assessment.draft.kol_impact == "Creator content has reach and partnership impacts."
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
    assert metadata["business_impact"]["notice"].startswith("No valid evidence supports business impact")
    assert metadata["kol_impact"]["notice"].startswith("No valid evidence supports creator impact")
    assert metadata["consumer_signal"]["notice"] is None


def test_valid_three_domain_draft_maps_each_card_to_its_own_llm_summary():
    evidence = _c_evidence() + _b_evidence() + _kol_evidence()
    fallback, _ = deterministic_semantic_draft(evidence)
    parsed = parse_semantic_draft_partial(
        '{"summary":"Evidence from all three domains should be assessed separately; this conclusion covers only validated records.",'
        '"consumer_signal":"Consumer feedback indicates an open risk that should be monitored against available records.",'
        '"business_impact":"Business evidence contains a policy entry; verify the scope of impact against its effective date.",'
        '"kol_impact":"Creator evidence contains published content; review reach and partnership impact against the current status.",'
        '"actions":["Verify the source records supporting each of the three domains."]}'
    )
    assessment = assess_semantic_draft(parsed, evidence, ["c_current", "b_business", "kol"], fallback)
    output = build_prd_output(
        draft=assessment.draft, evidence=evidence, selected=["c_current", "b_business", "kol"],
    )

    assert aggregate_semantic_source(assessment.field_sources) == "maxkb"
    assert output["consumer_signal"] == parsed.consumer_signal
    assert output["business_impact"] == parsed.business_impact
    assert output["kol_impact"] == parsed.kol_impact
    assert output["summary"] == parsed.summary


def test_model_cannot_fill_a_domain_without_evidence():
    evidence = _c_evidence()
    fallback, _ = deterministic_semantic_draft(evidence)
    parsed = parse_semantic_draft_partial(
        '{"summary":"Consumer evidence requires review.",'
        '"consumer_signal":"Consumer feedback indicates an open risk.",'
        '"business_impact":null,'
        '"kol_impact":"Creator reach has a measurable impact.",'
        '"actions":["Review the consumer evidence."]}'
    )
    assessment = assess_semantic_draft(parsed, evidence, ["c_current", "b_business", "kol"], fallback)

    assert assessment.draft.kol_impact is None
    assert assessment.field_sources["kol_impact"] == "none"
    assert semantic_field_metadata(assessment.field_sources)["kol_impact"]["notice"].startswith("No valid evidence supports creator impact")


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
                return {"answer": '{"summary":"Consumer risk requires review.","consumer_signal":"Consumer risk status: open.","business_impact":null,"kol_impact":null,"actions":["Review the original customer feedback."]}'}

        client.app.state.adapter = Adapter()
        monkeypatch.setattr(
            "app.main._ollama_semantic_draft",
            lambda *args: (_ for _ in ()).throw(AssertionError("active mode must not call Ollama")),
        )
        response = client.post("/api/v1/query", headers=AUTH, json={"query": "What is the risk status for the Tesla Model Y?"})
        assert response.status_code == 200
        assert response.json()["query_meta"]["generation_source"] == "maxkb"
        assert response.json()["query_meta"]["generation_status"] == "ok"
        output = response.json()["output"]
        assert output["consumer_signal"] == "Consumer risk status: open."
        assert output["business_impact"] is None and output["kol_impact"] is None
        assert response.json()["query_meta"]["semantic_fields"]["consumer_signal"]["source"] == "maxkb"
        assert response.json()["query_meta"]["semantic_fields"]["business_impact"]["source"] == "none"
        assert "[Evidence domain: c_current]" in prompts[0]["query"]
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
                return {"answer": '{"summary":"The model summarized the brand evidence.","consumer_signal":"Consumer evidence identifies Example Motors.",' \
                                '"business_impact":null,"kol_impact":null,"actions":["Review the brand field."]}'}

        client.app.state.adapter = Adapter()
        response = client.post("/api/v1/query", headers=AUTH, json={"query": "Which brands are represented?"})
        assert response.status_code == 200
        assert len(calls) == 1
        assert response.json()["output"]["summary"] == "The model summarized the brand evidence."
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
        response = client.post("/api/v1/query", headers=AUTH, json={"query": "What is the risk status for the Tesla Model Y?"})
        assert response.status_code == 200
        body = response.json()
        assert body["query_meta"]["generation_source"] == "deterministic"
        assert body["query_meta"]["generation_status"] == "degraded"
        assert body["query_meta"]["degraded_reason"] == "maxkb_schema_invalid"
        output = body["output"]
        assert output["summary"].startswith("Evidence-based fallback")
        assert output["consumer_signal"].startswith("Consumer evidence-based fallback")
        assert output["business_impact"] is None


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
        response = client.post("/api/v1/query", headers=AUTH, json={"query": "What is the risk status for the Tesla Model Y?"})
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
        response = client.post("/api/v1/query", headers=AUTH, json={"query": "What is the risk status for the Tesla Model Y?"})
        assert response.status_code == 200
        body = response.json()
        assert body["query_meta"]["generation_status"] == "degraded"
        assert body["query_meta"]["degraded_reason"] == "query_deadline_exceeded"
        assert body["query_meta"]["generation_source"] == "deterministic"
        assert body["output"]["summary"]
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
                return {"answer": '{"summary":"Semantic conclusion","consumer_signal":"Consumer domain summary","business_impact":null,"kol_impact":null,"actions":["Review the evidence."]}'}

        client.app.state.adapter = Adapter()
        response = client.post("/api/v1/query", headers=AUTH, json={"query": "What is the risk status for the Tesla Model Y?"})
        assert response.status_code == 200
        assert calls and "[Evidence domain: c_current]" in calls[0]["query"]
        # Shadow stays on the legacy response shape and does not surface the draft.
        assert response.json()["output"]["summary"] != "Semantic conclusion"


def test_no_evidence_does_not_call_semantic_model(tmp_path):
    with _semantic_client(tmp_path) as client:
        class Adapter:
            def search(self, **kwargs):
                return []

            def chat(self, **kwargs):
                raise AssertionError("no evidence must not call a model")

        client.app.state.adapter = Adapter()
        response = client.post("/api/v1/query", headers=AUTH, json={"query": "Which brands are represented?"})
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
        response = client.post("/api/v1/query", headers=AUTH, json={"query": "What recent consumer risks affect this vehicle?"})
        assert response.status_code == 200
        assert response.json()["clarification"]["required"] == ["brand", "vehicle_model"]
