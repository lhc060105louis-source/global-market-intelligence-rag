from datetime import date, datetime

import pytest
from sqlalchemy import select

from app.models import Campaign, CampaignReview, ContentTask, Kol, PerformanceReview, ScoreRecord


@pytest.fixture()
def creator(client):
    with client.app.state.session_factory() as session:
        kol = Kol(name="New creator", handle="@new-creator", platform="YouTube", country="GB")
        session.add(kol)
        session.flush()
        kol_id = kol.id
        session.add(PerformanceReview(kol_id=kol_id, campaign="Recorded campaign", impressions=1000, engagements=100, conversions=7))
        session.add(ContentTask(task_code="REAL-1", kol_id=kol_id, campaign="Recorded campaign", platform="YouTube", title="Recorded content", execution_stage="In Progress", content_url="https://example.org/content"))
        session.commit()
    return kol_id


def test_empty_database_has_no_business_defaults(client):
    overview = client.get("/reinvestment/overview").json()
    assert overview["metrics"]["total"] == 0
    assert overview["assets"] == []
    assert client.get("/reinvestment/archives/@AutoBildDE").status_code == 404
    portfolio = client.get("/reinvestment/portfolio").json()
    assert portfolio["project"] is None
    assert portfolio["candidates"] == portfolio["scenarios"] == []
    assert portfolio["selected_scenario"] is None
    assert all(check["status"] == "Unavailable" for check in portfolio["checks"])
    assert client.get("/reinvestment/actions").json()["tasks"] == []
    with client.app.state.session_factory() as session:
        assert session.scalar(select(CampaignReview)) is None


def test_new_creator_uses_persisted_history(client, creator):
    assets = client.get("/reinvestment/overview").json()["assets"]
    assert len(assets) == 1
    assert assets[0]["kol_id"] == creator
    assert assets[0]["collaborations"] == 1
    assert assets[0]["conversions"] == 7
    archive = client.get(f"/reinvestment/archives/{creator}").json()
    assert [row["project"] for row in archive["project_history"]] == ["Recorded campaign"]
    assert archive["metrics"]["avg_engagement"] == 10
    assert archive["reusable_assets"] == ["https://example.org/content"]


def test_performance_change_updates_metrics(client, creator):
    with client.app.state.session_factory() as session:
        review = session.scalar(select(PerformanceReview).where(PerformanceReview.kol_id == creator))
        review.engagements = 200
        review.conversions = 12
        session.commit()
    archive = client.get(f"/reinvestment/archives/{creator}").json()
    assert archive["metrics"]["avg_engagement"] == 20
    assert archive["metrics"]["conversions"] == 12


def test_missing_evidence_is_unavailable(client):
    with client.app.state.session_factory() as session:
        kol = Kol(platform="TikTok", country="FR")
        session.add(kol)
        session.commit()
        key = kol.id
    archive = client.get(f"/reinvestment/archives/{key}").json()
    assert archive["recent_cooperation"] is None
    assert archive["project_history"] == archive["trend"] == archive["reusable_assets"] == []
    assert archive["metrics"]["avg_engagement"] is None
    assert archive["metrics"]["conversions"] is None
    evaluation = client.get(f"/reinvestment/evaluations/{key}").json()
    assert evaluation["suggestion_score"] is None
    assert evaluation["historical_score"] is None
    assert evaluation["conditions"]["quote_cap"] is None
    assert evaluation["data_completeness"] == 0
    assert all(item["score"] is None for item in evaluation["dimensions"])


def test_manual_scores_and_completeness_are_preserved(client, creator):
    with client.app.state.session_factory() as session:
        session.add(ScoreRecord(kol_id=creator, score_type="commercial", dimension="audience_fit", auto_score=10, manual_score=80, manual_evidence="Reviewed audience", manual_source="Analyst"))
        session.commit()
    data = client.get(f"/reinvestment/evaluations/{creator}").json()
    assert data["historical_score"] == 80
    assert data["suggestion_score"] is None
    assert data["data_completeness"] == 20
    dimension = next(item for item in data["dimensions"] if item["dimension"] == "audience_fit")
    assert dimension["score"] == 80
    assert dimension["evidence"] == "Reviewed audience"
    assert dimension["source"] == "Analyst"


def test_approval_and_governance_persist_by_creator_identity(client, creator):
    assert client.post(f"/reinvestment/evaluations/{creator}/approval", json={"decision": "Conditionally Approved", "note": "Need quote"}).status_code == 200
    assert client.post(f"/reinvestment/governance/{creator}", json={"status": "Paused", "reason": "Need verification"}).status_code == 200
    with client.app.state.session_factory() as session:
        session.get(Kol, creator).handle = "@renamed"
        session.commit()
    data = client.get(f"/reinvestment/evaluations/{creator}").json()
    assert data["approval"]["decision"] == "Conditionally Approved"
    assert data["major_risk"] is True
    assert data["suggestion_status"] == "Paused Assessment"
    assert client.get("/reinvestment/governance").json()["timeline"]


