# -*- coding: utf-8 -*-
"""Explainable partner recommendations based on project market-access gaps."""
from __future__ import annotations

from datetime import date


RULE_VERSION = "gap-partner/1.0"
EVIDENCE_CHECKED_AT = date(2026, 8, 14).isoformat()


# The demo catalogue includes organizations with public evidence. It supports discovery and does not imply an established partnership.
PARTNER_CATALOG = [
    {
        "id": "partner-vde-tic",
        "name": "VDE Testing and Certification Institute",
        "country": "Germany",
        "region_scope": ["Europe", "Germany"],
        "partner_type": "Certification and Testing Organization",
        "capability_categories": ["Qualification and Market Access", "Compliance and Material Readiness", "Technology and Solution Fit"],
        "recommended_role": "Candidate for certification testing, type approval, and market-access evidence",
        "evidence": [{
            "title": "VDE Automotive and E-Mobility Testing and Certification Services",
            "url": "https://www.vde.com/tic-en/industries/automotive-and-e-mobility",
            "source_type": "official",
            "checked_at": EVIDENCE_CHECKED_AT,
            "summary": "Official information describes vehicle, component, and charging-infrastructure testing and certification capabilities.",
        }],
        "risk": "Confirm whether the specific tender accepts its certificates; verify testing scope, lead time, and fees.",
        "introduction_required": False,
    },
    {
        "id": "partner-tuv-rheinland",
        "name": "TÜV Rheinland",
        "country": "Germany",
        "region_scope": ["Europe", "Germany"],
        "partner_type": "Certification and Testing Organization",
        "capability_categories": ["Qualification and Market Access", "Compliance and Material Readiness", "Technology and Solution Fit"],
        "recommended_role": "Candidate for charging-infrastructure compliance testing and market-access evidence",
        "evidence": [{
            "title": "TÜV Rheinland Charging Station Product Testing Services",
            "url": "https://www.tuv.com/world/en/charging-stations-product-testing.html",
            "source_type": "official",
            "checked_at": EVIDENCE_CHECKED_AT,
            "summary": "Official information describes charging-infrastructure safety, standards-conformity testing, and market-access services.",
        }],
        "risk": "Public capabilities do not automatically satisfy this project's eligibility clauses. Map the required standards and report types first.",
        "introduction_required": False,
    },
    {
        "id": "partner-kempower",
        "name": "Kempower",
        "country": "Finland",
        "region_scope": ["Europe", "Finland"],
        "partner_type": "Charging Solutions and Systems Integrator",
        "capability_categories": ["Product and Project Fit", "Technology and Solution Fit", "Localization and Delivery Capability"],
        "recommended_role": "Candidate for bus and heavy-duty charging and fleet charging management",
        "evidence": [{
            "title": "Kempower Charging Solutions",
            "url": "https://kempower.com/charging-solutions/",
            "source_type": "official",
            "checked_at": EVIDENCE_CHECKED_AT,
            "summary": "Official information describes DC fast charging, bus depots, pantographs, and fleet charging management.",
        }],
        "risk": "Verify delivery coverage in the target country, comparable project experience, and partnership interest; also check for potential competition.",
        "introduction_required": True,
    },
    {
        "id": "partner-bosch-aftermarket",
        "name": "Bosch Mobility Aftermarket",
        "country": "Germany",
        "region_scope": ["Europe", "Germany", "United Kingdom", "Denmark", "Italy", "Romania", "Croatia"],
        "partner_type": "After-sales, Diagnostics, and Spare-Parts Network",
        "capability_categories": ["Technology and Solution Fit", "Localization and Delivery Capability"],
        "recommended_role": "Candidate for local after-sales, diagnostic equipment, and spare-parts support",
        "evidence": [{
            "title": "Bosch Mobility Aftermarket Europe",
            "url": "https://www.boschaftermarket.com/xc/en/",
            "source_type": "official",
            "checked_at": EVIDENCE_CHECKED_AT,
            "summary": "Official information describes passenger and commercial vehicle diagnostics, repair equipment, spare parts, and European service information.",
        }],
        "risk": "A public service network does not replace project-specific authorization. Verify scope, response commitments, and partnership interest commercially.",
        "introduction_required": True,
    },
    {
        "id": "partner-wattif-ev",
        "name": "Wattif EV",
        "country": "Norway",
        "region_scope": ["Europe", "Germany", "United Kingdom"],
        "partner_type": "Charging Operations and Maintenance Provider",
        "capability_categories": ["Localization and Delivery Capability"],
        "recommended_role": "Candidate for charging operations, maintenance, and local customer support",
        "evidence": [{
            "title": "Wattif EV Charging Solutions",
            "url": "https://wattifev.com/",
            "source_type": "official",
            "checked_at": EVIDENCE_CHECKED_AT,
            "summary": "Official information describes charging-infrastructure deployment, management, and maintenance in Germany and other European markets.",
        }],
        "risk": "Public examples focus on destination charging. Verify high-power bus charging, scheduling integration, and project-specific SLAs.",
        "introduction_required": True,
    },
]


