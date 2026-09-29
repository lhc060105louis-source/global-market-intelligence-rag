import importlib.util

from app.main import create_app


def test_mutation_and_outbox_event_commit_together(tmp_path):
    assert importlib.util.find_spec("app.sync.outbox") is not None
    from app.models import Kol, SyncEvent
    from app.sync.outbox import record_mutation

    app = create_app(f"sqlite:///{tmp_path / 'outbox.db'}")

    with app.state.session_factory() as session:
        kol = Kol(platform="YouTube", handle="@sync", country="GB")
        session.add(kol)
        session.flush()
        event = record_mutation(session, kol, "upsert")
        session.commit()

        stored = session.get(SyncEvent, event.event_id)
        assert stored is not None
        assert stored.entity_id == kol.sync_id
        assert stored.status == "pending"
        assert stored.payload["handle"] == "@sync"


def test_rolling_back_mutation_also_rolls_back_outbox_event(tmp_path):
    assert importlib.util.find_spec("app.sync.outbox") is not None
    from app.models import Kol, SyncEvent
    from app.sync.outbox import record_mutation

    app = create_app(f"sqlite:///{tmp_path / 'rollback.db'}")

    with app.state.session_factory() as session:
        kol = Kol(platform="YouTube", handle="@rollback", country="GB")
        session.add(kol)
        session.flush()
        record_mutation(session, kol, "upsert")
        session.rollback()

    with app.state.session_factory() as session:
        assert session.query(SyncEvent).count() == 0
        assert session.query(Kol).count() == 0


def test_kol_api_create_queues_sync_event(client):
    response = client.post(
        "/kols",
        json={"platform": "YouTube", "handle": "@queued", "country": "GB"},
    )
    assert response.status_code == 201

    from app.models import SyncEvent

    with client.app.state.session_factory() as session:
        events = session.query(SyncEvent).all()
        assert len(events) == 1
        assert events[0].entity_id == response.json()["sync_id"]
