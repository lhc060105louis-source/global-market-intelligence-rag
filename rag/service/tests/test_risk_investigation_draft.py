import json
from types import SimpleNamespace

import httpx

from app import risk_investigation


def test_ollama_draft_requests_structured_proposal(monkeypatch):
    captured = {}
    draft = {
        "summary": "Synthetic evidence suggests a cross-domain issue.",
        "domain_impacts": {"C": "Recall risk", "B": "Dealer bulletin", "KOL": "No validated evidence"},
        "evidence": ["record-1"],
        "evidence_gaps": ["Synthetic scenario only"],
        "limitations": ["Not for operational decisions"],
        "tasks": [{"owner_domain": "C", "task_type": "review", "assignee": None,
                   "expected_output_type": "assessment", "is_required": True}],
    }

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return httpx.Response(200, json={"message": {"content": json.dumps(draft)}},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(risk_investigation.httpx, "post", fake_post)
    result = risk_investigation._ollama_draft(
        SimpleNamespace(ollama_base_url="http://ollama.test", ollama_text_model="qwen2.5:3b"),
        {"risk": {"vehicle_model": "Atlas X7"}},
        [{"record_id": "record-1", "domain": "c_current", "preview": "Synthetic."}],
        10,
    )

    request = captured["json"]
    assert isinstance(request["format"], dict)
    assert request["format"]["additionalProperties"] is False
    assert result["evidence"] == ["record-1"]
    assert "untrusted data" in request["messages"][0]["content"]
    assert 'domain_impacts must be an object with C, B, and KOL string values' in request["messages"][0]["content"]
