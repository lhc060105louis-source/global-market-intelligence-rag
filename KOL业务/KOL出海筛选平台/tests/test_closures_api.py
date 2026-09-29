def create_project(client):
    response = client.post(
        "/campaigns",
        json={
            "project_name": "XPENG G6 英国结案测试",
            "brand": "XPENG",
            "vehicle_model": "G6",
            "markets": ["GB"],
            "primary_market": "GB",
            "objectives": ["试驾传播", "有效留资"],
            "start_date": "2026-07-01",
            "end_date": "2026-08-31",
            "budget_total": 60000,
            "owner": "项目负责人",
            "milestones": [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_closure(client):
    project = create_project(client)
    response = client.post(
        f"/closures/campaigns/{project['campaign_id']}",
        json={"actor": "项目负责人", "actor_role": "project_owner"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def pass_all_checks(client, closure):
    response = client.put(
        f"/closures/{closure['closure_id']}/checks",
        json={
            "expected_revision": closure["revision"],
            "actor": "项目负责人",
            "actor_role": "project_owner",
            "items": [
                {
                    "check_key": item["key"],
                    "status": "通过",
                    "note": "测试环境人工核对确认",
                }
                for item in closure["checks"]
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def save_summary(client, closure):
    response = client.put(
        f"/closures/{closure['closure_id']}/summary",
        json={
            "expected_revision": closure["revision"],
            "actor": "业务分析",
            "actor_role": "business_analyst",
            "objective_result": "部分达成",
            "executive_summary": "项目完成主要内容发布，核心互动目标达成，留资仍需持续观察。",
            "key_results": "曝光和互动完成计划，转化口径沿用后期效果复盘。",
            "top_kols": "EVReviewUK 内容互动和执行配合较好。",
            "risk_kols": "无需要暂停合作的 KOL。",
            "lessons_learned": "应在签约阶段同步确认转化追踪方案。",
            "next_action": "下一轮保留核心 KOL，并提前锁定数据回收责任人。",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_closure_list_and_persistent_workspace(client):
    project = create_project(client)
    listed = client.get("/closures?brand=XPENG&market=GB")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["campaign_id"] == project["campaign_id"]

    first = client.post(
        f"/closures/campaigns/{project['campaign_id']}",
        json={"actor": "项目负责人", "actor_role": "project_owner"},
    )
    assert first.status_code == 201
    second = client.post(
        f"/closures/campaigns/{project['campaign_id']}",
        json={"actor": "项目负责人", "actor_role": "project_owner"},
    )
    assert second.json()["closure_id"] == first.json()["closure_id"]


def test_closure_check_issue_summary_and_approval_flow(client):
    closure = pass_all_checks(client, create_closure(client))
    assert closure["readiness"] == 100

    issue_response = client.post(
        f"/closures/{closure['closure_id']}/issues",
        json={
            "expected_revision": closure["revision"],
            "actor": "项目负责人",
            "actor_role": "project_owner",
            "issue_type": "数据",
            "title": "补齐最终留资去重结果",
            "description": "CRM 最终去重窗口尚未结束，需要补充最终数值。",
            "severity": "阻断",
            "owner": "数据负责人",
            "due_date": "2026-09-15",
            "source_reference": "后期效果复盘",
        },
    )
    assert issue_response.status_code == 201, issue_response.text
    closure = issue_response.json()["closure"]
    issue = closure["issues"][0]
    closure = save_summary(client, closure)

    blocked = client.post(
        f"/closures/{closure['closure_id']}/submit",
        json={
            "expected_revision": closure["revision"],
            "actor": "项目负责人",
            "actor_role": "project_owner",
        },
    )
    assert blocked.status_code == 422

    resolved = client.patch(
        f"/closures/{closure['closure_id']}/issues/{issue['issue_id']}",
        json={
            "expected_revision": closure["revision"],
            "actor": "数据负责人",
            "actor_role": "data_owner",
            "status": "已解决",
            "resolution_note": "最终结果已回收并完成去重核对。",
        },
    )
    assert resolved.status_code == 200, resolved.text
    closure = resolved.json()

    submitted = client.post(
        f"/closures/{closure['closure_id']}/submit",
        json={
            "expected_revision": closure["revision"],
            "actor": "项目负责人",
            "actor_role": "project_owner",
            "reason": "材料已齐全",
        },
    )
    assert submitted.status_code == 200, submitted.text
    closure = submitted.json()
    assert closure["status"] == "pending_confirmation"

    denied = client.post(
        f"/closures/{closure['closure_id']}/decision",
        json={
            "expected_revision": closure["revision"],
            "actor": "项目负责人",
            "actor_role": "project_owner",
            "decision": "确认结案",
        },
    )
    assert denied.status_code == 403

    closed = client.post(
        f"/closures/{closure['closure_id']}/decision",
        json={
            "expected_revision": closure["revision"],
            "actor": "品牌负责人",
            "actor_role": "brand_owner",
            "decision": "确认结案",
            "reason": "同意结案",
        },
    )
    assert closed.status_code == 200, closed.text
    closure = closed.json()
    assert closure["status"] == "closed"
    assert closure["closed_at"]

    archive = client.get(f"/closures/{closure['closure_id']}/archive")
    assert archive.status_code == 200
    assert archive.json()["read_only"] is True
    assert archive.json()["snapshots"]


def test_closed_closure_requires_revision_before_edit(client):
    closure = save_summary(client, pass_all_checks(client, create_closure(client)))
    closure = client.post(
        f"/closures/{closure['closure_id']}/submit",
        json={
            "expected_revision": closure["revision"],
            "actor": "项目负责人",
            "actor_role": "project_owner",
        },
    ).json()
    closure = client.post(
        f"/closures/{closure['closure_id']}/decision",
        json={
            "expected_revision": closure["revision"],
            "actor": "品牌负责人",
            "actor_role": "brand_owner",
            "decision": "确认结案",
        },
    ).json()

    edit = client.put(
        f"/closures/{closure['closure_id']}/checks",
        json={
            "expected_revision": closure["revision"],
            "actor": "项目负责人",
            "actor_role": "project_owner",
            "items": [{"check_key": "budget_confirmation", "status": "待确认"}],
        },
    )
    assert edit.status_code == 409

    revised = client.post(
        f"/closures/{closure['closure_id']}/revise",
        json={
            "expected_revision": closure["revision"],
            "actor": "项目负责人",
            "actor_role": "project_owner",
            "reason": "补充最终财务数据",
        },
    )
    assert revised.status_code == 200, revised.text
    assert revised.json()["version"] == 2


def test_closure_frontend_contract(client):
    html = client.get("/").text
    source = client.get("/static/closures.js")
    style = client.get("/static/closures.css")

    assert 'data-page="closures"' in html
    assert 'id="page-closures"' in html
    assert '<script src="/static/closures.js"></script>' in html
    assert '<link rel="stylesheet" href="/static/closures.css">' in html
    assert source.status_code == 200
    assert style.status_code == 200
    for view in ("overview", "checks", "archive"):
        assert f'data-closure-view="{view}"' in html
    for operation in (
        "loadClosureOverview",
        "openClosureItem",
        "saveClosureCheck",
        "addClosureIssue",
        "saveClosureSummary",
        "submitCurrentClosure",
        "decideCurrentClosure",
    ):
        assert f"function {operation}" in source.text or f"async function {operation}" in source.text
    assert "localStorage" not in source.text
