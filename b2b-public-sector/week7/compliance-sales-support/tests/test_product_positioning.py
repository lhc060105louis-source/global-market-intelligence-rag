def test_product_positioning_is_public_and_complete(client):
    response = client.get("/api/product/positioning")

    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "product-positioning/1.0"
    assert data["statement"] == "A platform for European project decisions and execution for Chinese new-energy companies"
    assert len(data["personas"]) == 3
    assert len(data["scenarios"]) == 3
    assert len(data["differentiators"]) == 5
    assert len(data["comparison"]) == 5


def test_positioning_routes_only_use_existing_hubs(client):
    data = client.get("/api/product/positioning").json()
    allowed = {
        "information": {"feed", "regulations", "clients"},
        "projecthub": {"opportunities", "case", "workspace", "sprint", "reports"},
        "ecosystem": {"profile", "partners"},
    }

    for item in data["personas"] + data["scenarios"]:
        route = item["route"]
        assert route["page"] in allowed
        assert route["tab"] in allowed[route["page"]]


def test_positioning_answers_three_core_customer_questions(client):
    data = client.get("/api/product/positioning").json()
    scenarios = {item["id"]: item for item in data["scenarios"]}

    assert set(scenarios) == {"can_bid", "missing_materials", "local_capability"}
    assert "Go／Hold／No-Go" in scenarios["can_bid"]["solution"]
    assert "P0—P3" in scenarios["missing_materials"]["solution"]
    assert "candidate partners" in scenarios["local_capability"]["solution"]
    for item in scenarios.values():
        assert item["generic_limit"]
        assert item["paid_reason"]
        assert item["next_step"]
