# -*- coding: utf-8 -*-
"""报告生成服务 —— 合规风险报告 + 材料缺口清单。纯 Python,不依赖 UI。"""
import io
import pandas as pd
from regulations_service import list_regulations, gap_stats, p0_gap_list

IMPACT_ORDER = {"高": 3, "中": 2, "低": 1}


def risk_report_markdown(scope: str = "全部法规", impact: str = "全部", prio_only: str = "全部") -> tuple[str, list[dict]]:
    """生成合规风险评估报告,返回 (markdown_text, 报告数据列表)。"""
    regs = list_regulations() if scope == "全部法规" else list_regulations(scope=scope)
    if impact != "全部":
        regs = [r for r in regs if r["impact_level"] == impact]
    regs.sort(key=lambda r: -IMPACT_ORDER.get(r["impact_level"], 0))

    lines = [f"# 欧洲市场合规风险评估报告", f"范围:{scope} · 影响:{impact} · 生成于规则引擎", ""]
    data = []
    for r in regs:
        risk_map = {"高": "极高/高", "中": "中等", "低": "关注"}
        materials = [f"{m}({p})" for m, p in r["provide"]]
        if prio_only == "仅 P0":
            materials = [f"{m}(P0)" for m, p in r["provide"] if p == "P0"]
        lines += [
            f"## {r['name']}（{r.get('official_number','')}）",
            f"- 影响程度:{r['impact_level']} | 风险等级:{risk_map.get(r['impact_level'],'关注')}",
            f"- 核心要求:{r['core_requirement']}",
            f"- 所需材料:{'、'.join(materials)}",
            f"- 本地方职责:{r.get('local_duty','')}",
            f"- 合规缺口:{r.get('gap','')}" if r.get("gap") else "",
            f"- 官方来源:{r['official_source']}", "",
        ]
        data.append(r)
    return "\n".join(lines), data


def gap_list_excel() -> bytes:
    """导出材料缺口清单为 Excel 字节流。"""
    rows = p0_gap_list() or [{"提示": "当前无缺口"}]
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame(rows).to_excel(w, index=False, sheet_name="材料缺口清单")
    return buf.getvalue()
