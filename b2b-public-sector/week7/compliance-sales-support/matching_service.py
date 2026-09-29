# -*- coding: utf-8 -*-
"""Explainable seven-dimension matching engine for company profiles and projects."""
from __future__ import annotations

MATCH_DIMS = [
    ("Qualification and Market Access", 15), ("Product and Project Fit", 20), ("Technology and Solution Fit", 15),
    ("Compliance and Material Readiness", 15), ("Localization and Delivery Capability", 15),
    ("Commercial Attractiveness", 10), ("Timing and Execution Feasibility", 10),
]
RULE_VERSION = "enterprise-match/1.2"

COUNTRY_ALIASES = {
    "Germany": "DE", "France": "FR", "United Kingdom": "UK", "Italy": "IT", "Spain": "ES",
    "Denmark": "DK", "Croatia": "HR", "North Macedonia": "MK", "Netherlands": "NL",
}


def _dim(name, result, detail, score, maximum, evidence):
    return {"name": name, "result": result, "detail": detail, "score": score,
            "max": maximum, "evidence": evidence}


def _vehicle_result(vehicles: list[str], project_type: str):
    if not vehicles:
        return "unconfirmed", "Vehicle model information has not been entered"
    if any(scene in project_type for scene in ("Bus", "PublicTransport", "Airport Transport")):
        return ("matched", "Electric bus model fits the bus use case") if any("bus" in v.lower() for v in vehicles) else ("gap", "No bus-compatible vehicle model")
    if "charging" in project_type:
        return "partial", "Vehicle models are not a threshold; verify charging-system integration capabilities"
    return "matched", "Product capabilities are configured for this use case"


REQUIREMENT_DEFINITIONS = {
    "Qualification and Market Access": {
        "requirement": "Project-specific certifications and tender eligibility",
        "required_evidence": "Required certifications, tender-entity eligibility, and validity evidence (confirm against the original tender)",
        "action": "Review each tender eligibility clause, obtain missing certifications, or confirm an acceptable consortium route",
    },
    "Product and Project Fit": {
        "requirement": "Products or vehicle models that fit the procurement use case",
        "required_evidence": "Product catalogue, vehicle specifications, and evidence of fit for similar use cases",
        "action": "Confirm the target product scope; adjust the tender role or stop pursuing the project if there is no fit",
    },
    "Technology and Solution Fit": {
        "requirement": "Charging, software, and system-integration solution",
        "required_evidence": "Technical proposal, interface documentation, test records, and integration references",
        "action": "Complete technical evidence and ask the technology owner to review project interface requirements",
    },
    "Compliance and Material Readiness": {
        "requirement": "Compliance materials that can be submitted and remain valid",
        "required_evidence": "Certificates, reports, and declarations required by the project's regulations",
        "action": "Inventory materials against project regulations and assign owners and expected completion dates",
    },
    "Localization and Delivery Capability": {
        "requirement": "In-country after-sales, spare-parts, operations, and delivery network",
        "required_evidence": "Local entity, team, service locations, warehouse, or partner evidence",
        "action": "Identify missing local capabilities and validate partners or build the required service network",
    },
    "Commercial Attractiveness": {
        "requirement": "Project scale and fit with the company's commercial limits",
        "required_evidence": "Acceptable contract size, budget limits, and internal approval criteria",
        "action": "Document commercial limits and complete an initial return assessment",
    },
    "Timing and Execution Feasibility": {
        "requirement": "Feasible tender deadline, certification lead time, and delivery schedule",
        "required_evidence": "Tender timeline, internal preparation time, and delivery plan",
        "action": "Have the project owner confirm key dates and set escalation criteria for fixed lead times",
    },
}


