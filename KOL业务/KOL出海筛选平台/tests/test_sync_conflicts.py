import importlib.util


def test_key_field_conflict_requires_user_choice():
    assert importlib.util.find_spec("app.sync.conflicts") is not None
    from app.sync.conflicts import resolve_remote_change

    decision = resolve_remote_change(
        local={"version": 4, "workflow_stage": 3},
        remote={"version": 4, "workflow_stage": 4},
        entity_type="workflow",
    )

    assert decision.kind == "manual"
    assert decision.fields == ["workflow_stage"]


def test_newer_ordinary_field_uses_remote_value():
    assert importlib.util.find_spec("app.sync.conflicts") is not None
    from app.sync.conflicts import resolve_remote_change

    decision = resolve_remote_change(
        local={"version": 3, "name": "Old"},
        remote={"version": 4, "name": "New"},
        entity_type="kol",
    )

    assert decision.kind == "remote"
    assert decision.fields == []


def test_soft_delete_is_a_key_conflict_at_equal_version():
    assert importlib.util.find_spec("app.sync.conflicts") is not None
    from app.sync.conflicts import resolve_remote_change

    decision = resolve_remote_change(
        local={"version": 5, "deleted_at": None},
        remote={"version": 5, "deleted_at": "2026-07-29T10:00:00Z"},
        entity_type="kol",
    )

    assert decision.kind == "manual"
    assert decision.fields == ["deleted_at"]
