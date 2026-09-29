from conftest import auth_headers


def test_register_login_and_duplicate(client, account):
    assert account["plan"] == "free"
    assert account["role"] == "owner"
    duplicate = client.post("/api/auth/register", json={
        "email": "OWNER@example.com", "password": "correct-horse-123"
    })
    assert duplicate.status_code == 409
    bad = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "wrong-password"})
    assert bad.status_code == 401
    good = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "correct-horse-123"})
    assert good.status_code == 200
    assert good.json()["user"]["email"] == "owner@example.com"


def test_me_requires_token(client, account):
    assert client.get("/api/auth/me").status_code == 401
    response = client.get("/api/auth/me", headers=auth_headers(account))
    assert response.status_code == 200
    assert response.json()["organization_id"] > 0


def test_anonymous_and_free_project_views_are_redacted(client, account):
    anonymous = client.get("/api/projects").json()[0]
    assert anonymous["source_url"] == ""
    assert "升级后查看" in anonymous["contracting_authority"]
    free = client.get("/api/projects", headers=auth_headers(account)).json()[0]
    assert free["source_url"] == ""


def test_free_monthly_reveal_quota(client, account):
    headers = auth_headers(account)
    for project_id in (1, 2, 3):
        response = client.get(f"/api/projects/{project_id}/reveal", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["source_url"]
    blocked = client.get("/api/projects/4/reveal", headers=headers)
    assert blocked.status_code == 403
    # 已经解锁的项目可重复查看，不重复消耗额度。
    assert client.get("/api/projects/1/reveal", headers=headers).status_code == 200


def test_paid_endpoints_cannot_be_bypassed(client, account):
    headers = auth_headers(account)
    assert client.get("/api/projects/1/scoring", headers=headers).status_code == 403
    assert client.get("/api/clients/gov/sales-pack", headers=headers).status_code == 403
    assert client.get("/api/reports/gaps/excel", headers=headers).status_code == 403
    assert client.post("/api/projects", headers=headers, json={
        "project_name": "权限测试项目", "country": "德国", "contracting_authority": "测试采购方"
    }).status_code == 403


def test_professional_permissions(client, account):
    from db import get_session
    from models import Subscription
    with get_session() as session:
        subscription = session.query(Subscription).filter(Subscription.organization_id == account["organization_id"]).one()
        subscription.plan = "professional"
        session.commit()
    # 套餐以数据库实时状态为准，旧 access token 无需伪造套餐声明。
    headers = auth_headers(account)
    assert client.get("/api/projects/1/scoring", headers=headers).status_code == 200
    created = client.post("/api/projects", headers=headers, json={
        "project_name": "权限自动化测试项目", "country": "德国", "contracting_authority": "测试采购方",
        "technical_score": 12, "compliance_score": 9, "competition_score": 6,
    })
    assert created.status_code == 200, created.text
    assert client.get("/api/reports/gaps/excel", headers=headers).status_code == 200


def test_refresh_rotation_and_logout(client):
    login = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "correct-horse-123"}).json()
    first = login["refresh_token"]
    refreshed = client.post("/api/auth/refresh", json={"refresh_token": first})
    assert refreshed.status_code == 200
    assert client.post("/api/auth/refresh", json={"refresh_token": first}).status_code == 401
    second = refreshed.json()["refresh_token"]
    assert client.post("/api/auth/logout", json={"refresh_token": second}).status_code == 204
    assert client.post("/api/auth/refresh", json={"refresh_token": second}).status_code == 401


def test_demo_identity_modes_issue_real_permissions(client):
    expected = {
        "professional": ("professional", "member", False),
        "enterprise": ("enterprise", "member", False),
        "admin": ("enterprise", "admin", True),
    }
    for mode, (plan, role, can_fetch) in expected.items():
        response = client.post("/api/auth/demo-mode", json={"mode": mode})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["plan"] == plan
        assert data["role"] == role
        assert ("intelligence.fetch" in data["permissions"]) is can_fetch
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"})
        assert me.status_code == 200
    assert client.post("/api/auth/demo-mode", json={"mode": "unknown"}).status_code == 422
