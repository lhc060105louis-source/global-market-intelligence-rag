def _professional_headers(client):
    data = client.post("/api/auth/demo-mode", json={"mode": "professional"}).json()
    return {"Authorization": f"Bearer {data['access_token']}"}


def test_demo_case_separates_current_and_method_decisions(client):
    response = client.get("/api/matching/demo-case", headers=_professional_headers(client))
    assert response.status_code == 200, response.text
    case = response.json()

    assert case["case_version"] == "admission-case/1.0"
    assert case["project"]["status"] == "closed"
    assert case["project"]["deadline"] == "2026-06-15"
    assert case["current_decision"]["decision"] == "no_go"
    assert case["method_decision"]["decision"] == "hold"
    assert set(case["method_decision"]["hard_gate_codes"]) == {"QUAL-03", "QUAL-05"}
    assert "模拟企业" in case["labels"]
    assert "项目已截止" in case["labels"]


def test_demo_case_matrix_and_partner_candidates_are_traceable(client):
    case = client.get("/api/matching/demo-case", headers=_professional_headers(client)).json()
    matrix = case["qualification_matrix"]
    assert len(matrix) == 8
    assert sum(row["gap_level"] == "P0" for row in matrix) == 2
    assert all(row["action"] for row in matrix)

    unresolved_codes = {row["code"] for row in matrix if row["status"] != "satisfied"}
    assert len(case["partners"]) == 3
    for partner in case["partners"]:
        assert set(partner["solves_gap_codes"]) <= unresolved_codes
        assert partner["confidence"] in {"high", "medium"}
        assert partner["evidence_url"].startswith("https://")
        assert partner["risk"]
        assert partner["manual_verification"]
    assert len(case["partner_rules"]) >= 4
    assert len(case["next_actions"]) >= 5
    assert case["disclaimer"]


def test_demo_case_requires_paid_matching_access(client):
    assert client.get("/api/matching/demo-case").status_code == 401
