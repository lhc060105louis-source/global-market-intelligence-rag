# -*- coding: utf-8 -*-
"""Fixed Week 7 demo case for project access assessment and gap-driven partner recommendations."""
from __future__ import annotations


CASE_VERSION = "admission-case/1.0"


def get_admission_demo_case() -> dict:
    """Return a standalone one-page demo case that separates simulated information from public facts."""
    matrix = [
        {"code": "QUAL-01", "category": "Company Registration", "requirement": "German commercial registration (Handelsregister)",
         "evidence": "The simulated company supplied registration documents for its German subsidiary", "status": "satisfied", "gap_level": "",
         "action": "Recheck registration status and authorized signatories before bidding"},
        {"code": "QUAL-02", "category": "Financial Capability Evidence", "requirement": "Audited financial statements for the past three years and a parent-company guarantee",
         "evidence": "The simulated company says its parent company can provide a guarantee", "status": "partial", "gap_level": "P1",
         "action": "Obtain the formal guarantee and check the tender's financial thresholds"},
        {"code": "QUAL-03", "category": "Product Certification", "requirement": "VDE testing, CE marking, and ISO 15118 compliance evidence",
         "evidence": "CE marking is available; VDE testing and ISO 15118 compliance evidence are missing", "status": "missing", "gap_level": "P0",
         "action": "Ask VDE or another organization to assess testing scope, lead time, and expedited options"},
        {"code": "QUAL-04", "category": "Metering Certification", "requirement": "MID and German Eichrecht metering compliance",
         "evidence": "The simulated company has not provided metering certification documents", "status": "missing", "gap_level": "P1",
         "action": "Confirm the equipment billing model and complete the metering-regulation applicability assessment"},
        {"code": "QUAL-05", "category": "Project Experience", "requirement": "At least two comparable bus-charging project references",
         "evidence": "Only two commercial energy-storage projects are available; no public-transit projects", "status": "missing", "gap_level": "P0",
         "action": "Assess a consortium or subcontracting role and engage a partner with bus references"},
        {"code": "QUAL-06", "category": "Technology Solution", "requirement": "Plug-in and pantograph bus-charging solutions",
         "evidence": "DC charging capability is available; pantograph and scheduling integration evidence is limited", "status": "partial", "gap_level": "P2",
         "action": "Provide pantograph, power-allocation, and fleet-scheduling interface plans"},
        {"code": "QUAL-07", "category": "Tender Documents", "requirement": "Complete German-language tender documents and declarations",
         "evidence": "The simulated company has not prepared German-language bid documents", "status": "missing", "gap_level": "P1",
         "action": "Prepare a German-language document list and arrange local legal and procurement-language review"},
        {"code": "QUAL-08", "category": "Operations and Maintenance Plan", "requirement": "German local operations, response SLA, and spare-parts plan",
         "evidence": "An 18-person team is based in Frankfurt, but no bus operations and maintenance plan is available", "status": "missing", "gap_level": "P1",
         "action": "Verify the local operations partner's bus capabilities and document an SLA"},
    ]
    partners = [
        {
            "id": "vde", "name": "VDE Testing and Certification Institute", "partner_type": "Certification and Testing Organization",
            "solves_gap_codes": ["QUAL-03", "QUAL-04"], "confidence": "high", "confidence_label": "High",
            "role": "Confirm the compliance pathway for charging-equipment testing, ISO 15118, and metering",
            "evidence": "Publicly offers testing and certification services for vehicles, components, and charging infrastructure.",
            "evidence_url": "https://www.vde.com/tic-en/industries/automotive-and-e-mobility",
            "risk": "Confirm applicable standards, certificate acceptance, testing lead times, and fees directly with the organization.",
            "manual_verification": "No intermediary introduction is required; the technical team should request written confirmation of scope.",
        },
        {
            "id": "kempower", "name": "Kempower", "partner_type": "Bus-Charging Solutions Provider",
            "solves_gap_codes": ["QUAL-05", "QUAL-06"], "confidence": "medium", "confidence_label": "Medium",
            "role": "Address project-experience and technology gaps with German bus-charging references and pantograph solutions",
            "evidence": "Public materials show a bus-charging project in Karlsruhe, Germany, and pantograph products.",
            "evidence_url": "https://kempower.com/news/modern-charging-infrastructure-for-electric-buses-in-karlsruhe-vbk-opts-for-kempower-solution/",
            "risk": "A direct competitive relationship may exist. Partnership interest, tender role, and reference authorization are unconfirmed.",
            "manual_verification": "Contact the company directly or request an introduction; confirm consortium or systems-partnership interest.",
        },
        {
            "id": "wattif", "name": "Wattif EV", "partner_type": "Charging Operations and Maintenance Provider",
            "solves_gap_codes": ["QUAL-08"], "confidence": "medium", "confidence_label": "Medium",
            "role": "Address gaps in local German charging operations, maintenance, and customer support",
            "evidence": "Public materials describe charging-infrastructure management and maintenance in Germany and other European markets.",
            "evidence_url": "https://wattifev.com/",
            "risk": "Public examples focus on destination charging. Verify high-power bus charging and scheduling integration experience.",
            "manual_verification": "Verify bus references, response SLAs, and German service coverage directly.",
        },
    ]
    return {
        "case_id": "BVG-EBUS-2026-DEMO",
        "case_version": CASE_VERSION,
        "data_as_of": "2026-08-14",
        "labels": ["Business Case", "Simulated Company", "Method Demonstration", "Project Deadline Passed"],
        "project": {
            "name": "BVG 106-Bus Electric Fleet Operations Service Project",
            "buyer": "Berliner Verkehrsbetriebe (BVG)",
            "country": "Germany",
            "budget": "Approx. €721M",
            "deadline": "2026-06-15",
            "status": "closed",
            "status_label": "Deadline Passed",
            "scope": "Approximately 106 battery-electric buses and related operations and charging capabilities, divided into five lots, with contracts planned to cover 2030–2045.",
            "source_url": "https://ted.europa.eu/en/notice/164370-2026/pdf",
            "source_label": "TED 164370-2026",
            "official_context_url": "https://www.bvg.de/de/unternehmen/medienportal/pressemitteilungen/20260511-pm-subunternehmen-e-busse",
        },
        "enterprise": {
            "name": "EnPower New Energy Technology (Europe) Ltd.",
            "simulation_label": "Fully simulated; does not represent a real company",
            "type": "German subsidiary of a Chinese energy-storage and charging-systems integrator",
            "location": "Frankfurt", "founded": "2022", "team_size": "18",
            "capabilities": ["Energy-storage systems", "DC charging stations", "Integrated solar, storage, and charging"],
            "certifications": ["CE", "ISO 9001", "ISO 14001"],
            "experience": "Two commercial energy-storage projects in Germany totaling about 5 MWh; no public-sector public-transit project experience",
            "target_role": "Charging-infrastructure subcontractor or systems supplier",
        },
        "current_decision": {
            "decision": "no_go", "label": "No-Go: Not Currently Open for Bidding",
            "reason": "The project tender deadline had passed as of the case data date. The platform should not present a historical project as open for bidding.",
        },
        "method_decision": {
            "decision": "hold", "label": "Hold: Close Gaps and Reassess",
            "reason": "If assessed while the tender was open, the missing product certification and comparable project experience would still be two P0 gaps. Do not commit full tender resources yet.",
            "hard_gate_codes": ["QUAL-03", "QUAL-05"],
        },
        "qualification_matrix": matrix,
        "partner_rules": [
            "Each candidate must address at least one open gap; do not make generic industry recommendations.",
            "Every candidate must include a public source, confidence level, risk, and manual verification requirements.",
            "Public capabilities do not confirm credentials, partnership interest, or acceptance for this project.",
            "Clearly flag equipment providers that may be competitors; do not automatically recommend an introduction.",
        ],
        "partners": partners,
        "next_actions": [
            "Stop allocating bid resources to this project; retain it as a German bus-market methodology example.",
            "Conduct a preliminary assessment of certification scope and lead time for VDE, ISO 15118, and MID/Eichrecht requirements.",
            "Check consortium or systems-partnership interest with Kempower and agree on bus-reference usage rights.",
            "Verify Wattif's high-power bus-charging maintenance experience, German coverage, and response SLA.",
            "Reuse the completed certification, reference, and operations capabilities for the next open German project.",
        ],
        "disclaimer": "This case demonstrates the platform methodology. The company profile is simulated; partners are candidates identified from public information only. Verify eligibility requirements against the original procurement documents and professional review.",
    }
