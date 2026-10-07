def test_home_page_is_english(client):
    response = client.get("/")

    assert response.status_code == 200
    assert 'lang="en"' in response.text
    assert "Creator Partnership Management Platform" in response.text
    assert "v3.0" in response.text
    assert "Import Excel" in response.text
    assert "Find Creators" in response.text
    assert "YouTube" in response.text
    assert "France" in response.text
    assert "Instagram" not in response.text
    assert "Reddit" in response.text
    assert "TikTok" in response.text
    assert 'data-page="kol"' in response.text
    assert "Creators" in response.text
    assert "Creator Comparison" in response.text
    assert "Shortlists" in response.text


def test_static_assets_are_available(client):
    css = client.get("/static/styles.css")
    javascript = client.get("/static/app.js")

    assert css.status_code == 200
    assert javascript.status_code == 200
    assert "loadKols" in javascript.text


def test_page_contains_core_forms(client):
    html = client.get("/").text

    for element_id in (
        "import-form",
        "collection-form",
        "collection-status",
        "search-form",
        "selected-kol-count",
        "kol-results",
        "comparison-results",
        "detail-dialog",
        "score-form",
    ):
        assert f'id="{element_id}"' in html


def test_javascript_uses_required_apis_and_safe_dom(client):
    script = client.get("/static/app.js").text

    for endpoint in (
        "/imports",
        "/collections",
        "/kols",
        "/kols/enrich-youtube",
        "/comparisons",
    ):
        assert endpoint in script
    assert "textContent" in script
    assert "innerHTML" not in script
    assert "/dev/reset-database" not in script
    assert 'id="reset-database"' not in client.get("/").text


def test_search_page_selection_is_only_for_comparison(client):
    html = client.get("/").text
    script = client.get("/static/app.js").text

    assert 'id="select-all-kols"' in html
    assert "selectedKolIds" in script
    assert "Bulk Add to Shortlist" not in html
    assert "bulk-add-shortlist" not in html
    assert "shortlistId" not in script
    assert "bulkAddToShortlist" not in script


def test_search_page_auto_enriches_missing_youtube_followers(client):
    script = client.get("/static/app.js").text

    assert "maybeEnrichVisibleYoutubeKols" in script
    assert "/kols/enrich-youtube" in script
    assert "skipEnrichment: true" in script
    assert "YOUTUBE_ENRICHMENT_BATCH_SIZE" in script
