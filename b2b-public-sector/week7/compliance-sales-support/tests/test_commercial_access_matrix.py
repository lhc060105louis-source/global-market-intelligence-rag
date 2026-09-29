import pytest

from permissions import Principal, access_summary


def _principal(plan):
    return Principal(user_id=1, organization_id=1, plan=plan, role="member")


@pytest.mark.parametrize("capability,states", [
    ("project.exact_info", {"anonymous": "H", "free": "P", "professional": "R", "enterprise": "R", "special_service": "R"}),
    ("project.convert", {"anonymous": "NA", "free": "L", "professional": "R", "enterprise": "R", "special_service": "R"}),
    ("project.scoring", {"anonymous": "H", "free": "L", "professional": "R", "enterprise": "RW", "special_service": "RW"}),
    ("project.matching", {"anonymous": "H", "free": "L", "professional": "R", "enterprise": "RW", "special_service": "RW"}),
    ("partner.contact", {"anonymous": "H", "free": "H", "professional": "H", "enterprise": "L", "special_service": "R"}),
    ("task.create", {"anonymous": "NA", "free": "NA", "professional": "R", "enterprise": "RW", "special_service": "RW"}),
    ("enterprise_profile.edit", {"anonymous": "NA", "free": "RW", "professional": "RW", "enterprise": "RW", "special_service": "RW"}),
    ("service.request", {"anonymous": "NA", "free": "NA", "professional": "L", "enterprise": "R", "special_service": "RW"}),
])
def test_excel_access_states_are_executable(capability, states):
    assert access_summary(None)["capabilities"][capability]["state"] == states["anonymous"]
    for plan in ("free", "professional", "enterprise", "special_service"):
        assert access_summary(_principal(plan))["capabilities"][capability]["state"] == states[plan]


def test_access_endpoint_supports_visitor_and_paid_demo(client):
    visitor = client.get("/api/auth/access").json()
    assert visitor["plan"] == "anonymous"
    assert visitor["capabilities"]["project.exact_info"]["state"] == "H"

    demo = client.post("/api/auth/demo-mode", json={"mode": "enterprise"}).json()
    assert demo["access"]["capabilities"]["project.scoring"]["state"] == "RW"
    headers = {"Authorization": f"Bearer {demo['access_token']}"}
    current = client.get("/api/auth/access", headers=headers).json()
    assert current["plan"] == "enterprise"
    assert current["capabilities"]["partner.contact"]["state"] == "L"


def test_professional_report_export_permission_is_consistent(client):
    demo = client.post("/api/auth/demo-mode", json={"mode": "professional"}).json()
    assert "reports.export" in demo["permissions"]
    assert demo["access"]["capabilities"]["report.export"]["state"] == "R"
