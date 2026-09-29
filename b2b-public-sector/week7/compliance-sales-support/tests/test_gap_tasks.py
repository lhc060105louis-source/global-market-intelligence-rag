def _demo_headers(client, mode="professional"):
    data = client.post("/api/auth/demo-mode", json={"mode": mode}).json()
    return {"Authorization": f"Bearer {data['access_token']}"}


def _project_and_profile(client, headers):
    project_id = client.get("/api/projects", headers=headers).json()[0]["id"]
    profiles = client.get("/api/matching/profiles", headers=headers).json()
    return project_id, profiles[1]["id"]


def test_admission_gaps_create_idempotent_project_tasks(client):
    headers = _demo_headers(client)
    project_id, profile_id = _project_and_profile(client, headers)
    admission = client.get(
        f"/api/matching/match/{project_id}", params={"profile_id": profile_id}, headers=headers
    ).json()
    expected = [row for row in admission["requirement_gap_matrix"] if row["status"] != "satisfied"]

    first = client.post(
        f"/api/tasks/from-gaps/{project_id}", json={"profile_id": profile_id}, headers=headers
    )
    assert first.status_code == 201, first.text
    result = first.json()
    assert result["created_count"] == len(expected)
    assert result["skipped_count"] == 0
    assert {task["gap_code"] for task in result["tasks"]} == {row["code"] for row in expected}
    assert all(task["source_type"] == "admission_gap" for task in result["tasks"])
    assert all(task["owner_role"] and task["due_date"] for task in result["tasks"])

    duplicate = client.post(
        f"/api/tasks/from-gaps/{project_id}", json={"profile_id": profile_id}, headers=headers
    ).json()
    assert duplicate["created_count"] == 0
    assert duplicate["skipped_count"] == len(expected)


def test_gap_tasks_can_be_listed_and_updated(client):
    headers = _demo_headers(client)
    project_id, profile_id = _project_and_profile(client, headers)
    client.post(f"/api/tasks/from-gaps/{project_id}", json={"profile_id": profile_id}, headers=headers)
    tasks = client.get("/api/tasks", params={"project_id": project_id}, headers=headers).json()
    assert tasks
    task = tasks[0]
    assert task["project_name"]
    assert task["profile_name"]

    updated = client.patch(f"/api/tasks/{task['id']}", json={"status": "in_progress"}, headers=headers)
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "in_progress"
    assert client.patch(f"/api/tasks/{task['id']}", json={"status": "unknown"}, headers=headers).status_code == 422


def test_gap_task_selection_validation_and_access(client):
    headers = _demo_headers(client)
    project_id, profile_id = _project_and_profile(client, headers)
    invalid = client.post(
        f"/api/tasks/from-gaps/{project_id}",
        json={"profile_id": profile_id, "gap_codes": ["REQ-99"]}, headers=headers,
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "invalid_gap_codes"

    free = client.post("/api/auth/register", json={
        "email": "gap-task-free@example.com", "password": "correct-horse-123",
        "display_name": "Free Plan Task User", "organization_name": "Free Plan Task Organization",
    }).json()
    free_headers = {"Authorization": f"Bearer {free['access_token']}"}
    assert client.post(
        f"/api/tasks/from-gaps/{project_id}", json={"profile_id": profile_id}, headers=free_headers
    ).status_code == 403
    assert client.get("/api/tasks").status_code == 401


def test_project_tasks_are_isolated_by_organization(client):
    professional = _demo_headers(client, "professional")
    project_id, profile_id = _project_and_profile(client, professional)
    client.post(f"/api/tasks/from-gaps/{project_id}", json={"profile_id": profile_id}, headers=professional)
    enterprise = _demo_headers(client, "enterprise")
    assert client.get("/api/tasks", headers=enterprise).json() == []
