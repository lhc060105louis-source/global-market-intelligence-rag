def test_reinvestment_overview(client):
    response = client.get("/reinvestment/overview")
    assert response.status_code == 200
    data = response.json()
    assert data["metrics"]["total"] >= 5
    assert any(item["handle"] == "@AutoBildDE" for item in data["assets"])


def test_reinvestment_archive(client):
    response = client.get("/reinvestment/archives/@AutoBildDE")
    assert response.status_code == 200
    data = response.json()
    assert data["identity"]["handle"] == "@AutoBildDE"
    assert data["project_history"]


def test_reinvestment_approval(client):
    response = client.post(
        "/reinvestment/evaluations/@AutoBildDE/approval",
        json={"decision": "Conditionally Approved", "note": "Keep the quote within the cap."},
    )
    assert response.status_code == 200

    saved = client.get("/reinvestment/evaluations/@AutoBildDE").json()
    assert saved["approval"]["decision"] == "Conditionally Approved"


def test_reinvestment_portfolio(client):
    response = client.post("/reinvestment/portfolio/select", json={"scenario_id": "D"})
    assert response.status_code == 200
    data = client.get("/reinvestment/portfolio").json()
    assert data["selected_scenario"] == "D"


def test_reinvestment_governance(client):
    response = client.post(
        "/reinvestment/governance/@AutoBildDE",
        json={"status": "Paused", "reason": "Await additional verification of the entity-level risk."},
    )
    assert response.status_code == 200

    data = client.get("/reinvestment/evaluations/@AutoBildDE").json()
    assert data["major_risk"] is True
    assert data["suggestion_status"] == "Paused Assessment"


def test_reinvestment_action(client):
    task = client.get("/reinvestment/actions").json()["tasks"][0]
    response = client.post(
        f"/reinvestment/actions/{task['task_code']}",
        json={"status": "Completed"},
    )
    assert response.status_code == 200
