"""HTTP adapter for an unmodified MaxKB installation."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx

from .base import AdapterResult


class MaxKBError(RuntimeError):
    pass


logger = logging.getLogger(__name__)


class MaxKBRAGAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        api_token: str,
        workspace_id: str,
        knowledge_bases: dict[str, str] | None = None,
        applications: dict[str, str] | None = None,
        application_access_tokens: dict[str, str] | None = None,
        admin_username: str = "",
        admin_password: str = "",
        timeout: float = 45.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.admin_username = admin_username
        self.admin_password = admin_password
        self.workspace_id = workspace_id
        self.knowledge_bases = knowledge_bases or {}
        self.applications = applications or {}
        self.application_access_tokens = application_access_tokens or {}
        self._chat_tokens: dict[str, str] = {}
        self._auth_lock = threading.Lock()
        self.client = httpx.Client(base_url=self.base_url, timeout=timeout, transport=transport)
        self._tasks: dict[str, tuple[str, str]] = {}

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}

    def _can_login(self) -> bool:
        return bool(self.admin_username and self.admin_password)

    def _refresh_admin_token(self, *, timeout: float | None = None) -> None:
        if not self._can_login():
            raise MaxKBError(
                "MaxKB admin token expired and MAXKB_ADMIN_USERNAME/MAXKB_ADMIN_PASSWORD are not configured"
            )
        with self._auth_lock:
            kwargs: dict[str, Any] = {
                "json": {"username": self.admin_username, "password": self.admin_password},
            }
            if timeout is not None:
                kwargs["timeout"] = max(timeout, 0.01)
            response = self.client.request("POST", "/admin/api/user/login", **kwargs)
            if response.status_code >= 400:
                raise MaxKBError(f"MaxKB login failed: HTTP {response.status_code}: {response.text[:500]}")
            try:
                body = response.json()
            except ValueError as exc:  # pragma: no cover - defensive
                raise MaxKBError("MaxKB login did not return JSON") from exc
            data = body.get("data", body) if isinstance(body, dict) else body
            token = self._id(data, "token")
            if not token:
                raise MaxKBError("MaxKB login did not return a token")
            self.api_token = token

    def _request(self, method: str, path: str, *, retry_on_unauthorized: bool = True, **kwargs) -> Any:
        request_timeout = kwargs.get("timeout")
        deadline = None
        if isinstance(request_timeout, (int, float)):
            deadline = time.monotonic() + max(float(request_timeout), 0.01)

        def issue_request(request_kwargs: dict[str, Any]) -> httpx.Response:
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise httpx.TimeoutException("MaxKB request timeout budget exhausted")
                request_kwargs = dict(request_kwargs)
                request_kwargs["timeout"] = max(remaining, 0.01)
            return self.client.request(method, path, **request_kwargs)

        if path.startswith("/admin/api") and path != "/admin/api/user/login":
            headers = dict(kwargs.get("headers") or {})
            headers.update(self._headers())
            kwargs["headers"] = headers
        response = issue_request(kwargs)
        if (
            response.status_code == 401
            and retry_on_unauthorized
            and path.startswith("/admin/api")
            and path != "/admin/api/user/login"
        ):
            refresh_timeout = deadline - time.monotonic() if deadline is not None else None
            self._refresh_admin_token(timeout=refresh_timeout)
            headers = dict(kwargs.get("headers") or {})
            headers.update(self._headers())
            kwargs["headers"] = headers
            response = issue_request(kwargs)
        if response.status_code >= 400:
            raise MaxKBError(f"MaxKB HTTP {response.status_code}: {response.text[:500]}")
        try:
            body = response.json()
        except ValueError:
            return {}
        # MaxKB wraps successful payloads in {data: ...}; preserve unwrapped APIs too.
        return body.get("data", body) if isinstance(body, dict) else body

    @staticmethod
    def _id(value: Any, *keys: str) -> str | None:
        if isinstance(value, dict):
            for key in keys:
                if value.get(key) is not None:
                    return str(value[key])
        return str(value) if value is not None and not isinstance(value, (dict, list)) else None

    def _kb(self, target: str) -> str:
        kb = self.knowledge_bases.get(target)
        if not kb:
            raise MaxKBError(f"No MaxKB knowledge base configured for {target}")
        return kb

    def _list_documents(self, target: str) -> list[dict[str, Any]]:
        result = self._request(
            "GET",
            f"/admin/api/workspace/{self.workspace_id}/knowledge/{self._kb(target)}/document",
        )
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        if isinstance(result, dict):
            items = result.get("items", [])
            return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
        return []

    def _deactivate_stale_documents(
        self,
        *,
        target: str,
        record_id: str,
        source_version: int,
        keep_document_id: str,
    ) -> None:
        """Keep only the just-written version active for one RAG record.

        MaxKB's document creation endpoint returns a new document rather than
        updating the existing one. Without this cleanup, every current-record
        update leaves an older, still-searchable copy in the knowledge base.
        Cleanup is best-effort because the authoritative version is already
        stored in the RAG Hub database; a transient MaxKB listing/edit error
        must not turn a successful ingestion into a duplicate retry storm.
        """
        try:
            documents = self._list_documents(target)
            stale_ids: list[str] = []
            for document in documents:
                document_id = self._id(document, "id", "document_id")
                if not document_id or document_id == keep_document_id or document.get("is_active") is not True:
                    continue
                meta = document.get("meta") if isinstance(document.get("meta"), dict) else {}
                if str(meta.get("record_id") or "") != record_id:
                    continue
                try:
                    version = int(meta.get("source_version"))
                except (TypeError, ValueError):
                    continue
                if version <= source_version:
                    stale_ids.append(document_id)

            for document_id in stale_ids:
                self._request(
                    "PUT",
                    f"/admin/api/workspace/{self.workspace_id}/knowledge/{self._kb(target)}/document/{document_id}",
                    json={"is_active": False},
                )
        except (httpx.HTTPError, MaxKBError) as exc:
            logger.warning(
                "MaxKB stale-document cleanup failed for record_id=%s source_version=%s: %s",
                record_id,
                source_version,
                exc,
            )

    def upsert_document(
        self, *, target: str, record_id: str, source_version: int, text: str
    ) -> AdapterResult:
        kb = self._kb(target)
        # The original API's single-document endpoint reliably returns the document id;
        # batch_create may return an empty envelope while its post-hook is embedding.
        payload = {"name": f"{target}/{record_id}",
                   "meta": {"record_id": record_id, "source_version": source_version},
                   "paragraphs": [{"content": text, "title": ""}]}
        try:
            result = self._request(
                "POST",
                f"/admin/api/workspace/{self.workspace_id}/knowledge/{kb}/document",
                json=payload,
            )
            document_id = self._id(result, "id", "document_id")
            if document_id:
                task_id = f"maxkb-doc-{document_id}"
                self._tasks[task_id] = (kb, document_id)
                self._deactivate_stale_documents(
                    target=target,
                    record_id=record_id,
                    source_version=source_version,
                    keep_document_id=document_id,
                )
                status = str(result.get("status", "")).lower() if isinstance(result, dict) else ""
                indexed = any(token in status for token in ("success", "complete", "finish", "done"))
                return AdapterResult(
                    status="indexed" if indexed else "processing",
                    external_document_id=document_id,
                    external_task_id=None if indexed else task_id,
                )
            return AdapterResult(
                status="failed",
                error_code="maxkb_missing_document_id",
                error_message="MaxKB did not return document id",
            )
        except (httpx.HTTPError, MaxKBError) as exc:
            return AdapterResult(status="failed", error_code="maxkb_http_error", error_message=str(exc))

    def set_document_active(
        self, *, external_document_id: str, active: bool, target: str | None = None
    ) -> AdapterResult:
        # MaxKB exposes active state on the document edit endpoint.
        try:
            target_kb = self.knowledge_bases.get(target or "")
            if not target_kb:
                raise MaxKBError("No knowledge base configured")
            self._request(
                "PUT",
                f"/admin/api/workspace/{self.workspace_id}/knowledge/{target_kb}/document/{external_document_id}",
                json={"is_active": active},
            )
            return AdapterResult(status="indexed", external_document_id=external_document_id)
        except (httpx.HTTPError, MaxKBError) as exc:
            return AdapterResult(status="failed", error_code="maxkb_http_error", error_message=str(exc))

    def get_index_status(self, *, external_task_id: str, target: str | None = None) -> AdapterResult:
        relation = self._tasks.get(external_task_id)
        if relation is None:
            relation = self._recover_task_relation(external_task_id, target=target)
        if relation is None:
            return AdapterResult(status="processing", external_task_id=external_task_id,
                                 error_code="unknown_maxkb_task", error_message="Task was created by another process")
        kb, document_id = relation
        try:
            detail = self._request(
                "GET",
                f"/admin/api/workspace/{self.workspace_id}/knowledge/{kb}/document/{document_id}",
            )
            status = str(detail.get("status", detail.get("state", ""))).lower() if isinstance(detail, dict) else ""
            if any(token in status for token in ("fail", "error")):
                return AdapterResult(
                    status="failed",
                    external_document_id=document_id,
                    external_task_id=external_task_id,
                    error_code="maxkb_index_failed",
                    error_message=status,
                )
            if any(token in status for token in ("success", "complete", "finish", "done", "available")) or (
                isinstance(detail, dict) and detail.get("is_active") is True
            ):
                return AdapterResult(
                    status="indexed",
                    external_document_id=document_id,
                    external_task_id=external_task_id,
                )
            return AdapterResult(
                status="processing",
                external_document_id=document_id,
                external_task_id=external_task_id,
            )
        except (httpx.HTTPError, MaxKBError) as exc:
            return AdapterResult(
                status="failed",
                external_task_id=external_task_id,
                error_code="maxkb_http_error",
                error_message=str(exc),
            )

    def _recover_task_relation(self, external_task_id: str, *, target: str | None = None) -> tuple[str, str] | None:
        """Recover a document task after a service restart.

        Sync tasks are persisted in SQLite, while the adapter's short-lived
        task map is in memory. ``maxkb-doc-<document_id>`` carries the external
        document id, while ``target`` supplies the authoritative knowledge base
        from the RAG Hub record. Recovery must validate the returned document;
        some MaxKB versions return HTTP 200 with ``data: null`` for a document
        that is not in the requested knowledge base.
        """
        prefix = "maxkb-doc-"
        if not external_task_id.startswith(prefix):
            return None
        document_id = external_task_id[len(prefix):]
        if not document_id:
            return None
        configured_kb = self.knowledge_bases.get(target) if target else None
        candidates = [configured_kb] if configured_kb else list(self.knowledge_bases.values())
        for kb in candidates:
            if not kb:
                continue
            try:
                detail = self._request(
                    "GET",
                    f"/admin/api/workspace/{self.workspace_id}/knowledge/{kb}/document/{document_id}",
                )
            except MaxKBError as exc:
                # A 404 means this document belongs to another configured KB;
                # authentication and server errors must still surface.
                if "HTTP 404" in str(exc):
                    continue
                raise
            if not isinstance(detail, dict) or str(detail.get("id") or "") != document_id:
                continue
            detail_knowledge_id = str(detail.get("knowledge_id") or "")
            if detail_knowledge_id and detail_knowledge_id != kb:
                continue
            self._tasks[external_task_id] = (kb, document_id)
            return kb, document_id
        return None

    def search(
        self, *, target: str, query: str, top_k: int, similarity: float, timeout: float | None = None,
    ) -> list[dict]:
        kb = self._kb(target)
        kwargs: dict[str, Any] = {"json": {
            "workspace_id": self.workspace_id, "knowledge_id": kb, "query_text": query,
            "top_number": top_k, "similarity": similarity, "search_mode": "blend",
        }}
        if timeout is not None:
            kwargs["timeout"] = timeout
        result = self._request(
            "POST", f"/admin/api/workspace/{self.workspace_id}/knowledge/{kb}/hit_test", **kwargs,
        )
        return result if isinstance(result, list) else result.get("items", []) if isinstance(result, dict) else []

    def chat(self, *, application_id: str, query: str, context: str = "", timeout: float | None = None) -> dict:
        deadline = time.monotonic() + max(timeout, 0.01) if timeout is not None else None

        def remaining_timeout() -> float | None:
            if deadline is None:
                return None
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise httpx.TimeoutException("MaxKB chat timeout budget exhausted")
            return max(remaining, 0.01)

        messages = [{"role": "user", "content": query}]
        # The active semantic prompt already embeds the final evidence in the
        # user message. Do not send the same context a second time as a system
        # message; duplicating it increases local-model prefill cost and can
        # push a cross-domain request over its time budget.
        if context and context not in query:
            messages.insert(0, {"role": "system", "content": f"Use only this evidence:\n{context}"})
        access_token = next((token for app, token in self.application_access_tokens.items()
                             if self.applications.get(app) == application_id and token), "")
        if not access_token and not self._chat_tokens.get(application_id):
            raise MaxKBError(f"No MaxKB application access token configured for {application_id}")

        def resolve_chat_token(force_refresh: bool = False) -> str | None:
            chat_token = None if force_refresh else self._chat_tokens.get(application_id)
            if not chat_token and access_token:
                auth = self._request(
                    "POST", "/chat/api/auth/anonymous", json={"access_token": access_token},
                    **({"timeout": remaining_timeout()} if timeout is not None else {}),
                )
                chat_token = self._id(auth, "token") or (auth if isinstance(auth, str) else None)
                if chat_token:
                    self._chat_tokens[application_id] = chat_token
            return chat_token

        chat_token = resolve_chat_token()
        headers = {"Authorization": f"Bearer {chat_token}"} if chat_token else None
        response = self.client.request(
            "POST",
            f"/chat/api/{application_id}/chat/completions",
            headers=headers,
            json={"messages": messages, "stream": False},
            **({"timeout": remaining_timeout()} if timeout is not None else {}),
        )
        if response.status_code == 401 and access_token:
            self._chat_tokens.pop(application_id, None)
            chat_token = resolve_chat_token(force_refresh=True)
            headers = {"Authorization": f"Bearer {chat_token}"} if chat_token else None
            response = self.client.request(
                "POST",
                f"/chat/api/{application_id}/chat/completions",
                headers=headers,
                json={"messages": messages, "stream": False},
                **({"timeout": remaining_timeout()} if timeout is not None else {}),
            )
        if response.status_code >= 400:
            raise MaxKBError(f"MaxKB HTTP {response.status_code}: {response.text[:500]}")
        try:
            body = response.json()
        except ValueError:
            return {"answer": response.text}
        return body.get("data", body) if isinstance(body, dict) else {"answer": str(body)}
