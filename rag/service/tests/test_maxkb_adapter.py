from __future__ import annotations

import httpx
import json

from app.adapters.maxkb import MaxKBRAGAdapter


def test_maxkb_adapter_refreshes_admin_token_after_401():
    calls: list[tuple[str, str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("authorization")
        calls.append((request.method, request.url.path, auth))
        if request.method == "POST" and request.url.path == "/admin/api/workspace/ws-1/knowledge/kb-1/document":
            if auth == "Bearer stale-token":
                return httpx.Response(401, json={"message": "expired"})
            if auth == "Bearer fresh-token":
                return httpx.Response(200, json={"data": {"id": "doc-1", "status": "success"}})
        if request.url.path == "/admin/api/workspace/ws-1/knowledge/kb-1/document" and request.method == "GET":
            return httpx.Response(200, json={"data": []})
        if request.url.path == "/admin/api/user/login":
            return httpx.Response(200, json={"data": {"token": "fresh-token"}})
        raise AssertionError(f"unexpected request: {request.method} {request.url.path} {auth}")

    adapter = MaxKBRAGAdapter(
        base_url="http://maxkb.test",
        api_token="stale-token",
        admin_username="admin",
        admin_password="secret",
        workspace_id="ws-1",
        knowledge_bases={"c_current": "kb-1"},
        transport=httpx.MockTransport(handler),
    )

    result = adapter.upsert_document(target="c_current", record_id="record-1", source_version=1, text="hello")

    assert result.status == "indexed"
    assert result.external_document_id == "doc-1"
    assert calls == [
        ("POST", "/admin/api/workspace/ws-1/knowledge/kb-1/document", "Bearer stale-token"),
        ("POST", "/admin/api/user/login", None),
        ("POST", "/admin/api/workspace/ws-1/knowledge/kb-1/document", "Bearer fresh-token"),
        ("GET", "/admin/api/workspace/ws-1/knowledge/kb-1/document", "Bearer fresh-token"),
    ]


def test_maxkb_adapter_deactivates_older_versions_for_same_record():
    calls: list[tuple[str, str, str | None, dict | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("authorization")
        body = json.loads(request.content.decode("utf-8")) if request.content else None
        calls.append((request.method, request.url.path, auth, body))
        if request.method == "POST" and request.url.path.endswith("/knowledge/kb-1/document"):
            return httpx.Response(200, json={"data": {"id": "doc-new", "status": "success"}})
        if request.method == "GET" and request.url.path.endswith("/knowledge/kb-1/document"):
            return httpx.Response(200, json={"data": [
                {"id": "doc-old", "is_active": True, "meta": {"record_id": "record-1", "source_version": 30}},
                {"id": "doc-new", "is_active": True, "meta": {"record_id": "record-1", "source_version": 31}},
                {"id": "unrelated", "is_active": True, "meta": {"record_id": "other", "source_version": 1}},
            ]})
        if request.method == "PUT" and request.url.path.endswith("/document/doc-old"):
            return httpx.Response(200, json={"data": {"id": "doc-old", "is_active": False}})
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    adapter = MaxKBRAGAdapter(
        base_url="http://maxkb.test",
        api_token="token",
        workspace_id="ws-1",
        knowledge_bases={"c_current": "kb-1"},
        transport=httpx.MockTransport(handler),
    )

    result = adapter.upsert_document(target="c_current", record_id="record-1", source_version=31, text="updated")

    assert result.status == "indexed"
    assert result.external_document_id == "doc-new"
    assert calls == [
        (
            "POST",
            "/admin/api/workspace/ws-1/knowledge/kb-1/document",
            "Bearer token",
            {
                "name": "c_current/record-1",
                "meta": {"record_id": "record-1", "source_version": 31},
                "paragraphs": [{"content": "updated", "title": ""}],
            },
        ),
        ("GET", "/admin/api/workspace/ws-1/knowledge/kb-1/document", "Bearer token", None),
        ("PUT", "/admin/api/workspace/ws-1/knowledge/kb-1/document/doc-old", "Bearer token", {"is_active": False}),
    ]


def test_maxkb_adapter_recovers_document_only_in_target_knowledge_base():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/knowledge/kb-b/document/doc-1"):
            return httpx.Response(200, json={"data": {
                "id": "doc-1", "knowledge_id": "kb-b", "status": "nnn2", "is_active": True,
            }})
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    adapter = MaxKBRAGAdapter(
        base_url="http://maxkb.test",
        api_token="token",
        workspace_id="ws-1",
        knowledge_bases={"c_current": "kb-c", "b_business": "kb-b"},
        transport=httpx.MockTransport(handler),
    )

    result = adapter.get_index_status(external_task_id="maxkb-doc-doc-1", target="b_business")

    assert result.status == "indexed"
    assert result.external_document_id == "doc-1"
    assert calls == [
        "/admin/api/workspace/ws-1/knowledge/kb-b/document/doc-1",
        "/admin/api/workspace/ws-1/knowledge/kb-b/document/doc-1",
    ]


def test_maxkb_adapter_does_not_treat_empty_document_response_as_mapping():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": None})

    adapter = MaxKBRAGAdapter(
        base_url="http://maxkb.test",
        api_token="token",
        workspace_id="ws-1",
        knowledge_bases={"b_business": "kb-b"},
        transport=httpx.MockTransport(handler),
    )

    result = adapter.get_index_status(external_task_id="maxkb-doc-doc-1", target="b_business")

    assert result.status == "processing"
    assert result.error_code == "unknown_maxkb_task"


def test_maxkb_chat_does_not_duplicate_context_already_embedded_in_query():
    chat_requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/chat/api/auth/anonymous":
            return httpx.Response(200, json={"data": {"token": "chat-token"}})
        if request.url.path == "/chat/api/app-1/chat/completions":
            chat_requests.append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(200, json={"data": {"answer": "ok"}})
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    adapter = MaxKBRAGAdapter(
        base_url="http://maxkb.test",
        api_token="token",
        workspace_id="ws-1",
        applications={"cross_domain": "app-1"},
        application_access_tokens={"cross_domain": "access-token"},
        transport=httpx.MockTransport(handler),
    )

    result = adapter.chat(
        application_id="app-1",
        query="只按证据回答。\n最终证据：C1",
        context="最终证据：C1",
    )

    assert result["answer"] == "ok"
    assert len(chat_requests) == 1
    assert chat_requests[0]["messages"] == [{
        "role": "user", "content": "只按证据回答。\n最终证据：C1",
    }]
