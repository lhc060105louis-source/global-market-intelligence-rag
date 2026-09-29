# -*- coding: utf-8 -*-
"""Cross-module event contracts. Phase 1 defines the format without wiring it in.

All application modules import these definitions so each can understand events
published by the others.

Usage:
  from overseas_shared.events import VOCAlertToB
  alert = VOCAlertToB(brand="BYD", country="DE", sentiment="complaint", severity="high")
  # Serialize to JSON and write to the events table or a message queue.
  # The receiving module imports the same class to deserialize and consume it.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class VOCAlertToB:
    """Customer VOC alert sent to B2B when negative sentiment surges.

    The B2B module can match relevant regulations, flag a P0 gap, and prepare
    customer-retention messaging after receiving the alert.
    """
    brand: str                           # Brand, e.g. "BYD"
    country: str                         # ISO 3166-1 alpha-2 code, e.g. "DE"
    sentiment: str                       # Dominant sentiment, e.g. complaint / anger / concern
    topic: str = ""                      # Trending topic, e.g. brake noise / overstated driving range
    severity: str = "medium"             # high / medium / low
    regulation_hints: list[str] = field(default_factory=list)  # Potentially relevant regulation keywords
    signal_count: int = 0                # Number of signals
    detected_at: str = ""                # ISO 8601 datetime


@dataclass
class RegulationChange:
    """Regulation change notification sent from B2B to customer and creator modules.

    Customer marketing copy and creator talking points may need review when a
    regulation is added, amended, or repealed.
    """
    regulation_id: str                   # REG-001
    regulation_name: str = ""            # Regulation name
    country: list[str] = field(default_factory=list)   # Affected ISO 3166-1 alpha-2 country codes
    change_type: str = "effective"       # effective / amended / repealed
    summary: str = ""                    # One-sentence change summary
    affected_scenarios: list[str] = field(default_factory=list)  # Retail / fleet / public transit
    affected_brands: list[str] = field(default_factory=list)     # Affected automotive brands
    published_at: str = ""               # ISO 8601 datetime


@dataclass
class KOLRiskAlert:
    """Creator-content compliance risk alert sent to B2B.

    The B2B module can match regulations, assess customer impact, and prepare
    response recommendations after receiving the alert.
    """
    brand: str                           # Brand
    country: str                         # ISO 3166-1 alpha-2 country code
    creator_name: str = ""               # Creator name
    platform: str = ""                   # YouTube / TikTok / Instagram
    severity: str = "medium"             # high / medium / low
    topic: str = ""                      # Controversial topic
    regulation_hint: str = ""            # Potentially relevant regulation identified by the creator module
    detected_at: str = ""                # ISO 8601 datetime
