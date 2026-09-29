from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SyncEvent, SyncState


@dataclass(frozen=True)
class SyncRunResult:
    pushed: int
    pulled: int
    cursor: str


def _event_payload(event: SyncEvent) -> dict:
    return {
        "event_id": event.event_id,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "operation": event.operation,
        "version": event.version,
        "changed_at": event.changed_at.isoformat(),
        "changed_by_device": event.changed_by_device,
        "payload": event.payload,
    }


class SyncWorker:
    def __init__(self, session: Session, transport):
        self.session = session
        self.transport = transport

    def run_once(self) -> SyncRunResult:
        pending = list(
            self.session.scalars(
                select(SyncEvent)
                .where(SyncEvent.status == "pending")
                .order_by(SyncEvent.changed_at, SyncEvent.event_id)
            )
        )
        if pending:
            self.transport.push([_event_payload(event) for event in pending])
            for event in pending:
                event.status = "sent"
                event.last_error = None

        cursor_state = self.session.get(SyncState, "cursor")
        cursor = cursor_state.value if cursor_state else "0"
        result = self.transport.pull(cursor)
        new_cursor = str(result.get("cursor", cursor))
        if cursor_state is None:
            cursor_state = SyncState(key="cursor", value=new_cursor)
            self.session.add(cursor_state)
        else:
            cursor_state.value = new_cursor
        last_synced = self.session.get(SyncState, "last_synced_at")
        timestamp = datetime.now(timezone.utc).isoformat()
        if last_synced is None:
            self.session.add(SyncState(key="last_synced_at", value=timestamp))
        else:
            last_synced.value = timestamp
        self.session.commit()
        return SyncRunResult(
            pushed=len(pending),
            pulled=len(result.get("events", [])),
            cursor=new_cursor,
        )
