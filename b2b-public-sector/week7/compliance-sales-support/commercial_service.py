# -*- coding: utf-8 -*-
"""Commercial offers, specialist service boundaries, and 14-day sprint details for Week 7."""
from __future__ import annotations


CATALOG_VERSION = "commercial-offers/1.0"
PRICING_NOTE = "All paid prices are unvalidated pricing assumptions and do not constitute a formal quote or offer."


OFFERS = [
    {
        "id": "free", "name": "Free", "product_type": "subscription",
        "price_eur": 0, "price_label": "Free", "price_unit": "Trial / self-assessment",
        "quote_status": "free", "positioning": "Use public information for initial research into European project opportunities.",
        "audience": "Newcomers exploring the market and junior tender staff",
        "included": ["Basic information on public projects", "Initial AI screening of access rules", "General material gap checks", "Basic automation tools"],
        "excluded": ["No analyst review", "No localized gap diagnosis", "No partner recommendations or introductions", "No formal diagnostic report", "No expedited service"],
        "cta": "Start Free Trial", "demo_mode": "visitor", "upgrade_to": "professional",
        "upgrade_path": "Free → Professional: unlock detailed access assessments and full machine-generated self-assessment reports",
    },
    {
        "id": "professional", "name": "Professional", "product_type": "subscription",
        "price_eur": 499, "price_label": "€499", "price_unit": "per organization / month",
        "quote_status": "hypothesis", "positioning": "Frequent project screening and in-depth self-assessment for a single project.",
        "audience": "Tender specialists and project owners",
        "included": ["All Free features", "Detailed Go / Hold / No-Go assessment", "Material gap scans by dimension", "Machine-generated project self-assessment reports", "Monthly access trends and bid/no-bid risks"],
        "excluded": ["No customized analyst review", "No manual partner introductions", "No hands-on gap remediation", "No expedited tender sprint"],
        "cta": "Switch to Professional Demo", "demo_mode": "professional", "upgrade_to": "enterprise",
        "upgrade_path": "Professional → Enterprise: add team collaboration, company profiles, and localized capability assessments",
    },
    {
        "id": "enterprise", "name": "Enterprise", "product_type": "subscription",
        "price_eur": 1499, "price_label": "€1,499", "price_unit": "per organization / month",
        "quote_status": "hypothesis", "positioning": "Long-term project and compliance risk management for department-level teams.",
        "audience": "European business and compliance owners and department-level expansion teams",
        "included": ["All Professional features", "Ongoing company profile and credential management", "Multi-member permissions and collaboration boards", "High-precision localized gap assessments", "Bulk access screening and compliance alerts"],
        "excluded": ["No customized in-depth analyst work", "No guaranteed partner results", "No guarantee that materials will be completed", "No 14-day expedited delivery"],
        "cta": "Switch to Enterprise Demo", "demo_mode": "enterprise", "upgrade_to": "standard_service",
        "upgrade_path": "Enterprise → Standard Service / 14-Day Sprint: analyst-led delivery for a single project",
    },
    {
        "id": "standard_service", "name": "Standard Specialist Service", "product_type": "service",
        "price_eur": 7500, "price_label": "From €7,500", "price_unit": "per project",
        "quote_status": "hypothesis", "positioning": "Standard gap-remediation service for priority projects without an urgent deadline.",
        "audience": "Priority projects with a medium-term horizon and no imminent bid deadline",
        "included": ["Analyst review of access decisions", "Complete P0–P3 gap assessment", "Localized capability diagnosis", "Shortlist of standard partner candidates", "Formal internal report", "Remediation actions and checklist"],
        "excluded": ["No 14-day expedited closeout", "No priority analyst scheduling", "No daily progress management", "Not suitable for last-minute bid emergencies"],
        "cta": "View Service Scope", "demo_mode": "", "upgrade_to": "sprint_14d",
        "upgrade_path": "Standard Service → 14-Day Sprint: for projects near deadline that need dedicated resources",
    },
    {
        "id": "sprint_14d", "name": "14-Day Sprint Service", "product_type": "service",
        "price_eur": 12000, "price_label": "From €12,000", "price_unit": "per project / 14 days",
        "quote_status": "hypothesis", "positioning": "Highest-priority expedited service for projects approaching a bid deadline.",
        "audience": "High-value core projects with significant gaps that are difficult to address internally before the deadline",
        "included": ["Dedicated analyst for 14 days", "Daily progress updates and fixed SLA", "P0 priority re-ranking", "Urgent materials-completion guidance", "Partner screening and risk review", "Final access decision and implementation checklist"],
        "excluded": ["No guarantee of winning", "No guarantee that partners will engage successfully", "No guarantee that client materials will be completed", "No responsibility for client-side delays"],
        "cta": "Apply for 14-Day Sprint", "demo_mode": "", "upgrade_to": "",
        "upgrade_path": "Submit application → Confirm scope → Reserve schedule → Deliver on Days 1–14",
    },
]


