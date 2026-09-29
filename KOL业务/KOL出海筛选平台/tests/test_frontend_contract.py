def test_menu_order_and_toolbar(client):
    html = client.get("/").text
    navigation = html[html.index('<div class="nav-group">') :]

    assert (
        navigation.index("KOL 列表")
        < navigation.index("KOL 对比")
        < navigation.index("合作管理")
    )
    assert "自动查找 KOL" in html
    assert "导出 Excel" in html
    assert "TikTok" in html
    assert "Reddit" in html


def test_approved_pages_and_collection_overlay_exist(client):
    html = client.get("/").text

    for element_id in (
        "page-dashboard", "page-kol", "page-compare", "page-shortlists", "page-collab",
        "page-contracts", "page-results", "page-settings",
        "auto-collection-overlay",
    ):
        assert f'id="{element_id}"' in html


def test_collection_modal_and_polling_contract(client):
    html = client.get("/").text
    script = client.get("/static/collection.js")
    modal = html.split('id="auto-collection-overlay"', 1)[1].split(
        'id="import-overlay"', 1
    )[0]

    assert script.status_code == 200
    assert '<script src="/static/collection.js"></script>' in html
    for field in ('name="keywords"', 'name="markets"', 'name="languages"',
                  'name="limit_per_platform"'):
        assert field in modal
    for value in ('value="GB"', 'value="FR"', 'value="DE"',
                  'value="en"', 'value="fr"', 'value="de"'):
        assert value in modal
    assert 'name="platforms"' in modal
    for value in ('value="youtube"', 'value="reddit"', 'value="tiktok"'):
        assert value in modal

    source = script.text
    for function_name in ("openCollectionModal", "submitCollection", "pollCollection"):
        assert f"function {function_name}" in source
    assert "2000" in source
    assert "loadKols()" in source
    assert "updateDashboard()" in source
    assert "beforeunload" in source
    assert "retry-collection" in html


def test_kol_search_has_follower_range_controls_and_validation(client):
    html = client.get("/").text
    script = client.get("/static/app.js").text

    assert 'type="number" name="min_followers" min="0" step="1"' in html
    assert 'placeholder="最低粉丝量"' in html
    assert 'type="number" name="max_followers" min="0" step="1"' in html
    assert 'placeholder="最高粉丝量"' in html
    assert "function submitKolSearch(event)" in script
    assert 'showStatus("最低粉丝量不能大于最高粉丝量", true)' in script
    assert '["min_followers", "max_followers", "min_commercial_score"]' in script
    assert 'addEventListener("submit", submitKolSearch)' in script


def test_kol_search_has_minimum_commercial_score_control(client):
    html = client.get("/").text
    script = client.get("/static/app.js").text

    assert (
        'type="number" name="min_commercial_score" '
        'min="0" max="100" step="1"'
    ) in html
    assert 'placeholder="最低商业价值分"' in html
    assert 'aria-label="最低商业价值分"' in html
    assert (
        '["min_followers", "max_followers", "min_commercial_score"]'
        in script
    )


def test_open_add_kol_clears_stale_preview_state(client):
    script = client.get("/static/app.js").text

    start = script.index("function openAddKOL")
    body = script[start:script.index("async function openEditKOL", start)]
    assert 'document.getElementById("score-preview")' in body
    assert 'document.getElementById("yt-status")' in body
    assert 'document.getElementById("yt-preview-card")' in body
    assert "scheduleAssessmentPreview()" in body


def test_frontend_uses_api_state_and_split_assessment_module(client):
    html = client.get("/").text
    script = client.get("/static/app.js").text
    assessment = client.get("/static/assessment.js")

    assert assessment.status_code == 200
    assert '<script src="/static/assessment.js"></script>' in html
    assert '<script src="/static/app.js"></script>' in html
    assert 'api("/kols"' in script
    assert 'localStorage.setItem("kol_platform_kols"' not in script
    assert "function calcCommercial" not in script
    assert "function calcRisk" not in script


def test_add_and_edit_forms_use_authoritative_kol_api(client):
    html = client.get("/").text
    script = client.get("/static/app.js").text

    assert 'id="kol-form"' in html
    assert 'id="kol-id"' in html
    assert 'method: kolId ? "PUT" : "POST"' in script
    assert "`/kols/${kolId}`" in script