def _gap_severity(dimension: str, status: str) -> str:
    if status == "satisfied":
        return ""
    rules = {
        "Qualification and Market Access": {"missing": "P0", "unverified": "P0", "partial": "P1"},
        "Product and Project Fit": {"missing": "P0", "unverified": "P1", "partial": "P1"},
        "Technology and Solution Fit": {"missing": "P0", "unverified": "P1", "partial": "P1"},
        "Compliance and Material Readiness": {"missing": "P0", "unverified": "P1", "partial": "P1"},
        "Localization and Delivery Capability": {"missing": "P1", "unverified": "P1", "partial": "P2"},
        "Commercial Attractiveness": {"missing": "P2", "unverified": "P2", "partial": "P2"},
        "Timing and Execution Feasibility": {"missing": "P1", "unverified": "P1", "partial": "P2"},
    }
    return rules.get(dimension, {}).get(status, "P2")


def _requirement_gap_matrix(dimensions: list[dict], project: dict) -> list[dict]:
    """Convert the seven-dimension assessment into an auditable requirement, evidence, status, and gap matrix."""
    status_map = {
        "matched": "satisfied", "partial": "partial",
        "gap": "missing", "unconfirmed": "unverified",
    }
    rows = []
    for index, dimension in enumerate(dimensions, 1):
        definition = REQUIREMENT_DEFINITIONS[dimension["name"]]
        status = status_map[dimension["result"]]
        severity = _gap_severity(dimension["name"], status)
        rows.append({
            "code": f"REQ-{index:02d}",
            "category": dimension["name"],
            "requirement": definition["requirement"],
            "required_evidence": definition["required_evidence"],
            "enterprise_evidence": dimension.get("evidence") or [],
            "status": status,
            "severity": severity,
            "assessment": dimension["detail"],
            "source_type": "Project notice + company profile",
            "source_url": project.get("source_url") or "",
            "action": "No additional evidence required; recheck validity before bidding" if status == "satisfied" else definition["action"],
            "requires_human_review": status != "satisfied" or dimension["name"] in {"Qualification and Market Access", "Timing and Execution Feasibility"},
        })
    return rows


def _admission_decision(total_score: int, confidence_level: str,
                        matrix: list[dict]) -> tuple[str, str, list[str], list[dict]]:
    """Use the score for sorting; determine access from hard gates, evidence completeness, and total score."""
    hard_gates = []
    for row in matrix:
        if row["severity"] != "P0" or row["status"] not in {"missing", "unverified"}:
            continue
        impact = "no_go" if row["category"] == "Product and Project Fit" and row["status"] == "missing" else "hold"
        hard_gates.append({
            "code": row["code"], "requirement": row["requirement"],
            "status": row["status"], "severity": row["severity"],
            "impact": impact, "reason": row["assessment"], "action": row["action"],
        })

    reasons = []
    if any(gate["impact"] == "no_go" for gate in hard_gates):
        decision = "no_go"
        reasons.append("The core product does not fit the procurement use case, so the current tender role is not feasible")
    elif total_score < 45 and any(row["status"] == "missing" for row in matrix):
        decision = "no_go"
        reasons.append("Overall fit is too low and material capability gaps remain")
    elif hard_gates or total_score < 70 or confidence_level == "Low":
        decision = "hold"
        if hard_gates:
            reasons.append(f"{len(hard_gates)} P0 eligibility or evidence gates remain open")
        if total_score < 70:
            reasons.append(f"Overall fit is {total_score}/100, below the recommended investment threshold")
        if confidence_level == "Low":
            reasons.append("The company profile or project information is incomplete, so confidence is low")
    else:
        decision = "go"
        reasons.append("No unresolved P0 gates were found and overall fit meets the recommended investment threshold")

    labels = {"go": "Go: Recommended to Proceed", "hold": "Hold: Close Gaps and Reassess", "no_go": "No-Go: Do Not Proceed"}
    return decision, labels[decision], reasons, hard_gates


