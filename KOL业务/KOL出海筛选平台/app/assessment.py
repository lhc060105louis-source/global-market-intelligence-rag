from dataclasses import dataclass
from math import floor
from typing import Callable, Mapping, Sequence

from app.config import COMMERCIAL_WEIGHTS, RISK_WEIGHTS
from app.services.scoring import summarize_dimensions


@dataclass(frozen=True)
class DimensionResult:
    score: float | None
    evidence: list[str]


@dataclass(frozen=True)
class AssessmentResult:
    commercial_dimensions: dict[str, DimensionResult]
    commercial_score: float | None
    commercial_completeness: float
    commercial_status: str
    commercial_grade: str | None
    risk_dimensions: dict[str, DimensionResult]
    risk_score: float | None
    risk_completeness: float
    risk_status: str
    risk_level: str | None
    flags: list[str]


def _round(value: float) -> int:
    return floor(value + 0.5)


def _clamp(value: object) -> float:
    return min(max(float(value), 0), 100)


def _qual(value: object) -> int:
    return 90 if value == "high" else 60 if value == "mid" else 25


def _layer(parts: list[tuple[float, int]]) -> int:
    return _round(sum(score * weight / 100 for score, weight in parts))


def _has_value(value: object) -> bool:
    return value is not None and not (isinstance(value, str) and not value.strip())


def _complete(d: Mapping[str, object], keys: tuple[str, ...]) -> bool:
    return all(key in d and _has_value(d[key]) for key in keys)


def _dimension(
    d: Mapping[str, object], keys: tuple[str, ...], calculation: Callable[[], int]
) -> DimensionResult:
    if not _complete(d, keys):
        return DimensionResult(None, [])
    return DimensionResult(float(calculation()), [f"{key}={d[key]}" for key in keys])


def score_audience(d: Mapping[str, object]) -> DimensionResult:
    keys = ("geo", "lang", "autoInterest", "income", "age")

    def calculate() -> int:
        geo, auto = _clamp(d["geo"]), _clamp(d["autoInterest"])
        lang = 100 if d["lang"] == 3 else 65 if d["lang"] == 2 else 30
        income = 95 if d["income"] == "high" else 65 if d["income"] == "mid" else 35
        buyer = _round(income * 0.5 + _clamp(d["age"]) * 0.5)
        target = _round((geo + auto) / 2)
        return _layer([(_round(geo), 25), (lang, 20), (_round(auto), 20), (buyer, 20), (target, 15)])

    return _dimension(d, keys, calculate)


def score_content(d: Mapping[str, object]) -> DimensionResult:
    keys = ("focus", "depth", "credibility")
    return _dimension(d, keys, lambda: _layer([
        (_round(_clamp(d["focus"])), 35),
        (95 if d["depth"] == "deep" else 65 if d["depth"] == "mid" else 30, 35),
        (_qual(d["credibility"]), 30),
    ]))


def score_engagement(d: Mapping[str, object]) -> DimensionResult:
    keys = ("err", "completion", "commentQuality", "shareSave")
    return _dimension(d, keys, lambda: _layer([
        (_clamp(_round(float(d["err"]) / 3 * 100)), 30),
        (_clamp(_round(float(d["completion"]) / 60 * 100)), 25),
        (_qual(d["commentQuality"]), 30),
        (_clamp(_round(float(d["shareSave"]) / 20 * 100)), 15),
    ]))


def score_voc(d: Mapping[str, object]) -> DimensionResult:
    keys = ("vocDepth", "vocNeg", "vocHistory")
    return _dimension(d, keys, lambda: _layer([
        (_qual(d["vocDepth"]), 40), (_qual(d["vocNeg"]), 30),
        (90 if d["vocHistory"] == "yes" else 60 if d["vocHistory"] == "sometimes" else 20, 30),
    ]))


