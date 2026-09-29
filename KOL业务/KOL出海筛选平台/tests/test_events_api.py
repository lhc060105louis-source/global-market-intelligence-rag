from dataclasses import asdict

from app.shared_contracts import (
    Country,
    KOLRiskAlert,
    MaterialStatus,
    RegulationChange,
)


HIGH_RISK_INPUTS = {
    "incident": "critical",
    "falsead": "serious",
    "sentiment": "wide",
    "adlabel": "never",
    "penalty": "penalty",
    "compliance": "low",
    "competitor": "ambassador",
    "compcontentpct": 50,
    "complevel": "direct",
    "fakepct": 40,
    "spikegrowth": "multiple",
    "templatecomment": "heavy",
    "gdpr": "serious",
    "datause": "violation",
    "minorpct": 40,
    "agesuit": "unsuitable",
    "exaggerate": "serious",
    "adas": "exaggerated",
    "techaccuracy": "low",
    "latedelete": "frequent",
    "briefreject": "refuse",
}


def create_kol(client, *, country: str, handle: str, name: str):
    response = client.post(
        "/kols",
        json={
            "platform": "YouTube",
            "country": country,
            "handle": handle,
            "name": name,
            "content_categories": "BYD, EV review, 技术测评",
        },
    )
    assert response.status_code == 201
    return response.json()


def regulation_payload(**overrides):
    values = asdict(
        RegulationChange(
            regulation_id="REG-001",
            regulation_name="EU 汽车广告规则",
            country=[Country.DE.value],
            change_type="修订",
            summary="技术宣传需要补充证据",
            affected_scenarios=["技术测评"],
            affected_brands=["BYD"],
            published_at="2026-07-29T10:00:00+08:00",
        )
    )
    values.update(overrides)
    return values


def test_regulation_change_marks_only_matching_kol_copy_for_update(client):
    de = create_kol(
        client, country="DE", handle="@de-review", name="BYD Deutschland"
    )
    create_kol(client, country="FR", handle="@fr-review", name="BYD France")

    response = client.post(
        "/events/regulation-changes", json=regulation_payload()
    )

    assert response.status_code == 201
    assert response.json() == {"matched": 1, "created": 1, "existing": 0}
    reviews = client.get("/events/regulation-reviews").json()
    assert len(reviews) == 1
    assert reviews[0]["kol_id"] == de["id"]
    assert reviews[0]["regulation_id"] == "REG-001"
    assert reviews[0]["status"] == MaterialStatus.NEED_UPDATE.value


def test_regulation_change_is_idempotent(client):
    create_kol(client, country="DE", handle="@repeat", name="BYD Repeat")
    payload = regulation_payload()

    assert client.post("/events/regulation-changes", json=payload).json() == {
        "matched": 1,
        "created": 1,
        "existing": 0,
    }
    assert client.post("/events/regulation-changes", json=payload).json() == {
        "matched": 1,
        "created": 0,
        "existing": 1,
    }
    assert len(client.get("/events/regulation-reviews").json()) == 1


def test_regulation_change_rejects_unknown_country(client):
    response = client.post(
        "/events/regulation-changes",
        json=regulation_payload(country=["US"]),
    )
    assert response.status_code == 422


def test_regulation_change_accepts_no_matches(client):
    create_kol(client, country="FR", handle="@nomatch", name="BYD France")
    response = client.post(
        "/events/regulation-changes", json=regulation_payload()
    )
    assert response.status_code == 201
    assert response.json() == {"matched": 0, "created": 0, "existing": 0}


def test_regulation_change_requires_nonblank_id(client):
    response = client.post(
        "/events/regulation-changes",
        json=regulation_payload(regulation_id=" "),
    )
    assert response.status_code == 422


def test_kol_risk_alerts_emit_only_complete_high_risk_assessments(client):
    high = client.post(
        "/kols",
        json={
            "platform": "YouTube",
            "country": "DE",
            "handle": "@alert",
            "name": "BYD Alert",
            "content_categories": "BYD, EV",
            "risk_inputs": HIGH_RISK_INPUTS,
        },
    )
    assert high.status_code == 201
    assert high.json()["score_summary"]["risk_level"] == "high"
    assert high.json()["score_summary"]["risk_status"] == "ready"

    incomplete = client.post(
        "/kols",
        json={
            "platform": "YouTube",
            "country": "FR",
            "handle": "@incomplete",
            "name": "Incomplete",
            "risk_inputs": {"incident": "critical"},
        },
    )
    assert incomplete.status_code == 201

    response = client.get("/events/kol-risk-alerts")

    assert response.status_code == 200
    alerts = response.json()
    assert len(alerts) == 1
    assert set(alerts[0]) == set(KOLRiskAlert.__dataclass_fields__)
    assert alerts[0]["brand"] == "BYD"
    assert alerts[0]["country"] == Country.DE.value
    assert alerts[0]["creator_name"] == "BYD Alert"
    assert alerts[0]["severity"] == "high"
