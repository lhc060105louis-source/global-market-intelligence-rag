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
        json={"decision": "有条件批准", "note": "报价控制在上限内"},
    )
    assert response.status_code == 200

    saved = client.get("/reinvestment/evaluations/@AutoBildDE").json()
    assert saved["approval"]["decision"] == "有条件批准"


def test_reinvestment_portfolio(client):
    response = client.post("/reinvestment/portfolio/select", json={"scenario_id": "D"})
    assert response.status_code == 200
    data = client.get("/reinvestment/portfolio").json()
    assert data["selected_scenario"] == "D"


def test_reinvestment_governance(client):
    response = client.post(
        "/reinvestment/governance/@AutoBildDE",
        json={"status": "暂停", "reason": "等待主体风险补充核验"},
    )
    assert response.status_code == 200

    data = client.get("/reinvestment/evaluations/@AutoBildDE").json()
    assert data["major_risk"] is True
    assert data["suggestion_status"] == "暂停评估"


def test_reinvestment_action(client):
    task = client.get("/reinvestment/actions").json()["tasks"][0]
    response = client.post(
        f"/reinvestment/actions/{task['task_code']}",
        json={"status": "已完成"},
    )
    assert response.status_code == 200