def score_commercial_efficiency(d: Mapping[str, object]) -> DimensionResult:
    keys = ("benchCpm", "cpm", "reuse", "exclusive")

    def calculate() -> int:
        bench, cpm = float(d["benchCpm"]), float(d["cpm"])
        if bench <= 0:
            raise ValueError("benchCpm must be greater than zero")
        ratio = cpm / bench
        cpm_score = 100 if ratio <= 0.8 else _round(100 - (ratio - 0.8) * 150) if ratio <= 1 else _round(70 - (ratio - 1) * 80) if ratio <= 1.5 else 20
        reuse = 95 if d["reuse"] == "full" else 60 if d["reuse"] == "limited" else 20
        exclusive = 90 if d["exclusive"] == "none" else 65 if d["exclusive"] == "soft" else 25
        return _layer([(_clamp(cpm_score), 40), (reuse, 35), (exclusive, 25)])

    return _dimension(d, keys, calculate)


def score_brand_fit(d: Mapping[str, object]) -> DimensionResult:
    keys = ("brandTone", "histTone", "styleConsist")
    mapped = lambda value: 90 if value == "match" else 65 if value == "neutral" else 20
    return _dimension(d, keys, lambda: _layer([(mapped(d["brandTone"]), 50), (mapped(d["histTone"]), 30), (_qual(d["styleConsist"]), 20)]))


def score_execution(d: Mapping[str, object]) -> DimensionResult:
    keys = ("fulfill", "briefCoop", "dataReady", "contractFlex")
    return _dimension(d, keys, lambda: _layer([
        (_round(_clamp(d["fulfill"])), 35), (_qual(d["briefCoop"]), 25),
        (90 if d["dataReady"] == "active" else 60 if d["dataReady"] == "passive" else 15, 25),
        (90 if d["contractFlex"] == "flexible" else 65 if d["contractFlex"] == "normal" else 25, 15),
    ]))


def _risk_map(value: object, values: Mapping[str, int]) -> int:
    return values.get(str(value), 50)


RiskScorer = Callable[[object], float]
RiskSpec = tuple[str, RiskScorer, int]


def _risk_dimension(
    d: Mapping[str, object],
    keys: tuple[str, ...],
    specs: Sequence[RiskSpec],
) -> DimensionResult:
    return _dimension(d, keys, lambda: _layer([(fn(d[key]), weight) for key, fn, weight in specs]))


