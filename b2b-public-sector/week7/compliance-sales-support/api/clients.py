# -*- coding: utf-8 -*-
"""Customer support API for client profiles, compliance matching, and sales packs."""
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import PlainTextResponse

import client_service as cs
import data_clients as C
from auth_service import require_permission

router = APIRouter(prefix="/api/clients", tags=["Customer Support"])


@router.get("")
def list_clients():
    return [{"key": c.get("client_key",""), "type": c["client_type"], "region": c["region"], "scenario": c["scenario"]} for c in C.CLIENTS]


@router.get("/{client_key}")
def client_detail(client_key: str):
    c = cs.get_client(client_key)
    if not c: raise HTTPException(404, f"Customer {client_key} was not found. Available keys: gov, bus, log, ent, mob")
    gaps = cs.match_compliance_gaps(c)
    p0_gap = cs.count_client_p0_gaps(c)
    return {"client": c, "compliance_materials": gaps, "p0_gap_count": p0_gap}


@router.get("/{client_key}/compliance")
def client_compliance(client_key: str):
    c = cs.get_client(client_key)
    if not c: raise HTTPException(404)
    return {"client_key": client_key, "materials": cs.match_compliance_gaps(c)}


@router.get("/{client_key}/sales-pack")
def generate_sales_pack(client_key: str, fmt: str = Query("md"), _=Depends(require_permission("sales_pack.download"))):
    c = cs.get_client(client_key)
    if not c: raise HTTPException(404)
    md = cs.build_sales_pack(c)
    if fmt == "json": return {"client_key": client_key, "sales_pack_md": md}
    return PlainTextResponse(md, media_type="text/markdown")
