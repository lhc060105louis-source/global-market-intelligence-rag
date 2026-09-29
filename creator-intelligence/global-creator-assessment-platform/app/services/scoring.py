from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ScoreSummary:
    score: float | None
    completeness: float
    status: str


def _effective_score(value: object) -> float | None:
    if isinstance(value, dict):
        manual = value.get("manual")
        value = manual if manual is not None else value.get("auto")
    if value is None:
        return None
    score = float(value)
    if not 0 <= score <= 100:
        raise ValueError("score must be between 0 and 100")
    return score


def calculate_summary(
    scores: Mapping[str, object],
    weights: Mapping[str, int],
) -> ScoreSummary:
    weighted_sum = 0.0
    available_weight = 0
    for dimension, weight in weights.items():
        score = _effective_score(scores.get(dimension))
        if score is None:
            continue
        weighted_sum += score * weight
        available_weight += weight

    if available_weight == 0:
        return ScoreSummary(None, 0.0, "insufficient")

    completeness = available_weight / sum(weights.values())
    status = (
        "complete"
        if completeness == 1
        else "provisional"
        if completeness >= 0.6
        else "insufficient"
    )
    return ScoreSummary(weighted_sum / available_weight, completeness, status)


def summarize_dimensions(
    scores: Mapping[str, object], weights: Mapping[str, int]
) -> ScoreSummary:
    """Normalize over dimensions with evidence, without treating absence as zero."""
    weighted = 0.0
    available_weight = 0
    for name, weight in weights.items():
        value = _effective_score(scores.get(name))
        if value is None:
            continue
        weighted += value * weight
        available_weight += weight
    if not available_weight:
        return ScoreSummary(None, 0.0, "insufficient")
    completeness = available_weight / 100
    return ScoreSummary(
        round(weighted / available_weight, 1),
        completeness,
        "ready" if completeness >= 0.6 else "insufficient",
    )


def risk_level(score: float | None) -> str | None:
    if score is None:
        return None
    if score <= 30:
        return "low"
    if score <= 60:
        return "medium"
    return "high"
