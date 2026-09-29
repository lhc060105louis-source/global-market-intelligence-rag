import pytest

from app.assessment import calculate_assessment


HIGH_VALUE_INPUTS = {
    "geo": 90,
    "lang": 3,
    "autoInterest": 90,
    "income": "high",
    "age": 80,
    "focus": 90,
    "depth": "deep",
    "credibility": "high",
    "err": 1.8,
    "completion": 45,
    "commentQuality": "high",
    "shareSave": 14,
    "vocDepth": "high",
    "vocNeg": "mid",
    "vocHistory": "yes",
    "benchCpm": 20,
    "cpm": 16,
    "reuse": "full",
    "exclusive": "none",
    "brandTone": "match",
    "histTone": "match",
    "styleConsist": "high",
    "fulfill": 95,
    "briefCoop": "high",
    "dataReady": "active",
    "contractFlex": "flexible",
}

LOW_RISK_INPUTS = {
    "incident": "none",
    "falsead": "none",
    "sentiment": "none",
    "adlabel": "always",
    "penalty": "none",
    "compliance": "high",
    "competitor": "none",
    "compcontentpct": 0,
    "complevel": "none",
    "fakepct": 5,
    "spikegrowth": "none",
    "templatecomment": "normal",
    "gdpr": "none",
    "datause": "compliant",
    "minorpct": 5,
    "agesuit": "suitable",
    "exaggerate": "none",
    "adas": "none",
    "techaccuracy": "high",
    "latedelete": "none",
    "briefreject": "cooperative",
}


def test_complete_high_value_low_risk_assessment():
    result = calculate_assessment(HIGH_VALUE_INPUTS, LOW_RISK_INPUTS)

    assert result.commercial_score == 88
    assert result.commercial_grade == "A"
    assert result.commercial_completeness == 1.0
    assert result.commercial_status == "ready"
    assert result.risk_level == "low"
    assert result.risk_completeness == 1.0
    assert result.risk_status == "ready"
    assert result.flags == []
    assert {name: dimension.score for name, dimension in result.commercial_dimensions.items()} == {
        "audience_fit": 92.0,
        "content_relevance": 92.0,
        "interaction_quality": 74.0,
        "voc_value": 81.0,
        "commercial_efficiency": 96.0,
        "brand_fit": 90.0,
        "execution_capability": 92.0,
    }
    assert {name: dimension.score for name, dimension in result.risk_dimensions.items()} == {
        "historical_controversy": 4.0,
        "ad_disclosure": 5.0,
        "competitor_conflict": 0.0,
        "fake_traffic": 5.0,
        "data_privacy": 5.0,
        "sensitive_audience": 5.0,
        "sustainability_claims": 5.0,
        "execution_risk": 5.0,
    }


def test_absent_raw_inputs_make_a_dimension_unavailable():
    inputs = dict(HIGH_VALUE_INPUTS)
    del inputs["geo"]

    result = calculate_assessment(inputs, LOW_RISK_INPUTS)

    assert result.commercial_dimensions["audience_fit"].score is None
    assert result.commercial_completeness == pytest.approx(0.8)
    assert result.commercial_score is not None


@pytest.mark.parametrize(("field", "blank"), [("geo", ""), ("geo", "  ")])
def test_blank_numeric_input_makes_dimension_unavailable(field, blank):
    inputs = dict(HIGH_VALUE_INPUTS, **{field: blank})

    result = calculate_assessment(inputs, LOW_RISK_INPUTS)

    assert result.commercial_dimensions["audience_fit"].score is None


@pytest.mark.parametrize("blank", ["", "\t"])
def test_blank_categorical_input_makes_dimension_unavailable(blank):
    inputs = dict(HIGH_VALUE_INPUTS, depth=blank)

    result = calculate_assessment(inputs, LOW_RISK_INPUTS)

    assert result.commercial_dimensions["content_relevance"].score is None


@pytest.mark.parametrize(
    ("field", "dimension"),
    [("fakepct", "fake_traffic"), ("minorpct", "sensitive_audience")],
)
@pytest.mark.parametrize("blank", ["", "  "])
def test_blank_risk_percentage_makes_dimension_unavailable(field, dimension, blank):
    risks = dict(LOW_RISK_INPUTS, **{field: blank})

    result = calculate_assessment(HIGH_VALUE_INPUTS, risks)

    assert result.risk_dimensions[dimension].score is None
    assert result.flags == []


def test_risk_flags_match_prototype_thresholds():
    risks = dict(LOW_RISK_INPUTS, fakepct=30, minorpct=30)

    result = calculate_assessment(HIGH_VALUE_INPUTS, risks)

    assert len(result.flags) == 2
    assert "30%" in result.flags[0]
    assert "30%" in result.flags[1]


@pytest.mark.parametrize(
    ("score", "grade"), [(64, "C"), (65, "B"), (79, "B"), (80, "A")]
)
def test_commercial_grade_boundaries(score, grade):
    from app.assessment import commercial_grade

    assert commercial_grade(score) == grade


@pytest.mark.parametrize(
    ("score", "level"), [(30, "low"), (31, "medium"), (60, "medium"), (61, "high")]
)
def test_risk_level_boundaries(score, level):
    from app.assessment import assessment_risk_level

    assert assessment_risk_level(score) == level
