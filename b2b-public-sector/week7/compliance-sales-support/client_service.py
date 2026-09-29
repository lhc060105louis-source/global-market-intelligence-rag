# -*- coding: utf-8 -*-
"""Customer support services for regulation matching and client-specific sales packs."""
import data_clients as C
from db import load_regulations, load_material_status

PRIO_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def get_client(key_or_type: str) -> dict | None:
    for c in C.CLIENTS:
        if c.get("client_key") == key_or_type or c["client_type"] == key_or_type:
            return c
    return None


def match_compliance_gaps(client: dict) -> list[dict]:
    """Return applicable regulation materials and their current gap status for a client profile."""
    regs = {r["regulation_id"]: r for r in load_regulations()}
    ms_all = load_material_status()
    linked_ids = client.get("link_regulations", [])
    rows = []
    for rid in linked_ids:
        r = regs.get(rid)
        if not r:
            continue
        for mname, prio in r["provide"]:
            mkey = f"{rid}||{mname}"
            ms = ms_all.get(mkey, {})
            status = ms.get("status", "Unconfirmed")
            is_gap = prio == "P0" and status not in {"Ready", "Not Applicable"}
            rows.append({
                "priority": prio, "material": mname, "regulation": r["name"],
                "status": status, "is_gap": is_gap,
            })
    rows.sort(key=lambda x: (PRIO_ORDER.get(x["priority"], 9), not x["is_gap"]))
    return rows


def count_client_p0_gaps(client: dict) -> int:
    return sum(1 for r in match_compliance_gaps(client) if r["is_gap"])


def build_sales_pack(client: dict) -> str:
    """Build a client-specific sales support pack in Markdown."""
    lines = [
        f"# Sales Support Pack · {client['client_type']}", "",
        f"**Client:** {client.get('sample_name','')} | **Region:** {client.get('region','')} | **Scenario:** {client.get('scenario','')}", "",
        f"> {client['portrait']}", "",
        "## 1. Client Needs Analysis",
        "**Pain Points:** " + "; ".join(client.get("painpoints", [])),
        "**Procurement Priorities:** " + "; ".join(client.get("focus", [])), "",
        "## 2. Product and Service Proposal",
        "- **Product:** " + "; ".join(client.get("product", [])),
        "- **Technology:** " + "; ".join(client.get("tech", [])),
        "- **Services:** " + "; ".join(client.get("service", [])), "",
        "## 3. Case Studies and Evidence",
    ]
    for case in client.get("cases", []):
        flag = "✅ Verified source" if case.get("verified") else "◻ Conceptual example; source needed"
        lines.append(f"- **{case['title']}** [{flag}]: {case.get('detail','')} (Source: {case.get('source','')})")
    lines += [
        "**Supporting Evidence:** " + "; ".join(client.get("evidence", [])), "",
        f"**Key Talking Points:** {client.get('talking_points','')}", "",
        "## 4. Compliance Materials (P0–P3, Current Status)",
    ]
    gaps = match_compliance_gaps(client)
    for g in gaps:
        mark = "🔴" if g["is_gap"] else ""
        lines.append(f"- {mark} [{g['priority']}] {g['material']} ({g['regulation']}) — Status: {g['status']}")
    lines += ["", "---", "*This support pack is generated with rule-based assistance. Compliance conclusions must be confirmed by an authorized reviewer.*"]
    return "\n".join(lines)
