# -*- coding: utf-8 -*-
"""Report API for compliance risk and material-gap exports."""
from fastapi import APIRouter, Query, Depends
from fastapi.responses import PlainTextResponse, Response

import report_service as rpt
from db import load_projects, load_regulations
from auth_service import require_permission

router = APIRouter(prefix="/api/reports", tags=["Report"])


@router.get("/risk")
def risk_report(
    scope: str = Query("All Regulations"),
    impact: str = Query("All"),
    prio_only: str = Query("All"),
):
    """Generate a compliance risk assessment report in Markdown format."""
    md, _ = rpt.risk_report_markdown(scope, impact, prio_only)
    return PlainTextResponse(md, media_type="text/markdown")


@router.get("/gaps/excel")
def download_gap_excel(_=Depends(require_permission("material.export"))):
    """Export the material gap list as an Excel workbook."""
    data = rpt.gap_list_excel()
    from urllib.parse import quote
    fname = quote("Material Gaps.xlsx")
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fname}"})


@router.get("/dashboard")
def dashboard_summary():
    """Return summary data for the home dashboard, including regulations, projects, and gaps."""
    from regulations_service import gap_stats
    p0_t, p0_g, _ = gap_stats()
    regs = load_regulations()
    projs = load_projects()
    return {
        "regulations": {"total": len(regs), "p0_materials": p0_t, "p0_gaps": p0_g, "high_impact": sum(1 for r in regs if r["impact_level"] == "High")},
        "projects": {"total": len(projs), "priority": sum(1 for p in projs if p["project_level"] == "Priority Follow-up"), "avg_score": round(sum(p["total_score"] for p in projs) / max(len(projs), 1), 1) if projs else 0},
        "updated_at": max((r.get("last_verified_at", "") for r in regs), default=""),
    }
