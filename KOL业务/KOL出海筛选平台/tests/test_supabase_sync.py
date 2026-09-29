import httpx

from app.main import create_app
from app.models import Kol, SyncEvent
from app.sync.outbox import record_mutation


class FakeTransport:
    def __init__(self):
        self.pushed = []

    def push(self, events):
        self.pushed.extend(events)

    def pull(self, cursor):
        assert cursor == "0"
        return {"events": [], "cursor": "18"}


def test_worker_pushes_pending_events_and_advances_cursor(tmp_path):
    from app.sync.worker import SyncWorker

    app = create_app(f"sqlite:///{tmp_path / 'worker.db'}")
    with app.state.session_factory() as session:
        kol = Kol(platform="YouTube", handle="@worker", country="GB")
        session.add(kol)
        session.flush()
        record_mutation(session, kol, "upsert")
        session.commit()

        transport = FakeTransport()
        result = SyncWorker(session, transport).run_once()

        assert result.pushed == 1
        assert result.cursor == "18"
        assert session.query(SyncEvent).one().status == "sent"


def test_supabase_transport_uses_bearer_header_not_payload():
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(201, json=[])
        return httpx.Response(200, json={"events": [], "cursor": "1"})

    from app.sync.supabase import SupabaseTransport

    transport = SupabaseTransport(
        url="https://team.supabase.co",
        anon_key="anon-secret",
        access_token="user-secret",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    transport.push([{"event_id": "one", "payload": {"name": "EV"}}])
    result = transport.pull("0")

    assert result["cursor"] == "1"
    assert requests[0].headers["authorization"] == "Bearer user-secret"
    assert b"user-secret" not in requests[0].content