def test_actions_reference_real_tasks_and_persist(client, creator):
    tasks = client.get("/reinvestment/actions").json()["tasks"]
    assert [task["task_code"] for task in tasks] == ["REAL-1"]
    assert client.post("/reinvestment/actions/REAL-1", json={"status": "Completed"}).status_code == 200
    assert client.get("/reinvestment/actions").json()["tasks"][0]["status"] == "Completed"


def test_invalid_and_deleted_references_are_rejected(client, creator):
    assert client.post("/reinvestment/actions/ACT-001", json={"status": "Completed"}).status_code == 404
    assert client.post("/reinvestment/evaluations/@Carwow/approval", json={"decision": "Approved"}).status_code == 404
    assert client.post("/reinvestment/governance/99999", json={"status": "Paused", "reason": "Review"}).status_code == 404
    assert client.post("/reinvestment/portfolio/select", json={"scenario_id": "A"}).status_code == 422
    with client.app.state.session_factory() as session:
        session.get(Kol, creator).deleted_at = datetime.now()
        session.commit()
    assert client.get(f"/reinvestment/evaluations/{creator}").status_code == 404
    assert client.post("/reinvestment/actions/REAL-1", json={"status": "Completed"}).status_code == 404


def test_duplicate_handle_requires_stable_identity(client, creator):
    with client.app.state.session_factory() as session:
        session.add(Kol(handle="@new-creator", platform="TikTok", country="GB"))
        session.commit()
    assert client.get("/reinvestment/evaluations/@new-creator").status_code == 404
    assert client.get(f"/reinvestment/evaluations/{creator}").status_code == 200


def test_existing_handle_keyed_decisions_are_retained(client, creator):
    with client.app.state.session_factory() as session:
        session.add(CampaignReview(campaign="__asset_reinvestment__", analysis_data={
            "approvals": {"@new-creator": {"decision": "Rejected", "note": "Recorded review", "updated_at": None}},
            "governance": {"@new-creator": {"status": "Blocked", "reason": "Recorded restriction"}},
        }))
        session.commit()
    data = client.get(f"/reinvestment/evaluations/{creator}").json()
    assert data["approval"]["decision"] == "Rejected"
    assert data["major_risk"] is True


def test_selected_real_campaign_still_has_no_invented_portfolio(client, creator):
    with client.app.state.session_factory() as session:
        session.add(Campaign(campaign_id="CMP-REAL", project_name="Actual project", brand="Brand", vehicle_model="Model", primary_market="GB", start_date=date(2026, 10, 1), end_date=date(2026, 10, 31), timezone="UTC", currency="GBP", budget_total=20000, owner="Owner"))
        session.commit()
    data = client.get("/reinvestment/portfolio?campaign_id=CMP-REAL").json()
    assert data["project"]["name"] == "Actual project"
    assert data["project"]["budget"] == 20000
    assert data["candidates"][0]["kol_id"] == creator
    assert data["scenarios"] == []
    assert data["candidates"][0]["quote_cap"] is None
    assert all(check["status"] == "Unavailable" for check in data["checks"])
    assert client.get("/reinvestment/portfolio?campaign_id=missing").status_code == 404


def test_approvals_are_scoped_to_selected_campaign(client, creator):
    with client.app.state.session_factory() as session:
        for campaign_id in ("CMP-A", "CMP-B"):
            session.add(Campaign(campaign_id=campaign_id, project_name=campaign_id, brand="Brand", vehicle_model="Model", primary_market="GB", start_date=date(2026, 10, 1), end_date=date(2026, 10, 31), timezone="UTC", currency="GBP", budget_total=20000, owner="Owner"))
        session.commit()
    endpoint = f"/reinvestment/evaluations/{creator}"
    assert client.post(f"{endpoint}/approval", json={"decision": "Conditionally Approved", "note": "Unscoped historical review"}).status_code == 200
    assert client.get(f"{endpoint}?campaign_id=CMP-A").json()["approval"]["decision"] == "Pending Approval"
    response = client.post(f"{endpoint}/approval?campaign_id=CMP-A", json={"decision": "Approved", "note": "A only"})
    assert response.status_code == 200
    assert client.get(f"{endpoint}?campaign_id=CMP-A").json()["approval"]["note"] == "A only"
    assert client.get(f"{endpoint}?campaign_id=CMP-B").json()["approval"]["decision"] == "Pending Approval"
    assert client.get(endpoint).json()["approval"]["decision"] == "Conditionally Approved"
    assert client.post(f"{endpoint}/approval?campaign_id=missing", json={"decision": "Approved"}).status_code == 404
