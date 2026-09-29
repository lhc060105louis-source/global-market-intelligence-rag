import pytest

from app.models import AssessmentInput, Kol, KolScoreSummary
from app.shared_contracts import (
    Country,
    KOLRiskAlert,
    MaterialStatus,
    Priority,
    RegulationChange,
    RegType,
    build_kol_risk_alert,
    regulation_affects_kol,
    to_shared_country,
)


def make_kol(
    *,
    country: str = "DE",
    name: str = "BYD Technik",
    categories: str = "BYD, EV review",
    risk_score: float | None = 61,
    risk_status: str = "ready",
    risk_level: str | None = "high",
    flags: list[str] | None = None,
) -> Kol:
    kol = Kol(
        name=name,
        platform="YouTube",
        handle="@technik",
        country=country,
        content_categories=categories,
    )
    kol.score_summary = KolScoreSummary(
        commercial_score=None,
        commercial_completeness=0,
        commercial_status="insufficient",
        risk_score=risk_score,
        risk_completeness=1,
        risk_status=risk_status,
        risk_level=risk_level,
    )
    kol.assessment_input = AssessmentInput(
        commercial_inputs={},
        risk_inputs={"campaign_scenario": "技术测评"},
        flags=flags or ["⚠ 有严重虚假宣传记录，触发合规高风险"],
        source="test",
    )
    return kol


def test_shared_package_imports_from_repository_root():
    assert Country.DE.value == "DE"
    assert RegType.DATA_AI.value == "数据与AI"
    assert Priority.P0.value == "P0"
    assert MaterialStatus.NEED_UPDATE.value == "待更新"
    assert KOLRiskAlert.__name__ == "KOLRiskAlert"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("GB", Country.UK),
        ("UK", Country.UK),
        ("DE", Country.DE),
        ("FR", Country.FR),
        ("EU", Country.EU),
    ],
)
def test_to_shared_country_uses_shared_enum(raw, expected):
    assert to_shared_country(raw) is expected


def test_to_shared_country_rejects_non_shared_country():
    with pytest.raises(ValueError, match="Unsupported shared country"):
        to_shared_country("US")


def test_complete_high_risk_kol_builds_shared_alert():
    alert = build_kol_risk_alert(make_kol())

    assert alert == KOLRiskAlert(
        brand="BYD",
        country=Country.DE.value,
        creator_name="BYD Technik",
        platform="YouTube",
        severity="high",
        topic="⚠ 有严重虚假宣传记录，触发合规高风险",
        regulation_hint="虚假宣传/广告合规",
        detected_at="",
    )


@pytest.mark.parametrize(
    ("risk_score", "risk_status", "risk_level"),
    [(60, "ready", "medium"), (80, "insufficient", "high"), (None, "insufficient", None)],
)
def test_non_ready_or_non_high_risk_kol_does_not_build_alert(
    risk_score, risk_status, risk_level
):
    assert (
        build_kol_risk_alert(
            make_kol(
                risk_score=risk_score,
                risk_status=risk_status,
                risk_level=risk_level,
            )
        )
        is None
    )


def test_regulation_change_matches_country_brand_and_scenario():
    kol = make_kol()
    change = RegulationChange(
        regulation_id="REG-001",
        country=[Country.DE.value],
        affected_brands=["BYD"],
        affected_scenarios=["技术测评"],
    )

    assert regulation_affects_kol(change, kol)


def test_regulation_change_country_mismatch_does_not_match():
    assert not regulation_affects_kol(
        RegulationChange(regulation_id="REG-002", country=[Country.FR.value]),
        make_kol(country="DE"),
    )


def test_eu_regulation_matches_supported_country():
    assert regulation_affects_kol(
        RegulationChange(regulation_id="REG-003", country=[Country.EU.value]),
        make_kol(country="GB"),
    )


def test_regulation_brand_and_scenario_narrow_matches():
    kol = make_kol()
    assert not regulation_affects_kol(
        RegulationChange(
            regulation_id="REG-004",
            country=["DE"],
            affected_brands=["XPeng"],
        ),
        kol,
    )
    assert not regulation_affects_kol(
        RegulationChange(
            regulation_id="REG-005",
            country=["DE"],
            affected_scenarios=["直播带货"],
        ),
        kol,
    )
