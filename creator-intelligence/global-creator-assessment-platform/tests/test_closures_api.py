def create_project(client):
    response = client.post(
        "/campaigns",
        json={
            "project_name": "XPENG G6 United Kingdom Campaign Closure Test",
            "brand": "XPENG",
            "vehicle_model": "G6",
            "markets": ["GB"],
            "primary_market": "GB",
            "objectives": ["Test-Drive Reach", "Qualified Leads"],
            "start_date": "2026-07-01",
            "end_date": "2026-08-31",
            "budget_total": 60000,
            "owner": "Project Owner",
            "milestones": [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_closure(client):
    project = create_project(client)
    response = client.post(
        f"/closures/campaigns/{project['campaign_id']}",
        json={"actor": "Project Owner", "actor_role": "project_owner"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def pass_all_checks(client, closure):
    response = client.put(
        f"/closures/{closure['closure_id']}/checks",
        json={
            "expected_revision": closure["revision"],
            "actor": "Project Owner",
            "actor_role": "project_owner",
            "items": [
                {
                    "check_key": item["key"],
                    "status": "Passed",
                    "note": "Manually reviewed and confirmed in the test environment.",
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
            "actor": "Business Analyst",
            "actor_role": "business_analyst",
            "objective_result": "Partially Achieved",
            "executive_summary": "The campaign published its main content and achieved its core engagement target. Lead generation still requires monitoring.",
            "key_results": "Impressions and engagement met the plan; conversion definitions follow the post-campaign review.",
            "top_kols": "EVReviewUK delivered strong content engagement and execution coordination.",
            "risk_kols": "No creators require a partnership pause.",
            "lessons_learned": "Confirm the conversion tracking plan during contracting.",
            "next_action": "Retain core creators for the next round and assign data collection owners in advance.",
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
        json={"actor": "Project Owner", "actor_role": "project_owner"},
    )
    assert first.status_code == 201
    second = client.post(
        f"/closures/campaigns/{project['campaign_id']}",
        json={"actor": "Project Owner", "actor_role": "project_owner"},
    )
    assert second.json()["closure_id"] == first.json()["closure_id"]


def test_closure_check_issue_summary_and_approval_flow(client):
    closure = pass_all_checks(client, create_closure(client))
    assert closure["readiness"] == 100

    issue_response = client.post(
        f"/closures/{closure['closure_id']}/issues",
        json={
            "expected_revision": closure["revision"],
            "actor": "Project Owner",
            "actor_role": "project_owner",
            "issue_type": "Data",
            "title": "Add the Final Deduplicated Lead Count",
            "description": "The final CRM deduplication window is still open; add the final value when available.",
            "severity": "Critical",
            "owner": "Data Lead",
            "due_date": "2026-09-15",
            "source_reference": "Post-Campaign Review",
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
            "actor": "Project Owner",
            "actor_role": "project_owner",
        },
    )
    assert blocked.status_code == 422

    resolved = client.patch(
        f"/closures/{closure['closure_id']}/issues/{issue['issue_id']}",
        json={
            "expected_revision": closure["revision"],
            "actor": "Data Lead",
            "actor_role": "data_owner",
            "status": "Resolved",
            "resolution_note": "The final result has been collected and deduplication verified.",
        },
    )
    assert resolved.status_code == 200, resolved.text
    closure = resolved.json()

    submitted = client.post(
        f"/closures/{closure['closure_id']}/submit",
        json={
            "expected_revision": closure["revision"],
            "actor": "Project Owner",
            "actor_role": "project_owner",
            "reason": "All required materials are complete.",
        },
    )
    assert submitted.status_code == 200, submitted.text
    closure = submitted.json()
    assert closure["status"] == "pending_confirmation"

    denied = client.post(
        f"/closures/{closure['closure_id']}/decision",
        json={
            "expected_revision": closure["revision"],
            "actor": "Project Owner",
            "actor_role": "project_owner",
            "decision": "Confirm Closure",
        },
    )
    assert denied.status_code == 403

    closed = client.post(
        f"/closures/{closure['closure_id']}/decision",
        json={
            "expected_revision": closure["revision"],
            "actor": "Brand Owner",
            "actor_role": "brand_owner",
            "decision": "Confirm Closure",
            "reason": "Approved for closure.",
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
            "actor": "Project Owner",
            "actor_role": "project_owner",
        },
    ).json()
    closure = client.post(
        f"/closures/{closure['closure_id']}/decision",
        json={
            "expected_revision": closure["revision"],
            "actor": "Brand Owner",
            "actor_role": "brand_owner",
            "decision": "Confirm Closure",
        },
    ).json()

    edit = client.put(
        f"/closures/{closure['closure_id']}/checks",
        json={
            "expected_revision": closure["revision"],
            "actor": "Project Owner",
            "actor_role": "project_owner",
            "items": [{"check_key": "budget_confirmation", "status": "Unconfirmed"}],
        },
    )
    assert edit.status_code == 409

    revised = client.post(
        f"/closures/{closure['closure_id']}/revise",
        json={
            "expected_revision": closure["revision"],
            "actor": "Project Owner",
            "actor_role": "project_owner",
            "reason": "Add the final financial data.",
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
