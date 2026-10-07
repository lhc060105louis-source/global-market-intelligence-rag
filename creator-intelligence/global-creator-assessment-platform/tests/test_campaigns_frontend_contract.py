def test_campaign_navigation_and_six_step_workspace_exist(client):
    html = client.get("/").text

    assert 'data-page="campaigns"' in html
    assert 'id="page-campaigns"' in html
    for step, label in (
        ("M1", "Campaign Overview"),
        ("M2", "Basic Information"),
        ("M3", "Audience Strategy"),
        ("M4", "KPI Plan"),
        ("M5", "Creators & Budget"),
        ("M6", "Approval & Handoff"),
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
