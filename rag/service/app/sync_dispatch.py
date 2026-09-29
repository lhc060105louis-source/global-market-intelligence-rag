from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import logging
import threading

from .sync_tasks import AdapterFactory, SessionFactory, process_pending_tasks, queue_has_work


logger = logging.getLogger(__name__)


class SyncDispatcher:
    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        adapter_factory: AdapterFactory,
        enabled: bool,
        max_workers: int,
        batch_size: int,
        poll_interval_seconds: float,
        max_attempts: int,
    ) -> None:
        self._session_factory = session_factory
        self._adapter_factory = adapter_factory
        self._enabled = enabled
        self._max_workers = max(1, max_workers)
        self._batch_size = max(1, batch_size)
        self._poll_interval_seconds = max(0.1, poll_interval_seconds)
        self._max_attempts = max(1, max_attempts)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rag-sync-dispatch")
        self._state_lock = threading.Lock()
        self._wake_event = threading.Event()
        self._future: Future | None = None
        self._closed = False

    def kick(self) -> bool:
        if not self._enabled or self._closed:
            return False
        with self._state_lock:
            self._wake_event.set()
            if self._future is not None and not self._future.done():
                return False
            self._future = self._executor.submit(self._run)
            return True

    def close(self) -> None:
        with self._state_lock:
            self._closed = True
            self._wake_event.set()
        self._executor.shutdown(wait=True, cancel_futures=False)

    def _run(self) -> None:
        while not self._closed:
            self._wake_event.clear()
            try:
                process_pending_tasks(
                    self._session_factory,
                    self._adapter_factory,
                    max_workers=self._max_workers,
                    batch_size=self._batch_size,
                    poll_interval_seconds=self._poll_interval_seconds,
                    max_attempts=self._max_attempts,
                )
            except Exception:  # pragma: no cover - defensive logging for background loop
                logger.exception("sync dispatcher sweep failed")
                return
            if not queue_has_work(self._session_factory):
                if self._wake_event.wait(timeout=self._poll_interval_seconds):
                    continue
                if not queue_has_work(self._session_factory):
                    return
                continue
            if self._wake_event.wait(timeout=self._poll_interval_seconds):
                continue
