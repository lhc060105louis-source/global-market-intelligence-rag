# -*- coding: utf-8 -*-
"""Shared data contracts for the customer, creator, and B2B modules.

All modules import this package to keep enums, fields, and event formats
consistent across the application.
"""
from overseas_shared.enums import (
    Country,
    RegType,
    ImpactLevel,
    Priority,
    MaterialStatus,
    ClientType,
    SourceLevel,
    RegulationStatus,
    ProjectStage,
    ProjectLevel,
    SourceType,
    AccessMethod,
)
from overseas_shared.schemas import (
    MaterialItem,
    Regulation,
    Project,
    ClientProfile,
    DataSource,
)
from overseas_shared.events import (
    VOCAlertToB,
    RegulationChange,
    KOLRiskAlert,
)

__all__ = [
    # Enums
    "Country",
    "RegType",
    "ImpactLevel",
    "Priority",
    "MaterialStatus",
    "ClientType",
    "SourceLevel",
    "RegulationStatus",
    "ProjectStage",
    "ProjectLevel",
    "SourceType",
    "AccessMethod",
    # Schemas
    "MaterialItem",
    "Regulation",
    "Project",
    "ClientProfile",
    "DataSource",
    # Events
    "VOCAlertToB",
    "RegulationChange",
    "KOLRiskAlert",
]
