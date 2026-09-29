def create_project(client, **overrides):
    payload = {
        "project_name": "XPENG G6 United Kingdom Test-Drive Reach Campaign",
        "brand": "XPENG",
        "vehicle_model": "G6",
        "markets": ["GB"],
        "primary_market": "GB",
        "objectives": ["Test Drives", "Lead Generation"],
        "start_date": "2026-10-01",
        "end_date": "2026-11-15",
        "budget_total": 60000,
        "owner": "Project Owner",
        "milestones": [
            {"name": "Campaign Approval", "planned_date": "2026-10-02", "owner": "Project Owner"},
            {"name": "Content Publication", "planned_date": "2026-11-01", "owner": "Content Lead"},
        ],
    }
    payload.update(overrides)
    response = client.post("/campaigns", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def fill_required_sections(client, project):
    campaign_id = project["campaign_id"]
    strategy = client.put(
        f"/campaigns/{campaign_id}/strategy",
        json={
            "expected_revision": project["revision"],
            "audiences": [
                {
                    "name": "United Kingdom Urban Families Considering Electric Vehicles",
                    "market": "GB",
                    "language": "English",
                    "purchase_stage": "Consideration",
                    "priority": "core",
                }
            ],
            "platforms": ["YouTube"],
            "content_formats": ["In-depth Test Drive"],
            "message_pillars": ["Space and Charging Experience"],
            "prohibited_claims": ["Unverified driving-range data"],
            "cta": "Book a Test Drive",
            "disclosure_rule": "Clearly disclose the commercial partnership.",
            "risk_reviewer": "Compliance Lead",
        },
    )
    assert strategy.status_code == 200, strategy.text
    project = strategy.json()

    measurement = client.put(
        f"/campaigns/{campaign_id}/measurement-plan",
        json={
            "expected_revision": project["revision"],
            "items": [
                {
                    "metric_code": "leads",
                    "name": "Qualified Leads",
                    "target_value": 500,
                    "unit": "people",
                    "formula": "Deduplicated number of qualified CRM leads",
                    "data_source": "CRM",
                    "data_status": "manual",
                    "observation_window": "30 days after publication",
                    "owner": "Data Lead",
                    "refresh_frequency": "Daily",
                    "is_primary": True,
                }
            ],
        },
    )
    assert measurement.status_code == 200, measurement.text
    project = measurement.json()

    requirements = client.put(
        f"/campaigns/{campaign_id}/kol-requirements",
        json={
            "expected_revision": project["revision"],
            "roles": [
                {
                    "role_code": "reviewer",
                    "role_name": "Expert Reviewer",
                    "market": "GB",
                    "platform": "YouTube",
                    "required_count": 2,
                    "content_format": "In-depth Test Drive",
                    "audience_requirement": "The share of United Kingdom electric vehicle audiences must be verifiable.",
                    "score_preferences": ["Audience Fit", "Expertise"],
                    "risk_threshold": "Any critical entity-level risk blocks participation.",
                    "quote_min": 10000,
                    "quote_cap": 18000,
                    "estimated": True,
                }
            ],
            "budget_items": [
                {"category": "Creator Partnership Fees", "amount": 36000, "estimated": True},
                {"category": "Monitoring and Tools", "amount": 4000, "estimated": False},
            ],
        },
    )
    assert requirements.status_code == 200, requirements.text
    return requirements.json()


def test_campaign_defaults_and_persistence(client):
    project = create_project(client)
    assert project["currency"] == "GBP"
    assert project["timezone"] == "Europe/London"
    assert project["status"] == "draft"
    assert project["current_version"] == 1
    assert project["configuration"]["basic"]["milestones"][0]["name"] == "Campaign Approval"

    listed = client.get("/campaigns?brand=XPENG&market=GB")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    loaded = client.get(f"/campaigns/{project['campaign_id']}").json()
    assert loaded["project_name"] == project["project_name"]


def test_version_conflict_and_archive_restore(client):
    project = create_project(client)
    stale = client.patch(
        f"/campaigns/{project['campaign_id']}",
        json={"expected_revision": 99, "project_name": "Invalid overwrite"},
    )
    assert stale.status_code == 409
    assert "Version conflict" in stale.json()["detail"]

    archived = client.post(
        f"/campaigns/{project['campaign_id']}/archive",
        json={"expected_revision": project["revision"]},
    )
    assert archived.status_code == 200
    archived_project = archived.json()
    assert archived_project["status"] == "archived"
    assert client.get("/campaigns").json()["total"] == 0
    assert client.get("/campaigns?include_archived=true").json()["total"] == 1

    restored = client.post(
        f"/campaigns/{project['campaign_id']}/restore",
        json={"expected_revision": archived_project["revision"]},
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "draft"


def test_budget_validation_blocks_submission(client):
    project = create_project(client, budget_total=10000)
    response = client.put(
        f"/campaigns/{project['campaign_id']}/kol-requirements",
        json={
            "expected_revision": project["revision"],
            "roles": [],
            "budget_items": [{"category": "Creator Partnership Fees", "amount": 12000}],
        },
    )
    assert response.status_code == 200
    project = response.json()
    checked = client.post(f"/campaigns/{project['campaign_id']}/validate")
    assert checked.status_code == 200
    assert checked.json()["valid"] is False
    assert "budget_exceeded" in {item["code"] for item in checked.json()["errors"]}

    submitted = client.post(
        f"/campaigns/{project['campaign_id']}/submit",
        json={"expected_revision": project["revision"]},
    )
    assert submitted.status_code == 422
    assert submitted.json()["detail"]["message"] == "Campaign configuration did not pass pre-approval validation."


def test_approval_freeze_publish_and_new_revision(client):
    project = fill_required_sections(client, create_project(client))
    checked = client.post(f"/campaigns/{project['campaign_id']}/validate").json()
    assert checked["valid"] is True

    submitted = client.post(
        f"/campaigns/{project['campaign_id']}/submit",
        json={"expected_revision": project["revision"], "actor": "Project Owner"},
    )
    assert submitted.status_code == 200, submitted.text
    project = submitted.json()
    assert project["status"] == "pending_approval"

    unauthorized = client.post(
        f"/campaigns/{project['campaign_id']}/decision",
        json={
            "expected_revision": project["revision"],
            "decision": "approve",
            "actor_role": "business_analyst",
            "risk_signoff": True,
        },
    )
    assert unauthorized.status_code == 403

    missing_signoff = client.post(
        f"/campaigns/{project['campaign_id']}/decision",
        json={
            "expected_revision": project["revision"],
            "decision": "approve",
            "actor_role": "brand_owner",
        },
    )
    assert missing_signoff.status_code == 409

    approved = client.post(
        f"/campaigns/{project['campaign_id']}/decision",
        json={
            "expected_revision": project["revision"],
            "decision": "approve",
            "actor": "Brand Owner",
            "actor_role": "brand_owner",
            "risk_signoff": True,
        },
    )
    assert approved.status_code == 200, approved.text
    project = approved.json()
    assert project["status"] == "approved"
    assert project["approved_version"] == 1
    assert project["versions"][0]["is_frozen"] is True

    published = client.post(
        f"/campaigns/{project['campaign_id']}/publish",
        json={"actor": "Project Owner", "actor_role": "project_owner"},
    )
    assert published.status_code == 200, published.text
    assert len(published.json()["items"]) == 6
    monitoring = client.get(
        f"/campaigns/{project['campaign_id']}/handoffs/monitoring"
    )
    assert monitoring.status_code == 200
    assert monitoring.json()["payload"]["campaign_id"] == project["campaign_id"]
    assert monitoring.json()["payload"]["project_version"] == 1

    republished = client.post(
        f"/campaigns/{project['campaign_id']}/publish",
        json={"targets": ["monitoring"]},
    )
    assert republished.status_code == 200
    assert republished.json()["items"][0]["attempts"] == 2

    revised = client.patch(
        f"/campaigns/{project['campaign_id']}",
        json={"expected_revision": project["revision"], "budget_total": 65000},
    )
    assert revised.status_code == 200, revised.text
    revised_project = revised.json()
    assert revised_project["status"] == "draft"
    assert revised_project["current_version"] == 2
    assert revised_project["approved_version"] == 1
    assert revised_project["versions"][0]["status"] == "approved"
    assert revised_project["versions"][1]["status"] == "draft"


def test_return_creates_new_draft_and_keeps_audit(client):
    project = fill_required_sections(client, create_project(client))
    project = client.post(
        f"/campaigns/{project['campaign_id']}/submit",
        json={"expected_revision": project["revision"]},
    ).json()
    returned = client.post(
        f"/campaigns/{project['campaign_id']}/decision",
        json={
            "expected_revision": project["revision"],
            "decision": "return",
            "reason": "Add budget assumptions.",
            "actor": "Brand Owner",
            "actor_role": "brand_owner",
        },
    )
    assert returned.status_code == 200, returned.text
    payload = returned.json()
    assert payload["status"] == "draft"
    assert payload["current_version"] == 2
    assert payload["versions"][0]["status"] == "returned"
    assert payload["approvals"][-1]["reason"] == "Add budget assumptions."