SPRINT = {
    "application_materials": [
        "Company credentials and past EU tender records", "Full notice and attachments for the target project",
        "Overview of the existing European team and local partnership resources", "Bid deadline, internal owner, and available resources",
    ],
    "scope": [
        "One target project only", "Scope includes access assessment, gap prioritization, remediation paths, and partner recommendations",
        "Confirm service boundaries in writing before kickoff; additional projects or requirements require a change request",
    ],
    "timeline": [
        {"days": "Day 1", "title": "Requirement Review", "output": "Full project requirement breakdown and initial Go / No-Go decision"},
        {"days": "Day 2—3", "title": "Gap Assessment", "output": "Complete P0 / P1 / P2 / P3 gap table"},
        {"days": "Day 4—6", "title": "Localization Review", "output": "Localized capability gaps and priorities"},
        {"days": "Day 7—9", "title": "Partner Screening", "output": "Candidates, evidence, confidence, and risks"},
        {"days": "Day 10—12", "title": "Remediation Plan", "output": "Action priorities and implementation steps"},
        {"days": "Day 13", "title": "Final Review", "output": "Risk summary and final access decision"},
        {"days": "Day 14", "title": "Delivery Package", "output": "Delivery review and next-step actions"},
    ],
    "deliverables": [
        "Final project-access decision report", "Consolidated P0–P3 gap register", "Remediation list for missing materials",
        "Localized capability remediation plan", "Partner shortlist with risks, evidence, and gap coverage", "14-day implementation tracker",
    ],
    "sla": ["Confirm Day 1 after scope and materials are complete", "Deliver in phases over 14 calendar days", "Client to provide key materials and decisions within 24 hours"],
    "client_cooperation": ["Respond to material requests within 24 hours", "Confirm scope promptly and avoid unplanned additions", "Share internal blockers and decision changes in a timely manner"],
    "change_rules": [
        "Late client materials: delivery dates move accordingly; this is not grounds for a refund",
        "Additional projects or scope: re-confirm pricing, fees, and schedule",
        "Provider delay: one additional Q&A review or agreed SLA compensation",
    ],
    "why_premium": ["Reserves scarce analyst capacity", "Provides a firm daily SLA for 14 days", "Reduces risk when bid deadlines are close", "Supports investment decisions for high-value projects"],
    "not_promised": ["No guarantee of winning", "No guarantee of successful partner engagement", "No guarantee that all client remediation will be completed", "No responsibility for falsified or noncompliant materials or client delays"],
}


AUTOMATION_VS_ANALYST = {
    "platform": ["Project retrieval, rule matching, and initial scoring", "Automated material gap checks", "Basic credential and localization comparisons", "Reports, trackers, permissions, and workflow automation"],
    "analyst": ["Validate machine errors and hidden local requirements", "Prioritize critical and acceptable gaps", "Review partner confidence and partnership risks", "Adjust daily scheduling and tailor implementation strategies", "Deliver formal conclusions for internal approval"],
}


FAQ = [
    {"question": "What is the main difference between Free and paid plans?", "answer": "Free supports trials with public information. Subscriptions provide full eligibility assessments and gap pathways. Specialist services add analyst-led delivery."},
    {"question": "Can Enterprise replace a specialist service?", "answer": "No. Enterprise supports ongoing self-assessment and team collaboration; specialist services provide hands-on work for a specific project."},
    {"question": "Why does the 14-Day Sprint cost more?", "answer": "It reserves analyst capacity, provides a daily SLA, supports urgent risk decisions, and delivers intensive project work."},
    {"question": "Does a purchase guarantee that we can bid or win?", "answer": "No. The service provides reviewed assessments and action pathways. Results still depend on procurement rules, client materials and execution, and external partners."},
    {"question": "Can I combine a specialist service with a subscription?", "answer": "Yes. The subscription supports daily monitoring and self-assessment; specialist services provide hands-on delivery for priority projects."},
]


def get_commercial_catalog() -> dict:
    return {
        "version": CATALOG_VERSION,
        "currency": "EUR",
        "pricing_note": PRICING_NOTE,
        "offers": OFFERS,
        "sprint": SPRINT,
        "automation_vs_analyst": AUTOMATION_VS_ANALYST,
        "faq": FAQ,
        "upgrade_path": ["free", "professional", "enterprise", "standard_service", "sprint_14d"],
    }
