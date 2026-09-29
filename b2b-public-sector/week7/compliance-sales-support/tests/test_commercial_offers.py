def test_commercial_catalog_has_five_distinct_offers(client):
    response = client.get("/api/commercial/offers")
    assert response.status_code == 200
    catalog = response.json()
    assert catalog["version"] == "commercial-offers/1.0"
    assert catalog["currency"] == "EUR"
    assert "pricing assumptions require validation" in catalog["pricing_note"]

    offers = {offer["id"]: offer for offer in catalog["offers"]}
    assert set(offers) == {"free", "professional", "enterprise", "standard_service", "sprint_14d"}
    assert offers["professional"]["price_eur"] == 499
    assert offers["enterprise"]["price_eur"] == 1499
    assert offers["standard_service"]["price_eur"] == 7500
    assert offers["sprint_14d"]["price_eur"] == 12000
    assert all(offers[key]["quote_status"] == "hypothesis" for key in offers if key != "free")
    assert [offers[key]["product_type"] for key in ("free", "professional", "enterprise")] == ["subscription"] * 3
    assert [offers[key]["product_type"] for key in ("standard_service", "sprint_14d")] == ["service"] * 2
    for offer in offers.values():
        assert offer["included"]
        assert offer["excluded"]
        assert offer["audience"]
        assert offer["cta"]
        assert offer["upgrade_path"]


def test_sprint_catalog_defines_scope_sla_and_risk_boundaries(client):
    catalog = client.get("/api/commercial/offers").json()
    sprint = catalog["sprint"]
    assert len(sprint["application_materials"]) == 4
    assert len(sprint["timeline"]) == 7
    assert sprint["timeline"][0]["days"] == "Day 1"
    assert sprint["timeline"][-1]["days"] == "Day 14"
    assert len(sprint["deliverables"]) == 6
    assert sprint["sla"]
    assert sprint["client_cooperation"]
    assert sprint["change_rules"]
    assert sprint["why_premium"]
    assert "No guarantee of winning" in sprint["not_promised"]
    assert catalog["automation_vs_analyst"]["platform"]
    assert catalog["automation_vs_analyst"]["analyst"]
    assert len(catalog["faq"]) == 5