def match_project(profile: dict, project: dict, regulations: list | None = None) -> dict:
    """Return seven-dimension scores, an access decision, evidence gaps, confidence, and recommended actions."""
    dims, advantages, partial_items, gaps, unconfirmed, actions = [], [], [], [], [], []
    project_type, country = project.get("project_type", ""), project.get("country", "")

    certs = profile.get("existing_certs") or []
    strong_certs = [c for c in certs if "WVTA" in c or "CSMS" in c]
    if len(strong_certs) >= 2:
        dims.append(_dim("Qualification and Market Access", "matched", "Both WVTA and CSMS certifications are available", 15, 15, strong_certs))
        advantages.append("Market access: WVTA and CSMS certifications are largely complete")
    elif strong_certs:
        dims.append(_dim("Qualification and Market Access", "partial", "Only some key certifications are covered", 8, 15, strong_certs))
        partial_items.append("Market access: verify other mandatory certifications in the project requirements")
        actions.append("Review mandatory tender certifications and provide missing evidence")
    elif certs:
        dims.append(_dim("Qualification and Market Access", "gap", "Current certifications do not include WVTA or CSMS", 2, 15, certs))
        gaps.append({"dim": "Qualification and Market Access", "desc": "Key WVTA or CSMS certification is missing", "severity": "P0", "reason": "Company certifications do not match European vehicle access requirements"})
        actions.append("Create a plan to obtain WVTA and CSMS certifications")
    else:
        dims.append(_dim("Qualification and Market Access", "unconfirmed", "Certification information has not been entered", 4, 15, []))
        unconfirmed.append("Existing certifications have not been entered, so eligibility cannot be assessed")

    vehicle_state, vehicle_detail = _vehicle_result(profile.get("vehicle_types") or [], project_type)
    vehicle_score = {"matched": 20, "partial": 12, "gap": 3, "unconfirmed": 6}[vehicle_state]
    dims.append(_dim("Product and Project Fit", vehicle_state, vehicle_detail, vehicle_score, 20, profile.get("vehicle_types") or []))
    if vehicle_state == "matched": advantages.append("Product capabilities: " + vehicle_detail)
    elif vehicle_state == "partial": partial_items.append("Product capabilities: " + vehicle_detail)
    elif vehicle_state == "gap": gaps.append({"dim": "Product and Project Fit", "desc": vehicle_detail, "severity": "P1", "reason": "Project type does not fit the company's vehicle models"})
    else: unconfirmed.append(vehicle_detail)

    charging = profile.get("charging_capability", "")
    software = profile.get("software_capability", "")
    if charging and software:
        dims.append(_dim("Technology and Solution Fit", "matched", "Charging and software capabilities are documented", 15, 15, [charging, software]))
        advantages.append("Technical solution: charging and software integration capabilities are available")
    elif charging or software:
        dims.append(_dim("Technology and Solution Fit", "partial", "Only some technical solution capabilities are documented", 9, 15, [charging or software]))
        partial_items.append("Technical solution: provide evidence for charging or software capabilities")
    else:
        dims.append(_dim("Technology and Solution Fit", "unconfirmed", "Technical capabilities have not been entered", 4, 15, []))
        unconfirmed.append("Charging, software, and data capabilities have not been entered")

    materials = profile.get("available_materials") or []
    if len(materials) >= 3:
        dims.append(_dim("Compliance and Material Readiness", "matched", f"{len(materials)} materials are registered", 15, 15, materials))
        advantages.append("Compliance materials: multiple usable items of evidence are available")
    elif materials:
        dims.append(_dim("Compliance and Material Readiness", "partial", f"Only {len(materials)} materials are registered", 8, 15, materials))
        partial_items.append("Compliance materials: evidence coverage is incomplete")
        actions.append("Add P0/P1 materials based on the project regulation list")
    else:
        dims.append(_dim("Compliance and Material Readiness", "unconfirmed", "Available materials have not been entered", 4, 15, []))
        unconfirmed.append("The company's available compliance materials have not been entered")

    local = profile.get("local_after_sales") or []
    country_code = COUNTRY_ALIASES.get(country, country)
    target = profile.get("target_countries") or []
    covers_country = country in local or country_code in local
    targets_country = country in target or country_code in target
    has_entity = str(profile.get("has_eu_entity", "")).casefold().startswith("yes")
    if covers_country:
        dims.append(_dim("Localization and Delivery Capability", "matched", f"After-sales service covers {country}", 15, 15, local))
        advantages.append(f"Localization: after-sales or service coverage is available in {country}")
    elif has_entity or targets_country:
        dims.append(_dim("Localization and Delivery Capability", "partial", f"Targeting {country}, but the local service network is not yet established", 8, 15, local + target))
        partial_items.append(f"Localization: service and spare-parts network in {country} still needs to be established")
        actions.append(f"Identify a local operations and after-sales partner in {country}")
    else:
        dims.append(_dim("Localization and Delivery Capability", "gap", f"No coverage in {country} and no European entity", 2, 15, []))
        gaps.append({"dim": "Localization and Delivery Capability", "desc": f"No local entity, after-sales service, or partner in {country}", "severity": "P1", "reason": "Company profile lacks localization capabilities"})
        actions.append(f"Prioritize building a local service partnership network in {country}")

    scale = profile.get("acceptable_scale", "")
    if scale:
        dims.append(_dim("Commercial Attractiveness", "matched", "Acceptable project scale is defined", 8, 10, [scale]))
        advantages.append("Commercial limits: acceptable project scale is defined")
    else:
        dims.append(_dim("Commercial Attractiveness", "unconfirmed", "Project scale preference has not been entered", 3, 10, []))
        unconfirmed.append("Acceptable project scale has not been entered")

    delivery = profile.get("delivery_cycle", "")
    if delivery:
        dims.append(_dim("Timing and Execution Feasibility", "partial", "Delivery lead time is entered; confirm it against the deadline", 7, 10, [delivery, project.get("deadline", "")]))
        partial_items.append("Timing: compare delivery lead time with the project deadline")
    else:
        dims.append(_dim("Timing and Execution Feasibility", "unconfirmed", "Delivery lead time has not been entered", 3, 10, []))
        unconfirmed.append("Delivery lead time has not been entered, so timing feasibility cannot be assessed")

    completeness = int(profile.get("completeness") or 0)
    project_fields = [project.get(k) for k in ("project_name", "country", "project_type", "contracting_authority", "description", "deadline")]
    project_completeness = round(sum(bool(v) for v in project_fields) / len(project_fields) * 100)
    confidence_score = round((completeness + project_completeness) / 2)
    confidence_level = "High" if confidence_score >= 80 else "Medium" if confidence_score >= 60 else "Low"
    if confidence_level != "High":
        actions.insert(0, "Complete the company profile or project requirements to improve match confidence")

    total_score = sum(d["score"] for d in dims)
    requirement_gap_matrix = _requirement_gap_matrix(dims, project)
    decision, decision_label, decision_reasons, hard_gates = _admission_decision(
        total_score, confidence_level, requirement_gap_matrix
    )
    for gate in hard_gates:
        actions.insert(0, gate["action"])

    return {
        "total_score": total_score, "max_score": 100,
        "rule_version": RULE_VERSION, "profile_id": profile.get("id"),
        "profile_name": profile.get("org_name", ""), "profile_version": profile.get("version", 1),
        "profile_completeness": completeness, "project_completeness": project_completeness,
        "confidence_score": confidence_score, "confidence_level": confidence_level,
        "dimensions": dims, "advantages": advantages, "partial_items": partial_items,
        "gaps": gaps, "unconfirmed": unconfirmed, "recommended_actions": list(dict.fromkeys(actions)),
        "decision": decision, "decision_label": decision_label,
        "decision_reason": "; ".join(decision_reasons), "decision_reasons": decision_reasons,
        "hard_gates": hard_gates, "requirement_gap_matrix": requirement_gap_matrix,
    }
