# -*- coding: utf-8 -*-
"""Enums shared by the customer VOC, creator, and B2B workflows.

All three applications import these definitions so that each shared value has
the same serialized representation across services.
"""
from enum import Enum


class Country(str, Enum):
    """Country or region codes using ISO 3166-1 alpha-2 where applicable.

    This replaces inconsistent values such as localized country names,
    country codes, and broad regional labels across the applications.
    """

    DE = "DE"
    FR = "FR"
    UK = "UK"
    ES = "ES"
    IT = "IT"
    EU = "EU"


class RegType(str, Enum):
    """Regulatory categories aligned with the compliance taxonomy."""

    ACCESS = "Access Certification"
    BATTERY = "Battery Compliance"
    CYBER = "Cybersecurity"
    DATA_AI = "Data and AI"
    CARBON = "Carbon Compliance"
    EMISSION = "Emissions Compliance"
    MATERIAL = "Materials Compliance"
    PROCUREMENT = "Public Procurement"
    SAFETY = "Safety Assessment"
    INFRA = "Infrastructure"


class ImpactLevel(str, Enum):
    """Impact severity."""

    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class Priority(str, Enum):
    """Document priority levels (P0-P3), aligned with PRD section 8.3.

    P0 is mandatory and can affect market access or bid eligibility.
    P1 affects scoring, trust, or negotiation.
    P2 improves competitiveness.
    P3 should be monitored and may not currently apply.
    """

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class MaterialStatus(str, Enum):
    """Document preparation status, aligned with PRD section 8.4."""

    UNCONFIRMED = "Unconfirmed"
    READY = "Ready"
    MISSING = "Missing"
    NEED_UPDATE = "Needs Update"
    REVIEWING = "Under Review"
    EXPIRED = "Expired"
    NOT_APPLICABLE = "Not Applicable"


class ClientType(str, Enum):
    """B2B customer types aligned with the Week 2 sales-support template."""

    GOVERNMENT = "Government / Municipality"
    BUS_OPERATOR = "Public Transit Operator"
    LOGISTICS = "Logistics Fleet"
    ENTERPRISE_FLEET = "Corporate Fleet"
    MOBILITY_PLATFORM = "Mobility Platform"


class SourceLevel(str, Enum):
    """Source reliability levels aligned with PRD v2.0 section 9.3.

    T1 represents official primary sources such as EUR-Lex, TED, and the
    European Commission. T2 covers authoritative aggregators such as ACEA,
    EAFO, and Euro NCAP. T3 covers industry media and research such as JATO,
    Reuters, and Autovista. T4 sources are unverified leads and must not be
    used in formal reports.
    """

    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    T4 = "T4"


class RegulationStatus(str, Enum):
    """Review status for regulatory records."""

    DRAFT = "Draft"
    PENDING = "Pending Review"
    APPROVED = "Approved"
    DEPRECATED = "Deprecated"


class ProjectStage(str, Enum):
    """Lifecycle stage for public-sector and enterprise projects."""

    LEAD = "New Lead"
    EVALUATING = "Under Evaluation"
    PREPARING = "Preparing Bid"
    SUBMITTED = "Submitted"
    WON = "Won"
    LOST = "Lost"
    TERMINATED = "Terminated"


class ProjectLevel(str, Enum):
    """Project investment posture."""

    PRIORITY = "Priority Follow-up"
    OBSERVING = "Monitoring"
    HOLD = "On Hold"


class SourceType(str, Enum):
    """Types of intelligence sources."""

    REGULATION = "Regulation"
    POLICY = "Policy"
    PROCUREMENT = "Procurement"
    INDUSTRY = "Industry Data"
    NEWS = "News"


class AccessMethod(str, Enum):
    """Methods used to retrieve source data."""

    API = "API"
    WEB = "Web"
    RSS = "RSS"
    MANUAL = "Manual"
