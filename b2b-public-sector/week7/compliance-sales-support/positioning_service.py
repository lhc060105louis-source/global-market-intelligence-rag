# -*- coding: utf-8 -*-
"""Product positioning, user personas, and key use cases for Chinese new-energy companies."""
from __future__ import annotations


POSITIONING_VERSION = "product-positioning/1.0"


def get_product_positioning() -> dict:
    return {
        "version": POSITIONING_VERSION,
        "statement": "A platform for European project decisions and execution for Chinese new-energy companies",
        "value_proposition": "Go beyond discovering projects: assess bid eligibility, identify missing materials and local capabilities, and decide who can help close gaps and how to proceed.",
        "personas": [
            {
                "id": "strategy", "role": "European Business or Strategy Owner", "short_role": "Business and Strategy",
                "goal": "Choose which markets to enter and which projects merit investment",
                "pain": "Scattered information makes it difficult to prioritize markets and identify capabilities to build in advance",
                "current_method": "Search notices manually and rely on agents and personal experience",
                "outcome": "View market opportunities, company fit, and local capability gaps in one decision workspace",
                "route": {"page": "information", "tab": "feed"}, "cta": "View Market and Regulation Intelligence",
            },
            {
                "id": "bid", "role": "Tender or Project Owner", "short_role": "Tender and Projects",
                "goal": "Decide whether a specific project is worth pursuing and coordinate execution",
                "pain": "Eligibility, competition, and resource decisions depend on spreadsheets and personal experience",
                "current_method": "Score projects manually and make Go / No-Go decisions from experience",
                "outcome": "Get an explainable decision based on seven scores, hard gates, and Go / Hold / No-Go criteria",
                "route": {"page": "ecosystem", "tab": "profile"}, "cta": "Generate Access Assessment",
            },
            {
                "id": "compliance", "role": "Compliance or Materials Owner", "short_role": "Compliance and Materials",
                "goal": "Prepare the certifications, declarations, and evidence required for a tender",
                "pain": "Regulations are complex, materials are easily missed, and owners and timelines are unclear",
                "current_method": "Review regulations one by one and repeatedly consult third parties",
                "outcome": "Track P0–P3 gaps, material status, owners, and remediation tasks",
                "route": {"page": "information", "tab": "regulations"}, "cta": "Check Material Gaps",
            },
        ],
        "scenarios": [
            {
                "id": "can_bid", "question": "Can we bid for this project?", "icon": "01",
                "generic_limit": "Generic platforms often provide only relevance scores or broad bid/no-bid recommendations.",
                "solution": "Assess seven dimensions of company fit and P0 hard gates to produce a Go / Hold / No-Go decision.",
                "next_step": "Generate Company Access Assessment", "route": {"page": "ecosystem", "tab": "profile"},
                "paid_reason": "Professional unlocks the full decision rationale and gap matrix",
            },
            {
                "id": "missing_materials", "question": "Which materials are missing?", "icon": "02",
                "generic_limit": "Notice searches do not convert requirements into a materials checklist for Chinese new-energy companies.",
                "solution": "Translate regulations and project requirements into P0–P3 material gaps and trackable tasks.",
                "next_step": "View Regulations and Materials", "route": {"page": "information", "tab": "regulations"},
                "paid_reason": "Professional provides complete gaps, ownership, and export capabilities",
            },
            {
                "id": "local_capability", "question": "Which local capabilities are missing, and how can we add them?", "icon": "03",
                "generic_limit": "Generic project databases rarely model local after-sales, spare parts, certification, and operations gaps.",
                "solution": "Identify localization gaps, then recommend candidates with public evidence, risks, and verification requirements.",
                "next_step": "Assess Gaps and Find Partners", "route": {"page": "ecosystem", "tab": "profile"},
                "paid_reason": "Enterprise and specialist services support partner checks and hands-on execution",
            },
        ],
        "differentiators": [
            {"title": "From Project Discovery to Bid Decisions", "description": "Seven scores, hard gates, and Go / Hold / No-Go decisions."},
            {"title": "Visualized Compliance Gaps", "description": "Translate European requirements into P0–P3 materials and action lists."},
            {"title": "Local Gap Closure and Partner Support", "description": "Connect partner candidates to specific gaps, evidence, risks, and verification limits."},
            {"title": "Built for Chinese New-Energy Expansion", "description": "Cover vehicles, charging, energy storage, certification, and European localization capabilities."},
            {"title": "Automation with Analyst Review", "description": "Automate routine self-assessments and provide analyst-led delivery for priority projects."},
        ],
        "comparison": [
            {"pain": "Found a project but unsure about eligibility", "generic_limit": "Relevance scoring only",
             "solution": "Company-level access assessment", "paid_reason": "Pay for an explainable investment decision"},
            {"pain": "Unclear about European materials requirements", "generic_limit": "No mapping to company evidence",
             "solution": "P0–P3 gap matrix", "paid_reason": "Pay to reduce omissions and rework"},
            {"pain": "Missing local delivery capabilities", "generic_limit": "No localization capability model",
             "solution": "Localization gap assessment", "paid_reason": "Pay for a company-specific assessment"},
            {"pain": "Unsure who can close the gaps", "generic_limit": "No partner recommendations linked to gaps",
             "solution": "Evidence-based partner candidates", "paid_reason": "Pay for efficient verification and implementation paths"},
            {"pain": "Gap between analysis and execution", "generic_limit": "Automated results only",
             "solution": "14-day analyst sprint", "paid_reason": "Pay to reserve analyst time and a firm SLA"},
        ],
    }
