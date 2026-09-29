# -*- coding: utf-8 -*-
"""数据层(SQLAlchemy)。替换 raw sqlite3,与 KOL 端统一 ORM。
首次运行自动建表并 seed 种子数据。函数签名与旧版兼容,app.py 改动最小。"""
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
    """只创建缺失表，不载入种子；供独立任务安全复用。"""
    Base.metadata.create_all(_engine, checkfirst=True)
    _ensure_rag_columns()


def _ensure_rag_columns() -> None:
    """轻量演示迁移：为已有 SQLite 数据库补充主动推送所需字段。"""
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
                connection.execute(text("UPDATE regulations SET rag_status='published' WHERE status='已审核'"))
            if table == "projects" and "rag_status" not in existing:
                connection.execute(text("UPDATE projects SET rag_status='published'"))


# ═══════════════════════════════════════════════
# 初始化
# ═══════════════════════════════════════════════

def bootstrap() -> None:
    create_tables()
    seed_if_empty()
    ensure_demo_enterprise_profiles()


def ensure_demo_enterprise_profiles() -> None:
    """保证 P1 演示有两份差异化档案，可验证个性化匹配而非固定答案。"""
    from models import EnterpriseProfile
    profiles = [
        dict(
            org_name="BYD Europe（演示档案A）", target_countries='["DE","FR","UK","ES","IT"]',
            target_client_types='["政府 / 市政","公交运营商","物流车队"]', acceptable_scale="500万-1亿€",
            vehicle_types='["电动客车","电动货车","乘用车"]', powertrain_types='["纯电"]',
            charging_capability="800V快充+电池护照+刀片电池", software_capability="OTA/T-Box/ADAS L2+",
            existing_certs='["WVTA","CSMS(R155)","Euro NCAP五星"]',
            available_materials='["电池护照","碳足迹报告","CSMS证书","TARA报告"]',
            has_eu_entity="是", local_after_sales='["德国","英国","法国","荷兰"]',
            local_partners="Alexander Dennis (UK)", delivery_cycle="6-12个月",
            cooperation_mode="技术授权+联合投标", risk_preference="中性", completeness=100,
        ),
        dict(
            org_name="中国客车企业（演示档案B）", target_countries='["IT","ES"]',
            target_client_types='["公交运营商"]', acceptable_scale="100万-2000万€",
            vehicle_types='["电动客车"]', powertrain_types='["纯电"]',
            charging_capability="400V常规充电", software_capability="基础车队管理",
            existing_certs='["IATF 16949"]', available_materials='["产品测试报告"]',
            has_eu_entity="否", local_after_sales='[]', local_partners="",
            delivery_cycle="12-18个月", cooperation_mode="整车出口", risk_preference="保守", completeness=100,
        ),
    ]
    with get_session() as session:
        existing = {p.org_name for p in session.query(EnterpriseProfile).all()}
        # 兼容早期数据库中的旧名称，避免重复创建 A 档案。
        if "BYD Europe (演示企业)" in existing:
            existing.add("BYD Europe（演示档案A）")
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
            rag_status="published" if r["status"] == "已审核" else "draft",
            provide=json.dumps(r.get("provide", []), ensure_ascii=False),
            local_duty=r.get("local_duty", ""), gap=r.get("gap", ""),
            scenarios=json.dumps(r.get("scenarios", []), ensure_ascii=False),
        )
        s.add(reg)
        for mname, prio in r.get("provide", []):
            mkey = f"{r['regulation_id']}||{mname}"
            ms = MaterialStatus(mkey=mkey, regulation_id=r["regulation_id"],
                               material_name=mname, priority=prio,
                               status="缺失" if prio == "P0" else "待确认")
            s.add(ms)
    s.flush()
    # 演示数据:电池护照已准备,OTA 待更新
    s.query(MaterialStatus).filter(MaterialStatus.material_name == "数字电池护照数据").update(
        {"status": "已准备", "owner": "电池团队"})
    s.query(MaterialStatus).filter(MaterialStatus.material_name == "OTA 更新流程文件").update(
        {"status": "待更新"})
    s.commit()
    # 演示企业档案(仅首次)
    from models import EnterpriseProfile
    if not s.query(EnterpriseProfile).count():
        s.add(EnterpriseProfile(
            org_name="BYD Europe (演示企业)", target_countries='["DE","FR","UK","ES","IT"]',
            target_client_types='["政府 / 市政","公交运营商","物流车队"]',
            acceptable_scale="500万-1亿€",
            vehicle_types='["电动客车","电动货车","乘用车"]',
            powertrain_types='["纯电"]', charging_capability="800V快充+电池护照+刀片电池",
            software_capability="OTA/T-Box/ADAS L2+",
            existing_certs='["WVTA","CSMS(R155)","Euro NCAP五星","IATF 16949"]',
            available_materials='["电池护照","碳足迹报告","CSMS证书","TARA报告"]',
            has_eu_entity="是(匈牙利+英国子公司)", local_after_sales='["德国","英国","法国","荷兰"]',
            local_partners="Alexander Dennis(UK)", delivery_cycle="6-12个月",
            cooperation_mode="技术授权+联合投标", risk_preference="中性", completeness=75, version=1,
        ))
        s.commit()