def _gap_view(row: dict) -> dict:
    return {
        "code": row["code"],
        "category": row["category"],
        "severity": row["severity"],
        "status": row["status"],
        "requirement": row["requirement"],
        "assessment": row["assessment"],
        "action": row["action"],
    }


def recommend_partners(admission: dict, project: dict) -> dict:
    """Match partners to open gaps while retaining evidence, risks, and manual-verification limits."""
    unresolved = [
        _gap_view(row) for row in admission.get("requirement_gap_matrix", [])
        if row.get("status") != "satisfied"
    ]
    project_country = project.get("country", "")
    candidates = []

    for partner in PARTNER_CATALOG:
        solved = [gap for gap in unresolved if gap["category"] in partner["capability_categories"]]
        if not solved:
            continue
        exact_country = project_country in partner["region_scope"]
        urgent = sum(gap["severity"] == "P0" for gap in solved)
        score = min(96, 42 + min(len(solved), 3) * 11 + urgent * 4 + (15 if exact_country else 7))
        confidence = "high" if exact_country else "medium"
        confidence_label = "High" if exact_country else "Medium"
        solved_names = ", ".join(dict.fromkeys(gap["category"] for gap in solved))
        candidates.append({
            "id": partner["id"],
            "name": partner["name"],
            "country": partner["country"],
            "region_scope": partner["region_scope"],
            "partner_type": partner["partner_type"],
            "capability_categories": partner["capability_categories"],
            "recommended_role": partner["recommended_role"],
            "solves_gaps": solved,
            "match_score": score,
            "confidence": confidence,
            "confidence_label": confidence_label,
            "recommendation_reason": f"Public capabilities align with {solved_names} gaps; {'public coverage is available in the target country' if exact_country else 'European capabilities are available, but target-country coverage must be confirmed'}.",
            "evidence": partner["evidence"],
            "risk": partner["risk"],
            "verification_status": "public_evidence_only",
            "verification_status_label": "Public evidence verified · commercial relationship unconfirmed",
            "manual_verification_required": True,
            "introduction_required": partner["introduction_required"],
            "data_label": "Public candidate · pending commercial verification",
        })

    candidates.sort(key=lambda item: (-item["match_score"], item["name"]))
    covered_codes = {gap["code"] for candidate in candidates for gap in candidate["solves_gaps"]}
    uncovered = [gap for gap in unresolved if gap["code"] not in covered_codes]
    return {
        "rule_version": RULE_VERSION,
        "project_id": project.get("id"),
        "profile_id": admission.get("profile_id"),
        "admission_decision": admission.get("decision"),
        "admission_decision_label": admission.get("decision_label"),
        "gap_summary": unresolved,
        "uncovered_gaps": uncovered,
        "coverage": {
            "gap_count": len(unresolved),
            "covered_gap_count": len(covered_codes),
            "candidate_count": len(candidates),
        },
        "candidates": candidates,
        "disclaimer": "Recommendations are for candidate discovery only. They do not confirm partner credentials, partnership interest, or satisfaction of project requirements. Verify manually and obtain written confirmation before bidding.",
    }
