from conftest import auth_headers


def _payload(project_id=2):
    return {
        "project_id": project_id,
        "company_name": "Test Vehicle Manufacturer",
        "company_type": "Vehicle Manufacturer",
        "target_region": "Germany and neighboring markets",
        "project_stage": "Opportunity Assessment",
        "support_needs": ["Project eligibility assessment", "Local partner matching"],
        "current_challenge": "Determine within two weeks whether to commit resources to the tender.",
        "expected_result": "A practical market-entry decision and a checklist of required materials.",
        "materials_ready": ["Existing company credentials", "Full tender notice and attachments"],
        "target_deadline": "2026-09-15",
        "resource_commitment": "The project lead and compliance lead can respond within 24 hours.",
        "scope_confirmed": True,
        "cooperation_confirmed": True,
        "contact_name": "Jordan Lee",
        "contact_info": "wang@example.com",
    }


def test_sprint_application_requires_login(client):
    assert client.post("/api/sprints", json=_payload()).status_code == 401


def test_sprint_application_lifecycle(client, account):
    headers = auth_headers(account)
    created = client.post("/api/sprints", headers=headers, json=_payload())
    assert created.status_code == 201, created.text
    application = created.json()
    assert application["status"] == "submitted"
    assert application["support_needs"] == ["Project eligibility assessment", "Local partner matching"]
    assert application["materials_ready"] == ["Existing company credentials", "Full tender notice and attachments"]
    assert application["scope_confirmed"] is True
    assert application["cooperation_confirmed"] is True
    assert application["tasks"] == []
    application_id = application["id"]

    duplicate = client.post("/api/sprints", headers=headers, json=_payload())
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "sprint_already_exists"

    own_list = client.get("/api/sprints", headers=headers)
    assert own_list.status_code == 200
    assert any(item["id"] == application_id for item in own_list.json())
    assert client.post(f"/api/sprints/{application_id}/start", headers=headers).status_code == 403

    admin = client.post("/api/auth/demo-mode", json={"mode": "admin"}).json()
    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    started = client.post(f"/api/sprints/{application_id}/start", headers=admin_headers)
    assert started.status_code == 200, started.text
    workbench = started.json()
    assert workbench["status"] == "active"
    assert workbench["current_day"] == 1
    assert len(workbench["tasks"]) == 5

    task_id = workbench["tasks"][0]["id"]
    updated = client.patch(
        f"/api/sprints/{application_id}/tasks/{task_id}",
        headers=headers,
        json={"status": "completed"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["progress"] == 20
    assert updated.json()["tasks"][0]["status"] == "completed"


def test_sprint_application_is_organization_private(client, account):
    other = client.post("/api/auth/register", json={
        "email": "other-sprint@example.com",
        "password": "correct-horse-456",
        "display_name": "Other Organization",
    })
    assert other.status_code == 201, other.text
    other_data = other.json()
    rows = client.get("/api/sprints", headers=auth_headers(other_data))
    assert rows.status_code == 200
    assert rows.json() == []
    assert client.get("/api/sprints/1", headers=auth_headers(other_data)).status_code == 403


def test_sprint_validates_project_and_task_state(client, account):
    headers = auth_headers(account)
    missing = client.post("/api/sprints", headers=headers, json=_payload(99999))
    assert missing.status_code == 404
    invalid = client.patch("/api/sprints/1/tasks/1", headers=headers, json={"status": "unknown"})
    assert invalid.status_code == 422


def test_sprint_requires_scope_and_cooperation_confirmation(client, account):
    payload = _payload(3)
    payload["scope_confirmed"] = False
    response = client.post("/api/sprints", headers=auth_headers(account), json=payload)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "service_terms_not_confirmed"
