COMMERCIAL_WEIGHTS = {
    "audience_fit": 20,
    "content_relevance": 15,
    "interaction_quality": 15,
    "voc_value": 15,
    "commercial_efficiency": 15,
    "brand_fit": 10,
    "execution_capability": 10,
}

RISK_WEIGHTS = {
    "historical_controversy": 20,
    "ad_disclosure": 15,
    "competitor_conflict": 15,
    "fake_traffic": 15,
    "data_privacy": 10,
    "sensitive_audience": 10,
    "sustainability_claims": 10,
    "execution_risk": 5,
}


def validate_weights() -> None:
    for name, weights in (
        ("commercial", COMMERCIAL_WEIGHTS),
        ("risk", RISK_WEIGHTS),
    ):
        if sum(weights.values()) != 100:
            raise RuntimeError(f"{name} weights must total 100")
