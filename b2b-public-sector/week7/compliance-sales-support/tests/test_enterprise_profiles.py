def _demo_headers(client, mode="professional"):
    data = client.post("/api/auth/demo-mode", json={"mode": mode}).json()
    return {"Authorization": f"Bearer {data['access_token']}"}


def test_two_demo_profiles_produce_different_project_matches(client):
    headers = _demo_headers(client)
    profiles = client.get("/api/matching/profiles", headers=headers).json()
    assert len(profiles) >= 2
    project_id = client.get("/api/projects", headers=headers).json()[0]["id"]
    first = client.get(
        f"/api/matching/match/{project_id}", params={"profile_id": profiles[0]["id"]}, headers=headers
    )
    second = client.get(
        f"/api/matching/match/{project_id}", params={"profile_id": profiles[1]["id"]}, headers=headers
    )
    assert first.status_code == second.status_code == 200
    a, b = first.json(), second.json()
    assert a["profile_id"] != b["profile_id"]
    assert a["total_score"] != b["total_score"]
    assert a["advantages"] != b["advantages"]
    assert a["gaps"] != b["gaps"]
    for result in (a, b):
        assert result["rule_version"] == "enterprise-match/1.2"
        assert result["confidence_level"] in {"High", "Medium", "Low"}
        assert "partial_items" in result
        assert "recommended_actions" in result
        assert len(result["dimensions"]) == 7
        assert result["decision"] in {"go", "hold", "no_go"}
        assert result["decision_label"]
        assert result["decision_reason"]
        assert len(result["requirement_gap_matrix"]) == 7
        for row in result["requirement_gap_matrix"]:
            assert row["status"] in {"satisfied", "partial", "missing", "unverified"}
            assert row["source_type"] == "Project notice + company profile"
            assert "requires_human_review" in row
    assert a["decision"] == "go"
    assert b["decision"] == "hold"
    assert b["hard_gates"]


def test_profile_update_recalculates_completeness_and_version(client):
    headers = _demo_headers(client)
    profile = client.get("/api/matching/profiles", headers=headers).json()[0]
    response = client.put(f"/api/matching/profiles/{profile['id']}", headers=headers, json={
        "org_name": profile["org_name"], "target_countries": [],
        "target_client_types": profile["target_client_types"], "vehicle_types": profile["vehicle_types"],
        "powertrain_types": profile["powertrain_types"], "existing_certs": profile["existing_certs"],
        "has_eu_entity": profile["has_eu_entity"],
    })
    assert response.status_code == 200
    saved = response.json()
    assert saved["version"] == profile["version"] + 1
    assert saved["completeness"] < 100
    assert "target_countries" in saved["missing_required"]
    assert saved["completeness"] != 999


def test_product_mismatch_is_a_no_go_hard_gate():
    from matching_service import match_project

    profile = {
        "id": 999, "org_name": "Passenger Car Demo Company", "version": 1, "completeness": 100,
        "existing_certs": ["WVTA", "CSMS (R155)"], "vehicle_types": ["Passenger Car"],
        "charging_capability": "800V fast charging", "software_capability": "OTA and connected vehicle services",
        "available_materials": ["WVTA", "CSMS Certificate", "Battery Passport"],
        "local_after_sales": ["DE"], "target_countries": ["DE"],
        "has_eu_entity": "Yes", "acceptable_scale": "€5M–€100M", "delivery_cycle": "6 months",
    }
    project = {
        "project_name": "Germany Electric Bus Project", "country": "Germany", "project_type": "Public Transit",
        "contracting_authority": "Demo Buyer", "description": "Battery-electric bus procurement",
        "deadline": "2026-12-31", "source_url": "https://example.invalid/tender",
    }
    result = match_project(profile, project)

    assert result["decision"] == "no_go"
    product_gate = next(gate for gate in result["hard_gates"] if gate["code"] == "REQ-02")
    assert product_gate["impact"] == "no_go"
    assert product_gate["severity"] == "P0"
