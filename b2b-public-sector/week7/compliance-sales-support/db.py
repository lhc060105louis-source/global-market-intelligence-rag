# -*- coding: utf-8 -*-
"""SQLAlchemy data layer that replaces raw sqlite3 and provides a shared ORM.

Tables and seed data are created on first run. Function signatures remain
backward compatible to minimize changes in app.py.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from datetime import datetime

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session as OrmSession

from models import Base, Regulation, MaterialStatus, Project
import data_regulations as R
import data_clients as C

DB_PATH = Path(__file__).resolve().parent / "compliance.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
_engine = create_engine(DATABASE_URL, echo=False, connect_args=_connect_args, pool_pre_ping=True)


def get_session() -> OrmSession:
    return OrmSession(_engine)


def create_tables() -> None:
    """Create missing tables without loading seeds; used by standalone task workers."""
    Base.metadata.create_all(_engine, checkfirst=True)
    _ensure_rag_columns()


def _ensure_rag_columns() -> None:
    """Apply a lightweight migration that adds push fields to existing SQLite databases."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    required = {
        "regulations": {"rag_version": "INTEGER NOT NULL DEFAULT 1", "rag_status": "VARCHAR(20) NOT NULL DEFAULT 'draft'", "published_at": "DATETIME"},
        "projects": {"rag_status": "VARCHAR(20) NOT NULL DEFAULT 'draft'", "version_no": "INTEGER NOT NULL DEFAULT 1", "published_at": "DATETIME"},
        "intelligence_items": {"review_status": "VARCHAR(20) NOT NULL DEFAULT 'draft'", "version_no": "INTEGER NOT NULL DEFAULT 1", "reviewed_at": "DATETIME", "published_at_rag": "DATETIME", "review_region": "VARCHAR(50) NOT NULL DEFAULT ''"},
        "sprint_applications": {"materials_ready": "TEXT NOT NULL DEFAULT '[]'", "target_deadline": "VARCHAR(30) NOT NULL DEFAULT ''", "resource_commitment": "VARCHAR(500) NOT NULL DEFAULT ''", "scope_confirmed": "BOOLEAN NOT NULL DEFAULT 0", "cooperation_confirmed": "BOOLEAN NOT NULL DEFAULT 0"},
    }
    with _engine.begin() as connection:
        schema = inspect(connection)
        tables = set(schema.get_table_names())
        for table, columns in required.items():
            if table not in tables:
                continue
            existing = {column["name"] for column in schema.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {ddl}'))
            if table == "regulations" and "rag_status" not in existing:
                connection.execute(text("UPDATE regulations SET rag_status='published' WHERE status='Approved'"))
            if table == "projects" and "rag_status" not in existing:
                connection.execute(text("UPDATE projects SET rag_status='published'"))


# ═══════════════════════════════════════════════
# Initialization
# ═══════════════════════════════════════════════

def bootstrap() -> None:
    create_tables()
    seed_if_empty()
    ensure_demo_enterprise_profiles()


def ensure_demo_enterprise_profiles() -> None:
    """Ensure two distinct P1 demo profiles are available for personalized matching."""
    from models import EnterpriseProfile
    profiles = [
        dict(
            org_name="BYD Europe (Demo Profile A)", target_countries='["DE","FR","UK","ES","IT"]',
            target_client_types='["Government","Public Transit Operator","Logistics Fleet"]', acceptable_scale="€5M–€100M",
            vehicle_types='["Electric Bus","Electric Truck","Passenger Car"]', powertrain_types='["Battery Electric"]',
            charging_capability="800V fast charging, battery passport, blade battery", software_capability="OTA/T-Box/ADAS Level 2+",
            existing_certs='["WVTA","CSMS (R155)","Euro NCAP 5-star"]',
            available_materials='["Battery Passport","Carbon Footprint Report","CSMS Certificate","TARA Report"]',
            has_eu_entity="Yes", local_after_sales='["Germany","United Kingdom","France","Netherlands"]',
            local_partners="Alexander Dennis (UK)", delivery_cycle="6–12 months",
            cooperation_mode="Technology Licensing and Joint Bidding", risk_preference="Medium", completeness=100,
        ),
        dict(
            org_name="China Bus Manufacturer (Demo Profile B)", target_countries='["IT","ES"]',
            target_client_types='["Public Transit Operator"]', acceptable_scale="€1M–€20M",
            vehicle_types='["Electric Bus"]', powertrain_types='["Battery Electric"]',
            charging_capability="400V standard charging", software_capability="Basic fleet management",
            existing_certs='["IATF 16949"]', available_materials='["Product Test Report"]',
            has_eu_entity="No", local_after_sales='[]', local_partners="",
            delivery_cycle="12–18 months", cooperation_mode="Vehicle Export", risk_preference="Conservative", completeness=100,
        ),
    ]
    with get_session() as session:
        existing = {p.org_name for p in session.query(EnterpriseProfile).all()}
        # Avoid duplicating profile A when an earlier BYD Europe demo profile exists.
        if any(name.startswith("BYD Europe") for name in existing):
            existing.add("BYD Europe (Demo Profile A)")
        for values in profiles:
            if values["org_name"] not in existing:
                session.add(EnterpriseProfile(**values))
        session.commit()


def seed_if_empty() -> None:
    with get_session() as s:
        if s.query(Regulation).count():
            return
        _seed_regulations(s)
        _seed_projects(s)


def _seed_regulations(s: OrmSession) -> None:
    for r in R.REGULATIONS:
        reg = Regulation(
            regulation_id=r["regulation_id"], name=r["name"],
            official_number=r.get("official_number", ""), issuer=r.get("issuer", ""),
            type=r["type"], scope=r["scope"],
            applicable_product=json.dumps(r.get("applicable_product", []), ensure_ascii=False),
            effective_date=r.get("effective_date", ""), impact_level=r["impact_level"],
            core_requirement=r["core_requirement"], official_source=r["official_source"],
            last_verified_at=r["last_verified_at"], status=r["status"], version=r["version"],
            rag_version=1,
            rag_status="published" if r["status"] == "Approved" else "draft",
            provide=json.dumps(r.get("provide", []), ensure_ascii=False),
            local_duty=r.get("local_duty", ""), gap=r.get("gap", ""),
            scenarios=json.dumps(r.get("scenarios", []), ensure_ascii=False),
        )
        s.add(reg)
        for mname, prio in r.get("provide", []):
            mkey = f"{r['regulation_id']}||{mname}"
            ms = MaterialStatus(mkey=mkey, regulation_id=r["regulation_id"],
                               material_name=mname, priority=prio,
                               status="Missing" if prio == "P0" else "Unconfirmed")
            s.add(ms)
    s.flush()
    # Demo data: the battery passport is ready, while the OTA update process needs revision.
    s.query(MaterialStatus).filter(MaterialStatus.material_name == "Battery Passport Data").update(
        {"status": "Ready", "owner": "Battery Team"})
    s.query(MaterialStatus).filter(MaterialStatus.material_name == "OTA Update Process Document").update(
        {"status": "Needs Update"})
    s.commit()
    # Create the demo company profile only when no profile exists.
    from models import EnterpriseProfile
    if not s.query(EnterpriseProfile).count():
        s.add(EnterpriseProfile(
            org_name="BYD Europe (Demo Company)", target_countries='["DE","FR","UK","ES","IT"]',
            target_client_types='["Government","Public Transit Operator","Logistics Fleet"]',
            acceptable_scale="€5M–€100M",
            vehicle_types='["Electric Bus","Electric Truck","Passenger Car"]',
            powertrain_types='["Battery Electric"]', charging_capability="800V fast charging, battery passport, blade battery",
            software_capability="OTA/T-Box/ADAS Level 2+",
            existing_certs='["WVTA","CSMS (R155)","Euro NCAP 5-star","IATF 16949"]',
            available_materials='["Battery Passport","Carbon Footprint Report","CSMS Certificate","TARA Report"]',
            has_eu_entity="Yes (Hungary and UK subsidiaries)", local_after_sales='["Germany","United Kingdom","France","Netherlands"]',
            local_partners="Alexander Dennis (UK)", delivery_cycle="6–12 months",
            cooperation_mode="Technology Licensing and Joint Bidding", risk_preference="Medium", completeness=75, version=1,
        ))
        s.commit()


_SEED_PROJECTS = [
    ("North Macedonia Electric Bus and Charging Infrastructure Procurement (120 buses)", "North Macedonia", "Public Transit", "Ministry of Transport", 0, "",
     "https://op.europa.eu/en/web/public-procurement/procurement-details/-/procurement/73ae5b8c",
     "Procurement for 120 electric buses and 60 charging stations. The deadline has passed; this is an example of a bundled vehicle-and-charger tender.",
     12, 4, 16, 12, 6, 16, 8, 74, "Priority Follow-up", "Under Evaluation"),
    ("North Macedonia 150 Electric Buses and 75 Charging Stations (2026)", "North Macedonia", "Public Transit",
     "Ministry of Transport of Republic of North Macedonia", 3137288000, "",
     "https://www.evergabe.com/sv/anbud/procurement-of-electrical-buses-and-charging-stations-2102236/",
     "150 electric buses and 75 charging stations; approximately €31.37 million. The scale suits an integrated solution.",
     15, 4, 16, 12, 6, 20, 6, 79, "Priority Follow-up", "Preparing Bid"),
    ("Copenhagen Airport Electric Apron Buses", "Denmark", "Airport Transport",
     "Københavns Lufthavne A/S", 30000000, "",
     "https://www.mofa.go.kr/www/brd/m_4052/view.do?seq=369409",
     "TED 322404-2026: procurement of electric apron buses, approximately €30 million.",
     12, 6, 16, 9, 6, 16, 6, 71, "Priority Follow-up", "Under Evaluation"),
    ("Croatia National Electric Bus Programme (206 buses)", "Croatia", "Public Transit",
     "Local public transit operator (NRRP)", 163000000, "",
     "https://alternative-fuels-observatory.ec.europa.eu/general-information/news/croatia-completes-funding-round-206-electric-buses",
     "NRRP support of €163 million, covering 17 cities and 206 electric buses with a charging ecosystem.",
     15, 6, 16, 12, 6, 20, 6, 81, "Priority Follow-up", "Monitoring"),
    ("UK LEVI Public Charging Infrastructure (Cumberland)", "United Kingdom", "Charging Infrastructure",
     "Cumberland Council", 3465000, "",
     "https://www.find-tender.service.gov.uk/procurement/ocds-h6vhtk-051e28",
     "LEVI public EV charging points and supporting infrastructure, approximately £3.465 million.",
     6, 4, 9, 12, 8, 12, 6, 57, "Monitoring", "Under Evaluation"),
    ("UK Strategic Road Network Ultra-Fast Charging Demonstration (Innovate UK)", "United Kingdom", "Charging Infrastructure",
     "Innovate UK / OZEV", 3000000, "",
     "https://iuk-business-connect.org.uk/opportunities/increasing-ev-charging-capacity-on-the-strategic-road-network/",
     "Awards of up to £3 million per project; requires ultra-fast charging at 150 kW or higher.",
     3, 6, 12, 9, 6, 12, 8, 56, "Monitoring", "Initial Review"),
    ("Romania 8 Electric Buses and Charging Facilities", "Romania", "Public Transit",
     "Municipal public transit operator", 2215000, "",
     "https://op.europa.eu/en/web/public-procurement/procurement-details/-/procurement/04e007bb",
     "Eight approximately 12-meter electric buses, three fast chargers, and eight standard chargers; awarded on January 9, 2026.",
     6, 4, 16, 12, 4, 9, 6, 57, "Monitoring", "Awarded"),
    ("Coventry Electric Bus Fleet", "United Kingdom", "Public Transit",
     "Coventry Transport Authority", 21650000, "2026-07-18",
     "https://www.find-tender.service.gov.uk/procurement/ocds-h6vhtk-059e54",
     "The existing subsidized contract is being retendered at expiry, with an estimated value of £21.65 million; an all-electric fleet is required.",
     12, 6, 16, 12, 8, 16, 6, 76, "Priority Follow-up", "Preparing Bid"),
]


def _seed_projects(s: OrmSession) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    for p in _SEED_PROJECTS:
        s.add(Project(
            project_name=p[0], country=p[1], project_type=p[2],
            contracting_authority=p[3], contract_value=p[4], deadline=p[5],
            source_url=p[6], description=p[7],
            scale_score=p[8], authority_score=p[9], technical_score=p[10],
            compliance_score=p[11], local_score=p[12], conversion_score=p[13],
            competition_score=p[14], total_score=p[15], project_level=p[16],
            stage=p[17], created_at=now,
            rag_status="published", version_no=1, published_at=datetime.now().astimezone(),
        ))
    s.commit()


# ═══════════════════════════════════════════════
# Regulations (legacy compatibility)
# ═══════════════════════════════════════════════

def load_regulations() -> list[dict]:
    with get_session() as s:
        return [r.to_dict() for r in s.query(Regulation).all()]


def get_regulation(rid: str) -> dict | None:
    with get_session() as s:
        r = s.get(Regulation, rid)
        return r.to_dict() if r else None


def upsert_regulation(data: dict) -> None:
    with get_session() as s:
        r = s.get(Regulation, data["regulation_id"])
        if r:
            for k, v in data.items():
                if hasattr(r, k):
                    setattr(r, k, v)
        else:
            s.add(Regulation(**data))
        s.commit()


def delete_regulation(rid: str) -> None:
    with get_session() as s:
        s.query(Regulation).filter(Regulation.regulation_id == rid).delete()
        s.query(MaterialStatus).filter(MaterialStatus.regulation_id == rid).delete()
        s.commit()


# ═══════════════════════════════════════════════
# Material status (legacy compatibility)
# ═══════════════════════════════════════════════

def load_material_status() -> dict:
    """Back {mkey: {status, owner, due_date, note, ...}}"""
    with get_session() as s:
        return {ms.mkey: ms.to_dict() for ms in s.query(MaterialStatus).all()}


def set_material_status(mkey: str, status: str, owner: str = "", due_date: str = "", note: str = "") -> None:
    with get_session() as s:
        ms = s.get(MaterialStatus, mkey)
        if ms:
            ms.status = status
            ms.owner = owner if owner is not None else ms.owner
            ms.due_date = due_date or ms.due_date or ""
            ms.note = note or ms.note or ""
            s.commit()


# ═══════════════════════════════════════════════
# Projects (legacy compatibility)
# ═══════════════════════════════════════════════

def load_projects() -> list[dict]:
    with get_session() as s:
        return [p.to_dict() for p in s.query(Project).order_by(Project.total_score.desc()).all()]
