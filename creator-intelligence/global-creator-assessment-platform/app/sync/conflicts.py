from app.sync.types import MergeDecision


KEY_FIELDS = {
    "kol": {"deleted_at"},
    "score_record": {
        "manual_score",
        "manual_evidence",
        "manual_source",
        "deleted_at",
    },
    "workflow": {"workflow_stage", "deleted_at"},
    "contract": {"status", "amount", "currency", "deleted_at"},
}


def resolve_remote_change(
    local: dict,
    remote: dict,
    entity_type: str = "kol",
) -> MergeDecision:
    local_version = int(local.get("version", 0))
    remote_version = int(remote.get("version", 0))
    if remote_version > local_version:
        return MergeDecision(kind="remote", fields=[])
    if local_version > remote_version:
        return MergeDecision(kind="local", fields=[])

    changed = sorted(
        field
        for field in KEY_FIELDS.get(entity_type, set())
        if local.get(field) != remote.get(field)
    )
    return MergeDecision(
        kind="manual" if changed else "local",
        fields=changed,
    )
