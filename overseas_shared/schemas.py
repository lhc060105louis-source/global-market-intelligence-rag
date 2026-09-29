# -*- coding: utf-8 -*-
"""Shared entity field definitions for all application modules.

Business stakeholders can review this file alongside the specification.
Field names use snake_case; enum values are defined in overseas_shared.enums.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# Enums are referenced within this package to keep import paths stable.
# For type hints, import the required types from overseas_shared.enums.


@dataclass
class MaterialItem:
    """A bid-material requirement aligned with the compliance specification."""
    name: str                              # Material name, e.g. "CSMS certificate"
    priority: str                          # P0 / P1 / P2 / P3
    status: str = "Unconfirmed"           # Unconfirmed / Ready / Missing / Needs Update / Under Review / Expired / Not Applicable
    owner: str = ""                        # Owner
    due_date: str = ""                     # Due date


@dataclass
class Regulation:
    """A regulation record aligned with the regulation field specification."""
    regulation_id: str                     # REG-001
    name: str                              # Regulation name
    official_number: str = ""              # Official number, e.g. (EU) 2023/1542
    issuer: str = ""                       # Issuing authority
    type: str = ""                         # Regulation type; preferably a RegType enum value
    country: list[str] = field(default_factory=list)  # Applicable ISO 3166-1 alpha-2 codes, e.g. ["DE", "EU"]
    applicable_product: list[str] = field(default_factory=list)
    effective_date: str = ""               # Effective date
    impact_level: str = ""                 # High / Medium / Low
    core_requirement: str = ""             # Core requirement summarized after manual verification
    official_source: str = ""              # Official source URL
    last_verified_at: str = ""             # Most recent verification date
    status: str = "Pending Review"        # Draft / Pending Review / Approved / Deprecated
    version: str = "v1.0"
    materials: list[MaterialItem] = field(default_factory=list)  # Required materials
    local_partner_duty: str = ""           # Local partner responsibilities
    gap: str = ""                          # Compliance gap description
    linked_intelligence_ids: list[str] = field(default_factory=list)


@dataclass
class Project:
    """A public-sector or enterprise procurement opportunity."""
    project_id: str                        # PRJ-001
    project_name: str                      # Official tender or project name
    country: str = ""                      # ISO2
    client_type: str = ""                  # Client type
    buyer_name: str = ""                   # Procuring organization
    scenario: str = ""                     # Use case
    amount: float = 0.0                    # Contract value
    currency: str = "EUR"
    deadline: str = ""
    source_url: str = ""
    description: str = ""
    stage: str = "Under Evaluation"      # New Lead / Under Evaluation / Preparing Bid / Submitted / Won / Lost / Terminated
    scores: dict = field(default_factory=dict)  # Seven-dimension score, e.g. {scale, buyer, technical, ...}
    total_score: int = 0
    project_level: str = "On Hold"        # Priority Follow-up / Monitoring / On Hold
    linked_regulation_ids: list[str] = field(default_factory=list)


@dataclass
class ClientProfile:
    """A B2B customer profile used by the sales-support workflow."""
    client_type: str                       # Client type
    region: str = ""                       # Country code (ISO 3166-1 alpha-2)
    scenario: str = ""                     # Use case
    painpoints: list[str] = field(default_factory=list)
    focus_points: list[str] = field(default_factory=list)
    product_direction: list[str] = field(default_factory=list)
    tech_solution: list[str] = field(default_factory=list)
    service_plan: list[str] = field(default_factory=list)
    linked_regulations: list[str] = field(default_factory=list)


@dataclass
class DataSource:
    """A public data source used by the application."""
    source_id: str                         # SRC-001
    name: str                              # Source name
    type: str = ""                         # Data type (regulation, policy, procurement, industry data, etc.)
    level: str = "T4"                      # Source reliability tier, T1-T4
    url: str = ""
    frequency: str = ""                    # Update frequency
    access_method: str = ""                # Access method (API / web / RSS / manual)
    free: bool = True
    module: str = ""                       # Owning module (regulations, industry data, public-sector opportunities, etc.)
    last_checked_at: str = ""
