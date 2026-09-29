# -*- coding: utf-8 -*-
"""Expose formally published B2B entries to the global RAG service (Week 6 RAG requirement §1.3)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Query, Depends

import data_clients as C
from db import load_projects, load_regulations
from models import IntelligenceItem, Project, Regulation, RagEventOutbox
from db import get_session
from rag_event_service import deliver_pending, make_payload
from rag_event_service import iso
from auth_service import require_permission

router = APIRouter(prefix="/api/rag", tags=["RAG Knowledge Hub"])

SCHEMA_VERSION = "b-end-rag-entry/1.0"
ENTRY_TYPES = ("Policy", "Procurement", "Market", "Customer/partnershipPartner")
REQUIRED_FIELDS = (
    "entry_id", "entry_type", "title", "summary", "countries", "tags",
    "related_objects", "impact_conclusion", "action_suggestions",
    "external_sources", "status", "published_at",
)


def _list(value) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def _action_from_gap(gap: str) -> str:
    if not gap:
        return ""
    hints = []
    normalized_gap = gap.casefold()
    if "battery passport" in normalized_gap or "carbon footprint" in normalized_gap:
        hints.append("Prepare a battery passport and carbon footprint report")
    if "csms" in normalized_gap or "tara" in normalized_gap:
        hints.append("Complete CSMS/TARA cybersecurity certification")
    if "data residency" in normalized_gap or "gdpr" in normalized_gap:
        hints.append("Confirm the EU data residency plan and prepare a DPIA")
    if "local" in normalized_gap:
        hints.append("Establish local partnerships or a maintenance network")
    if "certification" in normalized_gap or "wvta" in normalized_gap:
        hints.append("Complete EU WVTA certification materials for the full vehicle model")
    return "; ".join(hints) if hints else gap[:120]


def _base_entry(**values) -> dict:
    entry = {field: values.get(field) for field in REQUIRED_FIELDS}
    entry.update({
        "version_no": str(values.get("version_no") or "1"),
        "detail_url": values.get("detail_url") or "/",
        "data_label": values.get("data_label") or "Demo Data",
    })
    entry["countries"] = _list(entry["countries"])
    entry["tags"] = _list(entry["tags"])
    entry["related_objects"] = entry["related_objects"] or []
    entry["external_sources"] = entry["external_sources"] or []
    entry["impact_conclusion"] = entry["impact_conclusion"] or ""
    entry["action_suggestions"] = entry["action_suggestions"] or ""
    entry["published_at"] = iso(entry["published_at"])
    return entry


def published_entries(entry_type: str = "") -> list[dict]:
    entries: list[dict] = []

    if not entry_type or entry_type == "Policy":
        for regulation in load_regulations():
            if regulation.get("rag_status") != "published":
                continue
            entries.append(_base_entry(
                entry_id=f"B-REG-{regulation['regulation_id']}", entry_type="Policy",
                title=regulation["name"], summary=regulation.get("core_requirement", ""),
                countries=regulation.get("scope", ""),
                tags=[regulation.get("type", ""), f"Impact:{regulation.get('impact_level', '')}"],
                related_objects=[
                    {"object_type": "product", "object_id": "", "name": product}
                    for product in regulation.get("applicable_product", [])
                ],
                impact_conclusion=regulation.get("gap", ""),
                action_suggestions=_action_from_gap(regulation.get("gap", "")),
                external_sources=[{
                    "name": regulation.get("issuer", ""),
                    "url": regulation.get("official_source", ""),
                }],
                status="published", published_at=regulation.get("published_at") or regulation.get("last_verified_at", ""),
                version_no=regulation.get("version", "1"),
                detail_url=f"/?page=regulations&record_id={quote(str(regulation['regulation_id']))}",
            ))

    if not entry_type or entry_type == "Procurement":
        for project in load_projects():
            if project.get("rag_status") != "published":
                continue
            entries.append(_base_entry(
                entry_id=f"B-PRJ-{project['id']}", entry_type="Procurement",
                title=project["project_name"], summary=project.get("description", ""),
                countries=project.get("country", ""),
                tags=[project.get("project_type", ""), project.get("project_level", "")],
                related_objects=[{
                    "object_type": "buyer", "object_id": "",
                    "name": project.get("contracting_authority", ""),
                }],
                impact_conclusion=f"Overall score: {project['total_score']}/100; priority: {project['project_level']}",
                action_suggestions="Priority Follow-up" if project["project_level"] == "Priority Follow-up" else "Monitoring",
                external_sources=[{"name": "Original Project Source", "url": project.get("source_url", "")}],
                status="published", published_at=project.get("published_at") or project.get("created_at", ""),
                version_no=f"v{project.get('version_no', 1)}",
                detail_url=f"/?page=projects&record_id={project['id']}",
            ))

    if not entry_type or entry_type == "Customer/partnershipPartner":
        for client in C.CLIENTS:
            client_id = str(client.get("client_id", ""))
            entries.append(_base_entry(
                entry_id=f"B-CLI-{client_id}", entry_type="Customer/partnershipPartner",
                title=f"{client['client_type']} ({client.get('scenario', '')})",
                summary=client.get("portrait", ""), countries=client.get("region", ""),
                tags=[client.get("scenario", ""), client.get("client_type", "")],
                related_objects=[
                    {"object_type": "regulation", "object_id": rid, "name": rid}
                    for rid in client.get("link_regulations", [])
                ],
                impact_conclusion=client.get("talking_points", ""),
                action_suggestions="; ".join(client.get("painpoints", [])[:3]),
                external_sources=[
                    {"name": case.get("source", ""), "url": ""}
                    for case in client.get("cases", []) if case.get("source")
                ],
                status="published", published_at="2026-08-04T00:00:00Z", version_no="1",
                detail_url=f"/?page=clients&record_id={quote(client_id)}",
            ))

    if not entry_type or entry_type == "Market":
        with get_session() as session:
            rows = session.query(IntelligenceItem).filter(
                IntelligenceItem.review_status == "published"
            ).order_by(IntelligenceItem.published_at_rag.desc()).all()
            for item in rows:
                entries.append(_base_entry(
                    entry_id=f"B-INT-{item.id}", entry_type="Market", title=item.title,
                    summary=item.summary or "", countries=[], tags=[item.source],
                    related_objects=[], impact_conclusion="", action_suggestions="",
                    external_sources=[{"name": item.source, "url": item.link}],
                    status="published", published_at=item.published_at_rag,
                    version_no=f"v{item.version_no}",
                    detail_url=f"/?page=intelligence&record_id={item.id}",
                ))

    # RSS items remain drafts until a human reviews and publishes them.
    return entries


@router.get("/entries")
def list_entries(
    entry_type: str = Query("", description="Policy/Procurement/Market/Customer/partnershipPartner"),
    limit: int = Query(500, ge=1, le=1000),
):
    entries = published_entries(entry_type)[:limit]
    canonical = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    snapshot_id = "B-SNAPSHOT-" + hashlib.sha256(canonical.encode()).hexdigest()[:16]
    return {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_system": "B2B Public Sector Project Platform",
        "entries": entries,
        "total": len(entries),
        "types": list(ENTRY_TYPES),
    }


@router.get("/health")
def rag_health():
    entries = published_entries()
    counts = {entry_type: 0 for entry_type in ENTRY_TYPES}
    for entry in entries:
        counts[entry["entry_type"]] += 1
    return {
        "status": "ok", "schema_version": SCHEMA_VERSION,
        "published_entries": len(entries), "by_type": counts,
        "unreviewed_rss_excluded": True,
    }


def project_event_payload(project: Project, event_type: str = "upsert") -> dict:
    status = "archived" if event_type == "archive" else "published"
    return make_payload(
        event_type=event_type, upstream_id=f"B-PRJ-{project.id}",
        upstream_version=project.version_no, status=status,
        title=project.project_name, summary=project.description or "",
        content=(f"Contracting Authority: {project.contracting_authority}\nProject type: {project.project_type or ''}\n"
                 f"Project description: {project.description or ''}\nOverall score: {project.total_score}/100, {project.project_level}"),
        entry_type="procurement", countries=[project.country] if project.country else [],
        tags=[value for value in [project.project_type, project.project_level] if value],
        evidence=[{"name": "Original Project Source", "url": project.source_url}] if project.source_url else [],
        detail_url=f"/?page=projects&record_id={project.id}", published_at=project.published_at,
        related_entities=[{"type": "buyer", "standard_name": project.contracting_authority,
                           "stable_id": None}],
        business_impact=f"Overall score: {project.total_score}/100; priority: {project.project_level}",
        recommended_action="Priority Follow-up" if project.project_level == "Priority Follow-up" else "Monitoring",
    )


def regulation_event_payload(regulation: Regulation, event_type: str = "upsert") -> dict:
    status = "archived" if event_type == "archive" else "published"
    return make_payload(
        event_type=event_type, upstream_id=f"B-REG-{regulation.regulation_id}",
        upstream_version=regulation.rag_version or 1, status=status,
        title=regulation.name, summary=regulation.core_requirement or "",
        content=(f"Issuing organization: {regulation.issuer or ''}\nApplicable scope: {regulation.scope or ''}\n"
                 f"Core requirements: {regulation.core_requirement or ''}\nBusiness impact: {regulation.gap or ''}"),
        entry_type="policy", countries=[regulation.scope] if regulation.scope else [],
        tags=[value for value in [regulation.type, regulation.impact_level] if value],
        evidence=[{"name": regulation.issuer or "Original Regulation Source", "url": regulation.official_source}] if regulation.official_source else [],
        detail_url=f"/?page=regulations&record_id={quote(str(regulation.regulation_id))}",
        published_at=regulation.published_at or regulation.last_verified_at,
        related_entities=[{"type": "regulator", "standard_name": regulation.issuer,
                           "stable_id": None}] if regulation.issuer else [],
        business_impact=regulation.gap or "", recommended_action=_action_from_gap(regulation.gap or ""),
    )


def intelligence_event_payload(item: IntelligenceItem, event_type: str = "upsert") -> dict:
    status = "archived" if event_type == "archive" else "published"
    return make_payload(
        event_type=event_type, upstream_id=f"B-INT-{item.id}", upstream_version=item.version_no,
        status=status, title=item.title, summary=item.summary or "", content=item.summary or item.title,
        entry_type="market", countries=[item.review_region] if item.review_region else [], tags=[item.source],
        evidence=[{"name": item.source, "url": item.link}],
        detail_url=f"/?page=intelligence&record_id={item.id}", published_at=item.published_at_rag,
    )


@router.get("/outbox")
def outbox_status(limit: int = Query(100, ge=1, le=500), _=Depends(require_permission("regulation.manage"))):
    with get_session() as session:
        rows = session.query(RagEventOutbox).order_by(RagEventOutbox.created_at.desc()).limit(limit).all()
        return [{"event_id": row.event_id, "upstream_id": row.upstream_id,
                 "upstream_version": row.upstream_version, "event_type": row.event_type,
                 "delivery_status": row.delivery_status, "attempt_count": row.attempt_count,
                 "last_error": row.last_error, "created_at": row.created_at} for row in rows]


@router.post("/outbox/retry")
def retry_outbox(limit: int = Query(50, ge=1, le=500), _=Depends(require_permission("regulation.manage"))):
    return deliver_pending(limit)