_SEED_PROJECTS = [
    ("北马其顿 电动公交+充电基础设施采购(120辆)", "北马其顿", "公共交通", "Ministry of Transport", 0, "",
     "https://op.europa.eu/en/web/public-procurement/procurement-details/-/procurement/73ae5b8c",
     "120 辆电动公交+60 个充电站。已截止,为车+桩捆绑采购样例。",
     12, 4, 16, 12, 6, 16, 8, 74, "优先跟进", "评估中"),
    ("北马其顿 150辆电动公交+75充电站(2026)", "北马其顿", "公共交通",
     "Ministry of Transport of Republic of North Macedonia", 3137288000, "",
     "https://www.evergabe.com/sv/anbud/procurement-of-electrical-buses-and-charging-stations-2102236/",
     "150 辆电动公交+75 充电站;约 3137 万欧元。规模大,适合整套方案。",
     15, 4, 16, 12, 6, 20, 6, 79, "优先跟进", "准备投标"),
    ("丹麦 哥本哈根机场电动摆渡车", "丹麦", "机场交通",
     "Københavns Lufthavne A/S", 30000000, "",
     "https://www.mofa.go.kr/www/brd/m_4052/view.do?seq=369409",
     "TED 322404-2026:采购电动 apron buses,约 3000 万欧元。",
     12, 6, 16, 9, 6, 16, 6, 71, "优先跟进", "评估中"),
    ("克罗地亚 国家电动公交计划(206辆)", "克罗地亚", "公共交通",
     "地方公共交通运营商(NRRP)", 163000000, "",
     "https://alternative-fuels-observatory.ec.europa.eu/general-information/news/croatia-completes-funding-round-206-electric-buses",
     "NRRP 支持 1.63 亿欧元,覆盖 17 个城市,206 辆电动公交+充电生态。",
     15, 6, 16, 12, 6, 20, 6, 81, "优先跟进", "持续观察"),
    ("英国 LEVI 公共充电基础设施(Cumberland)", "英国", "充电基础设施",
     "Cumberland Council", 3465000, "",
     "https://www.find-tender.service.gov.uk/procurement/ocds-h6vhtk-051e28",
     "LEVI 公共 EV 充电点+配套基础设施,约 346.5 万英镑。",
     6, 4, 9, 12, 8, 12, 6, 57, "持续观察", "评估中"),
    ("英国 战略道路超快充示范(Innovate UK)", "英国", "充电基础设施",
     "Innovate UK / OZEV", 3000000, "",
     "https://iuk-business-connect.org.uk/opportunities/increasing-ev-charging-capacity-on-the-strategic-road-network/",
     "最高每项目 300 万英镑,要求 150kW+ 超快充。",
     3, 6, 12, 9, 6, 12, 8, 56, "持续观察", "初步关注"),
    ("罗马尼亚 8辆电动公交+充电设施", "罗马尼亚", "公共交通",
     "市级公共交通运营方", 2215000, "",
     "https://op.europa.eu/en/web/public-procurement/procurement-details/-/procurement/04e007bb",
     "8 辆约 12m 电动公交+3 快充+8 慢充;2026/1/9 授标。",
     6, 4, 16, 12, 4, 9, 6, 57, "持续观察", "已授标"),
    ("英国 Coventry 电动公交城", "英国", "公共交通",
     "Coventry Transport Authority", 21650000, "2026-07-18",
     "https://www.find-tender.service.gov.uk/procurement/ocds-h6vhtk-059e54",
     "现有补贴合约到期重招,约 2165 万英镑;要求全电动车队。",
     12, 6, 16, 12, 8, 16, 6, 76, "优先跟进", "准备投标"),
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
# 法规(兼容旧接口)
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
# 材料状态(兼容旧接口)
# ═══════════════════════════════════════════════

def load_material_status() -> dict:
    """返回 {mkey: {status, owner, due_date, note, ...}}"""
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
# 项目(兼容旧接口)
# ═══════════════════════════════════════════════

def load_projects() -> list[dict]:
    with get_session() as s:
        return [p.to_dict() for p in s.query(Project).order_by(Project.total_score.desc()).all()]
