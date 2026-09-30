from __future__ import annotations

import json
from types import SimpleNamespace

import httpx

from app import risk_investigation


def test_ollama_proposal_is_told_not_to_repeat_completed_tools(monkeypatch):
    captured: dict = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return httpx.Response(
            200,
            json={
                "message": {"content": json.dumps({
                    "tool": "search_domain",
                    "arguments": {"target": "b_business", "query": "Atlas X7 brake hose"},
                })}
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(risk_investigation.httpx, "post", fake_post)
    settings = SimpleNamespace(ollama_base_url="http://ollama.test", ollama_text_model="qwen2.5:3b")

    result = risk_investigation._ollama_proposal(
        settings,
        {"risk": {"vehicle_model": "Atlas X7"}},
        [],
        5,
        10,
        completed_tools=[
            {"tool": "get_risk_context", "arguments": {}},
            {"tool": "search_domain", "arguments": {"target": "b_business", "query": "Atlas X7 brake hose"}},
        ],
    )

    messages = captured["json"]["messages"]
    planner_state = json.loads(messages[1]["content"])
    assert planner_state["completed_tool_calls"][0]["tool"] == "get_risk_context"
    assert planner_state["completed_tool_calls"][1]["arguments"]["target"] == "b_business"
    assert "already supplied" in messages[0]["content"]
    assert "identical tool name and arguments" in messages[0]["content"]
    assert result["tool"] == "search_domain"
