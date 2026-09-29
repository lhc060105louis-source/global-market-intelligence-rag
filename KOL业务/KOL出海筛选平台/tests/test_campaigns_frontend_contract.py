def test_campaign_navigation_and_six_step_workspace_exist(client):
    html = client.get("/").text

    assert 'data-page="campaigns"' in html
    assert 'id="page-campaigns"' in html
    for step, label in (
        ("M1", "项目总览"),
        ("M2", "基本信息"),
        ("M3", "受众策略"),
        ("M4", "KPI方案"),
        ("M5", "KOL与预算"),
        ("M6", "审批交接"),
    ):
        assert f'data-campaign-step="{step}"' in html
        assert label in html


def test_campaign_frontend_is_loaded_and_uses_real_api(client):
    html = client.get("/").text
    response = client.get("/static/campaigns.js")

    assert response.status_code == 200
    assert '<script src="/static/campaigns.js"></script>' in html
    source = response.text
    for operation in (
        "loadCampaigns",
        "saveCampaignBasic",
        "saveCampaignStrategy",
        "saveCampaignMeasurement",
        "saveCampaignRequirements",
        "submitCurrentCampaign",
        "decideCurrentCampaign",
        "publishCurrentCampaign",
    ):
        assert f"function {operation}" in source or f"async function {operation}" in source
    for endpoint in (
        'campaignRequest("/campaigns",',
        "/strategy",
        "/measurement-plan",
        "/kol-requirements",
        "/validate",
        "/submit",
        "/decision",
        "/publish",
    ):
        assert endpoint in source
    assert "localStorage" not in source