def _risk_dimensions(d: Mapping[str, object], flags: list[str]) -> dict[str, DimensionResult]:
    def mapping(values: Mapping[str, int]) -> RiskScorer:
        return lambda value: _risk_map(value, values)
    fake = lambda value: 100 if float(value) >= 40 else 80 if float(value) >= 30 else 55 if float(value) >= 20 else 30 if float(value) >= 10 else 5
    minor = lambda value: 90 if float(value) >= 40 else 70 if float(value) >= 30 else 45 if float(value) >= 20 else 20 if float(value) >= 10 else 5
    pct50 = lambda value: _clamp(_round(float(value) / 50 * 100))
    definitions = {
        "historical_controversy": (("incident", "falsead", "sentiment"), [("incident", mapping({"none":5,"minor":35,"serious":72,"critical":100}),40), ("falsead", mapping({"none":5,"minor":40,"serious":90}),35), ("sentiment", mapping({"none":0,"local":30,"wide":80}),25)]),
        "ad_disclosure": (("adlabel", "penalty", "compliance"), [("adlabel", mapping({"always":5,"sometimes":45,"never":95}),50), ("penalty", mapping({"none":5,"warning":40,"penalty":85}),30), ("compliance", mapping({"high":5,"mid":40,"low":85}),20)]),
        "competitor_conflict": (("competitor", "compcontentpct", "complevel"), [("competitor", mapping({"none":0,"nonexclusive":30,"exclusive":70,"ambassador":100}),50), ("compcontentpct", pct50,25), ("complevel", mapping({"none":0,"indirect":25,"direct":80}),25)]),
        "fake_traffic": (("fakepct", "spikegrowth", "templatecomment"), [("fakepct", fake,45), ("spikegrowth", mapping({"none":5,"once":50,"multiple":90}),30), ("templatecomment", mapping({"normal":5,"some":45,"heavy":90}),25)]),
        "data_privacy": (("gdpr", "datause"), [("gdpr", mapping({"none":5,"minor":40,"serious":95}),55), ("datause", mapping({"compliant":5,"unclear":45,"violation":90}),45)]),
        "sensitive_audience": (("minorpct", "agesuit"), [("minorpct", minor,60), ("agesuit", mapping({"suitable":5,"partial":45,"unsuitable":85}),40)]),
        "sustainability_claims": (("exaggerate", "adas", "techaccuracy"), [("exaggerate", mapping({"none":5,"minor":40,"serious":90}),45), ("adas", mapping({"none":5,"cautious":30,"exaggerated":85}),30), ("techaccuracy", mapping({"high":5,"mid":40,"low":80}),25)]),
        "execution_risk": (("latedelete", "briefreject"), [("latedelete", mapping({"none":5,"occasional":40,"frequent":85}),55), ("briefreject", mapping({"cooperative":5,"friction":45,"refuse":90}),45)]),
    }
    if d.get("incident") == "critical": flags.append("⚠ 存在极严重负面事件（司法处罚/平台封号），需法务和品牌负责人复核")
    if d.get("falsead") == "serious": flags.append("⚠ 有严重虚假宣传记录，触发合规高风险")
    if d.get("adlabel") == "never": flags.append("⚠ 拒绝广告披露标注，严重违反欧盟广告法规（ASA/ARPP/UWG）")
    if d.get("competitor") == "ambassador": flags.append("⚠ 当前为直接竞品品牌大使，存在重大竞品冲突风险，建议直接排除")
    elif d.get("competitor") == "exclusive": flags.append("⚠ 当前有竞品排他合作，需确认排他条款范围后决策")
    fake_pct = float(d["fakepct"]) if _has_value(d.get("fakepct")) else None
    if fake_pct is not None and fake_pct >= 30: flags.append(f"⚠ 僵尸粉比例 {d['fakepct']}%，" + ("明显超过高风险阈值（40%），疑似刷量" if fake_pct >= 40 else "超过预警阈值（30%），建议核查"))
    if d.get("gdpr") == "serious": flags.append("⚠ 存在严重 GDPR 违规记录，欧洲市场合规风险极高，需法务审查")
    minor_pct = float(d["minorpct"]) if _has_value(d.get("minorpct")) else None
    if minor_pct is not None and minor_pct >= 30: flags.append(f"⚠ 未成年受众占比 {d['minorpct']}%，超过预警阈值，汽车广告合规性存疑")
    if d.get("exaggerate") == "serious": flags.append("⚠ 有严重夸大技术/环保声明记录，需在合同中明确技术声明边界")
    return {name: _risk_dimension(d, keys, specs) for name, (keys, specs) in definitions.items()}


def commercial_grade(score: float | None) -> str | None:
    return None if score is None else "A" if score >= 80 else "B" if score >= 65 else "C"


def assessment_risk_level(score: float | None) -> str | None:
    return None if score is None else "high" if score >= 61 else "medium" if score >= 31 else "low"


def calculate_assessment(commercial_inputs: Mapping[str, object], risk_inputs: Mapping[str, object]) -> AssessmentResult:
    commercial = {
        "audience_fit": score_audience(commercial_inputs), "content_relevance": score_content(commercial_inputs),
        "interaction_quality": score_engagement(commercial_inputs), "voc_value": score_voc(commercial_inputs),
        "commercial_efficiency": score_commercial_efficiency(commercial_inputs), "brand_fit": score_brand_fit(commercial_inputs),
        "execution_capability": score_execution(commercial_inputs),
    }
    flags: list[str] = []
    risks = _risk_dimensions(risk_inputs, flags)
    cs = summarize_dimensions({k: v.score for k, v in commercial.items()}, COMMERCIAL_WEIGHTS)
    rs = summarize_dimensions({k: v.score for k, v in risks.items()}, RISK_WEIGHTS)
    return AssessmentResult(commercial, cs.score, cs.completeness, cs.status, commercial_grade(cs.score), risks, rs.score, rs.completeness, rs.status, assessment_risk_level(rs.score), flags)
