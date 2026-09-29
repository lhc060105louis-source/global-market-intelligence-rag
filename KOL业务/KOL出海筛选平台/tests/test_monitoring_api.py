def test_monitoring_overview(client):
    response = client.get("/monitoring/overview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["project"]["name"] == "BYD 德国新车上市传播项目"
    assert payload["metrics"] == {
        "total_tasks": 24,
        "on_time_rate": 87.5,
        "pending_review": 5,
        "pending_publish": 4,
        "published": 11,
        "open_risks": 3,
    }
    assert sum(stage["count"] for stage in payload["stages"]) == 24


def test_task_filter_and_detail(client):
    filtered = client.get("/monitoring/tasks", params={"stage": "审核中"})
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 5

    detail = client.get("/monitoring/tasks/TASK-006")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["kol_handle"] == "@EVReviewUK"
    assert payload["brief_checks"]["广告披露"] is False
    assert payload["risk_level"] == "高风险"


def test_risk_release_flow(client):
    blocked = client.post("/monitoring/tasks/TASK-006/approve")
    assert blocked.status_code == 409

    new_version = client.post("/monitoring/risks/RISK-20260804-017/actions/new-version")
    assert new_version.status_code == 200
    assert client.get("/monitoring/tasks/TASK-006").json()["brief_checks"]["广告披露"] is True

    legal = client.post("/monitoring/risks/RISK-20260804-017/actions/legal-review")
    assert legal.status_code == 200

    recheck = client.post("/monitoring/risks/RISK-20260804-017/actions/recheck")
    assert recheck.status_code == 200
    assert recheck.json()["status"] == "已关闭"
    assert recheck.json()["blocked"] is False

    approved = client.post("/monitoring/tasks/TASK-006/approve")
    assert approved.status_code == 200
    assert approved.json()["execution_stage"] == "待发布"


def test_monitoring_page(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert 'data-page="monitoring"' in html
    assert 'id="page-monitoring"' in html
    assert '/static/monitoring.js' in html
