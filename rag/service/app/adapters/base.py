from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class AdapterResult:
    status: Literal["processing", "indexed", "failed"]
    external_document_id: str | None = None
    external_task_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class RAGAdapter(Protocol):
    def upsert_document(self, *, target: str, record_id: str, source_version: int, text: str) -> AdapterResult: ...

    def set_document_active(self, *, external_document_id: str, active: bool, target: str | None = None) -> AdapterResult: ...

    def get_index_status(self, *, external_task_id: str, target: str | None = None) -> AdapterResult: ...

    def search(self, *, target: str, query: str, top_k: int, similarity: float) -> list[dict]: ...

    def chat(self, *, application_id: str, query: str, context: str = "") -> dict: ...
