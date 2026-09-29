REQUIRED = {
    "entry_id", "entry_type", "title", "summary", "countries", "tags",
    "related_objects", "impact_conclusion", "action_suggestions",
    "external_sources", "status", "published_at", "version_no",
    "detail_url", "data_label",
}


def test_rag_entries_follow_versioned_contract(client):
    response = client.get("/api/rag/entries")
    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == "b-end-rag-entry/1.0"
    assert data["snapshot_id"].startswith("B-SNAPSHOT-")
    assert data["total"] == len(data["entries"])
    assert data["entries"]
    for entry in data["entries"]:
        assert REQUIRED <= entry.keys()
        assert entry["status"] == "published"
        assert entry["data_label"] == "演示数据"
        assert isinstance(entry["countries"], list)
        assert isinstance(entry["tags"], list)
        assert entry["detail_url"].startswith("/?page=")


def test_rag_snapshot_is_idempotent_and_filters_types(client):
    first = client.get("/api/rag/entries").json()
    second = client.get("/api/rag/entries").json()
    assert first["snapshot_id"] == second["snapshot_id"]
    policies = client.get("/api/rag/entries", params={"entry_type": "政策"}).json()
    assert policies["entries"]
    assert {entry["entry_type"] for entry in policies["entries"]} == {"政策"}


def test_unreviewed_rss_is_not_published_to_rag(client):
    data = client.get("/api/rag/entries").json()
    assert all("RSS" not in entry["tags"] for entry in data["entries"])
    health = client.get("/api/rag/health").json()
    assert health["unreviewed_rss_excluded"] is True
    assert health["by_type"]["市场"] == 0


def test_rag_detail_links_are_understood_by_frontend():
    from pathlib import Path
    html = (Path(__file__).parent.parent / "static" / "index.html").read_text(encoding="utf-8")
    assert "new URLSearchParams(location.search).get('page')" in html
    assert "loadPage(currentPage)" in html