def test_workflow_score_and_prototype_modal_contract(client):
    html = client.get("/").text
    script = client.get("/static/app.js").text

    for label in ("KOL识别", "资质评估", "比稿议价", "合同签订", "投放执行", "效果归因", "续约/归档"):
        assert label in script
    for marker in ("m-tabs", "m-tab-0", "m-tab-1", "m-tab-2", "yt-import", "受众与内容", "商业条件", "风险评估"):
        assert marker in html
    assert "COMMERCIAL_DIMENSIONS" in script
    assert "RISK_DIMENSIONS" in script
    assert "renderScoreRecords" in script
    assert "populateScoreDimensions" in script
    assert "stageCounts" in script


def test_enrichment_preserves_query_and_compare_limit_rerenders(client):
    script = client.get("/static/app.js").text
    comparison = client.get("/static/comparison.js").text

    assert "currentQuery" in script
    assert 'await loadKols(state.currentQuery' in script
    assert "renderKOLPage();" in script
    assert "state.selectedKolIds.size >= MAX_COMPARISON_KOLS" in comparison


def test_comparison_workflow_settings_and_export_are_split_modules(client):
    html = client.get("/").text
    script = client.get("/static/app.js").text
    comparison = client.get("/static/comparison.js").text
    workflow = client.get("/static/workflow.js").text
    settings = client.get("/static/settings.js").text

    for module in ("comparison.js", "workflow.js", "settings.js"):
        assert f'<script src="/static/{module}"></script>' in html
    for marker in ("toggleComparison", "renderComparison", "score_records", "commercial_completeness", "risk_completeness", "recommendation"):
        assert marker in comparison
    assert "MAX_COMPARISON_KOLS = 4" in comparison
    assert "checkbox.disabled" in comparison
    assert "advanceWorkflow" in workflow
    assert 'method: "PUT"' in workflow
    assert "await loadKols" in workflow
    assert "loadYoutubeSettings" in settings
    assert "saveYoutubeKey" in settings
    assert 'method: "DELETE"' in settings

    assert 'id="export-kols"' in html
    assert "downloadKolsExport" in script
    assert "currentQuery" in script
    assert "credentials: \"same-origin\"" in script
    download_helper = script[script.index("async function protectedSameOriginDownload"):script.index("function downloadKolsExport")]
    assert 'headers.set("X-KOL-Session", window.__KOL_SESSION_TOKEN__)' in download_helper
    assert "credentials: \"same-origin\"" in download_helper
    for boundary in ('>= 80 ? "high"', '>= 65 ? "medium"', '<= 30 ? "low"', '<= 60 ? "medium"'):
        assert boundary in comparison
    for action in ("强烈推荐合作", "合同中加强约束条款", "进入法务复核", "稳健合作对象", "可考虑合作", "不建议合作"):
        assert action in comparison


def test_youtube_lookup_and_all_assessment_inputs_are_bound(client):
    html = client.get("/").text
    script = client.get("/static/app.js").text
    assessment = client.get("/static/assessment.js").text
    assert "/kols/lookup-youtube" in script
    assert "fetchYouTubePreview" in script
    assert "commercial_inputs" in script and "risk_inputs" in script
    for key in ("geo", "lang", "autoInterest", "income", "age", "focus", "depth", "credibility", "err", "completion", "commentQuality", "shareSave", "vocDepth", "vocNeg", "vocHistory", "benchCpm", "cpm", "reuse", "exclusive", "brandTone", "histTone", "styleConsist", "fulfill", "briefCoop", "dataReady", "contractFlex"):
        assert f'name="{key}"' in html
    for key in ("incident", "falsead", "sentiment", "adlabel", "penalty", "compliance", "competitor", "compcontentpct", "complevel", "fakepct", "spikegrowth", "templatecomment", "gdpr", "datause", "minorpct", "agesuit", "exaggerate", "adas", "techaccuracy", "latedelete", "briefreject"):
        assert f'name="{key}"' in html
    assert "calculatePreview" in assessment
    assert "initializeAssessmentSelects" in script
    assert 'new Option("未评估", "", true, true)' in script
    assert 'benchmark.defaultValue = ""' in script
