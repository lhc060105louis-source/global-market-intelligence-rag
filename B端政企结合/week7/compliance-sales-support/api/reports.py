# -*- coding: utf-8 -*-
"""报告 API —— 合规风险报告 / 缺口清单导出"""
from fastapi import APIRouter, Query, Depends
from fastapi.responses import PlainTextResponse, Response

import report_service as rpt
from db import load_projects, load_regulations
from auth_service import require_permission

router = APIRouter(prefix="/api/reports", tags=["报告"])


@router.get("/risk")
def risk_report(
    scope: str = Query("全部法规"),
    impact: str = Query("全部"),
    prio_only: str = Query("全部"),
):
    """合规风险评估报告(Markdown)。"""
    md, _ = rpt.risk_report_markdown(scope, impact, prio_only)
    return PlainTextResponse(md, media_type="text/markdown")


@router.get("/gaps/excel")
def download_gap_excel(_=Depends(require_permission("material.export"))):
    """材料缺口清单(Excel 下载)。"""
    data = rpt.gap_list_excel()
    from urllib.parse import quote
    fname = quote("材料缺口清单.xlsx")
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fname}"})


@router.get("/dashboard")
def dashboard_summary():
    """首页 Dashboard 数据(法规/项目/缺口汇总)。"""
    from regulations_service import gap_stats
    p0_t, p0_g, _ = gap_stats()
    regs = load_regulations()
    projs = load_projects()
    return {
        "regulations": {"total": len(regs), "p0_materials": p0_t, "p0_gaps": p0_g, "high_impact": sum(1 for r in regs if r["impact_level"] == "高")},
        "projects": {"total": len(projs), "priority": sum(1 for p in projs if p["project_level"] == "优先跟进"), "avg_score": round(sum(p["total_score"] for p in projs) / max(len(projs), 1), 1) if projs else 0},
        "updated_at": max((r.get("last_verified_at", "") for r in regs), default=""),
    }
