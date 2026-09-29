import pytest

from app.config import COMMERCIAL_WEIGHTS, RISK_WEIGHTS
from app.services.scoring import calculate_summary, risk_level, summarize_dimensions


def test_weights_each_total_100():
    assert sum(COMMERCIAL_WEIGHTS.values()) == 100
    assert sum(RISK_WEIGHTS.values()) == 100


def test_complete_weighted_score():
    scores = {dimension: 80 for dimension in COMMERCIAL_WEIGHTS}

    summary = calculate_summary(scores, COMMERCIAL_WEIGHTS)

    assert summary.score == pytest.approx(80.0)
    assert summary.completeness == pytest.approx(1.0)
    assert summary.status == "complete"


def test_missing_dimensions_are_not_zero():
    scores = {"audience_fit": 90, "content_relevance": 60}

    summary = calculate_summary(scores, COMMERCIAL_WEIGHTS)

    assert summary.score == pytest.approx((90 * 20 + 60 * 15) / 35)
    assert summary.completeness == pytest.approx(0.35)
    assert summary.status == "insufficient"


def test_manual_score_overrides_auto_score():
    scores = {"audience_fit": {"auto": 60, "manual": 85}}

    summary = calculate_summary(scores, {"audience_fit": 100})

    assert summary.score == 85


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0, "low"),
        (29.9, "low"),
        (30, "low"),
        (31, "medium"),
        (59.9, "medium"),
        (60, "medium"),
        (61, "high"),
    ],
)
def test_risk_level_thresholds(score, expected):
    assert risk_level(score) == expected


def test_out_of_range_score_is_rejected():
    with pytest.raises(ValueError, match="between 0 and 100"):
        calculate_summary({"audience_fit": 101}, {"audience_fit": 100})


def test_normalized_summary_uses_available_weight_and_ready_status():
    summary = summarize_dimensions({"audience_fit": 80.0}, COMMERCIAL_WEIGHTS)

    assert summary.score == 80.0
    assert summary.completeness == 0.2
    assert summary.status == "insufficient"


def test_normalized_summary_rounds_to_one_decimal():
    summary = summarize_dimensions({"a": 80, "b": 81}, {"a": 67, "b": 33})

    assert summary.score == 80.3
    assert summary.completeness == 1.0
    assert summary.status == "ready"
