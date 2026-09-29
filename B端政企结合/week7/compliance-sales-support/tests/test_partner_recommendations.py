def _demo_headers(client, mode="professional"):
    data = client.post("/api/auth/demo-mode", json={"mode": mode}).json()
    return {"Authorization": f"Bearer {data['access_token']}"}


def test_gap_driven_partner_recommendations_are_traceable(client):
    headers = _demo_headers(client)
    profiles = client.get("/api/matching/profiles", headers=headers).json()
    project_id = client.get("/api/projects", headers=headers).json()[0]["id"]
    response = client.get(
        f"/api/matching/partner-recommendations/{project_id}",
        params={"profile_id": profiles[1]["id"]}, headers=headers,
    )
    assert response.status_code == 200, response.text
    result = response.json()

    assert result["rule_version"] == "gap-partner/1.0"
    assert result["admission_decision"] in {"go", "hold", "no_go"}
    assert 3 <= len(result["candidates"]) <= 5
    assert result["coverage"]["candidate_count"] == len(result["candidates"])
    assert result["disclaimer"]
    gap_codes = {gap["code"] for gap in result["gap_summary"]}
    scores = [candidate["match_score"] for candidate in result["candidates"]]
    assert scores == sorted(scores, reverse=True)

    for candidate in result["candidates"]:
        assert candidate["solves_gaps"]
        assert {gap["code"] for gap in candidate["solves_gaps"]} <= gap_codes
        assert candidate["confidence"] in {"high", "medium"}
        assert candidate["manual_verification_required"] is True
        assert candidate["verification_status"] == "public_evidence_only"
        assert candidate["risk"]
        assert candidate["data_label"] == "公开候选·待商务核验"
        assert candidate["evidence"]
        assert all(item["source_type"] == "official" and item["url"].startswith("https://")
                   for item in candidate["evidence"])


def test_partner_candidates_change_with_enterprise_gaps(client):
    headers = _demo_headers(client)
    profiles = client.get("/api/matching/profiles", headers=headers).json()
    project_id = client.get("/api/projects", headers=headers).json()[0]["id"]
    first = client.get(
        f"/api/matching/partner-recommendations/{project_id}",
        params={"profile_id": profiles[0]["id"]}, headers=headers,
    ).json()
    second = client.get(
        f"/api/matching/partner-recommendations/{project_id}",
        params={"profile_id": profiles[1]["id"]}, headers=headers,
    ).json()

    assert first["gap_summary"] != second["gap_summary"]
    assert {item["id"] for item in first["candidates"]} != {item["id"] for item in second["candidates"]}


def test_partner_recommendations_enforce_access_and_not_found(client):
    assert client.get("/api/matching/partner-recommendations/1").status_code == 401
    headers = _demo_headers(client)
    assert client.get(
        "/api/matching/partner-recommendations/999999", params={"profile_id": 1}, headers=headers
    ).status_code == 404
    assert client.get(
        "/api/matching/partner-recommendations/1", params={"profile_id": 999999}, headers=headers
    ).status_code == 404


def test_no_unresolved_gap_produces_no_partner_candidate():
    from partner_service import recommend_partners

    result = recommend_partners({
        "profile_id": 1, "decision": "go", "decision_label": "Go 建议推进",
        "requirement_gap_matrix": [{"code": "REQ-01", "category": "资格与准入", "status": "satisfied"}],
    }, {"id": 1, "country": "德国"})
    assert result["gap_summary"] == []
    assert result["candidates"] == []
    assert result["coverage"] == {"gap_count": 0, "covered_gap_count": 0, "candidate_count": 0}
