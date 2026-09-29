from .base import AdapterResult


class FakeRAGAdapter:
    def __init__(self, mode: str = "success"):
        if mode not in {"success", "failure", "processing"}:
            raise ValueError("fake mode must be success, failure, or processing")
        self.mode = mode

    def _result(self, record_id: str | None = None) -> AdapterResult:
        if self.mode == "failure":
            return AdapterResult(status="failed", error_code="fake_failure", error_message="Fake adapter failure")
        if self.mode == "processing":
            suffix = record_id or "pending"
            return AdapterResult(status="processing", external_task_id=f"fake-task-{suffix}")
        return AdapterResult(
            status="indexed",
            external_document_id=f"fake-doc-{record_id}" if record_id else None,
        )

    def upsert_document(self, *, target: str, record_id: str, source_version: int, text: str) -> AdapterResult:
        return self._result(record_id)

    def set_document_active(self, *, external_document_id: str, active: bool, target: str | None = None) -> AdapterResult:
        record_id = external_document_id.removeprefix("fake-doc-")
        return self._result(record_id)

    def get_index_status(self, *, external_task_id: str, target: str | None = None) -> AdapterResult:
        record_id = external_task_id.removeprefix("fake-task-")
        return self._result(record_id)
