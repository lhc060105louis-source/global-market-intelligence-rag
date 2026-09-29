import json
from datetime import datetime, timezone

from db import get_session
from models import IntelligenceItem, Project, RagEventOutbox


def _admin_headers(client):
    data = client.post("/api/auth/demo-mode", json={"mode": "admin"}).json()
    return {"Authorization": f"Bearer {data['access_token']}"}


def test_new_project_stays_draft_until_explicit_publish(client):
    headers = _admin_headers(client)
    created = client.post("/api/projects", headers=headers, json={
        "project_name": "RAG 主动推送测试项目", "country": "DE",
        "contracting_authority": "Test Authority", "description": "测试摘要",
        "source_url": "https://example.com/procurement",
        "scale_score": 12, "authority_score": 6, "technical_score": 16,
        "compliance_score": 12, "local_score": 8, "conversion_score": 16,
        "competition_score": 6,
    })
    assert created.status_code == 200, created.text
    project_id = created.json()["id"]
    with get_session() as session:
        project = session.get(Project, project_id)
        assert project.rag_status == "draft"
        assert session.query(RagEventOutbox).filter(RagEventOutbox.upstream_id == f"B-PRJ-{project_id}").count() == 0

    published = client.post(f"/api/projects/{project_id}/publish", headers=headers)
    assert published.status_code == 200, published.text
    assert published.json()["version_no"] == "v1"
    assert published.json()["rag_event"]["status"] == "disabled"
    with get_session() as session:
        event = session.query(RagEventOutbox).filter(RagEventOutbox.upstream_id == f"B-PRJ-{project_id}").one()
        payload = json.loads(event.payload)
        assert payload["source_system"] == "B"
        assert payload["record_type"] == "business_procurement"
        assert payload["event_type"] == "update_current"
        assert payload["source_record_id"] == f"B-PRJ-{project_id}"
        assert payload["source_version"] == 1
        assert payload["push_id"] == event.event_id
        assert payload["source_url"].endswith(f"/?page=projects&record_id={project_id}")
        assert payload["payload"]["entry_type"] == "procurement"
        assert payload["payload"]["publication_status"] == "published"
        assert payload["payload"]["regions"] == ["DE"]
        assert payload["effective_at"].endswith("Z")
        assert payload["source_updated_at"].endswith("Z")


def test_rss_requires_review_and_archive_emits_event(client):
    headers = _admin_headers(client)
    with get_session() as session:
        item = IntelligenceItem(
            source="Test RSS", title="待人工确认的市场线索",
            link="https://example.com/rss-review-test", summary="原始抓取摘要",
            published_at=datetime.now(timezone.utc), review_status="draft",
        )
        session.add(item); session.commit(); session.refresh(item); item_id = item.id

    before = client.get("/api/rag/entries?entry_type=市场").json()
    assert all(entry["entry_id"] != f"B-INT-{item_id}" for entry in before["entries"])

    assert client.post(f"/api/intelligence/{item_id}/publish", headers=headers).status_code == 422
    published = client.post(f"/api/intelligence/{item_id}/publish?region=EU", headers=headers)
    assert published.status_code == 200, published.text
    after = client.get("/api/rag/entries?entry_type=市场").json()
    assert any(entry["entry_id"] == f"B-INT-{item_id}" for entry in after["entries"])
    archived = client.post(f"/api/intelligence/{item_id}/archive", headers=headers)
    assert archived.status_code == 200, archived.text
    with get_session() as session:
        events = session.query(RagEventOutbox).filter(
            RagEventOutbox.upstream_id == f"B-INT-{item_id}"
        ).order_by(RagEventOutbox.id).all()
        assert [event.event_type for event in events] == ["update_current", "archive"]
        archive_payload = json.loads(events[-1].payload)
        assert archive_payload["event_type"] == "archive"
        assert archive_payload["payload"]["publication_status"] == "published"
        assert archive_payload["source_version"] == 2


def test_regulation_keeps_business_version_and_uses_integer_rag_version(client):
    headers = _admin_headers(client)
    body = {
        "regulation_id": "RAG-VERSION-TEST", "name": "法规版本测试",
        "status": "已审核", "version": "v1.2", "scope": "EU",
        "official_source": "https://example.com/regulation", "issuer": "EU",
        "core_requirement": "正式要求",
    }
    first = client.post("/api/regulations", headers=headers, json=body)
    assert first.status_code == 200, first.text
    second = client.post("/api/regulations", headers=headers, json={**body, "core_requirement": "更新要求"})
    assert second.status_code == 200, second.text
    from models import Regulation
    with get_session() as session:
        regulation = session.get(Regulation, "RAG-VERSION-TEST")
        assert regulation.version == "v1.2"
        assert regulation.rag_version == 2
        events = session.query(RagEventOutbox).filter(
            RagEventOutbox.upstream_id == "B-REG-RAG-VERSION-TEST"
        ).order_by(RagEventOutbox.id).all()
        assert [json.loads(event.payload)["source_version"] for event in events] == [1, 2]


def test_outbox_is_admin_only(client):
    assert client.get("/api/rag/outbox").status_code == 401
    headers = _admin_headers(client)
    assert client.get("/api/rag/outbox", headers=headers).status_code == 200
