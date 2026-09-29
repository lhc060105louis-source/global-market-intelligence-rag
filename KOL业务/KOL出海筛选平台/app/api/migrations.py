from hashlib import sha256
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_session
from app.market import normalize_market
from app.models import Kol, KolWorkflow
from app.schemas import MigrationResult
from app.services.importer import _find_existing, persist_assessment

router = APIRouter(prefix="/migrations", tags=["Migrations"])

COMMERCIAL_KEYS = {"geo", "lang", "autoInterest", "income", "age", "focus", "depth", "credibility", "err", "completion", "commentQuality", "shareSave", "vocDepth", "vocNeg", "vocHistory", "benchCpm", "cpm", "reuse", "exclusive", "brandTone", "histTone", "styleConsist", "fulfill", "briefCoop", "dataReady", "contractFlex"}
RISK_KEYS = {"incident", "falsead", "sentiment", "adlabel", "penalty", "compliance", "competitor", "compcontentpct", "complevel", "fakepct", "spikegrowth", "templatecomment", "gdpr", "datause", "minorpct", "agesuit", "exaggerate", "adas", "techaccuracy", "latedelete", "briefreject"}


def _followers(value: object) -> int | None:
    if value in (None, "", "—"):
        return None
    return int(float(str(value).replace(",", "")))


def _legacy_identity(platform: str, name: str, market: str) -> str:
    """Stable fallback identity for prototype rows that had no account identifier."""
    normalized = "\x1f".join((platform.casefold(), name.casefold(), market))
    return f"legacy:{sha256(normalized.encode()).hexdigest()[:24]}"


@router.post("/local-storage", response_model=MigrationResult)
def migrate_local_storage(payload: list[dict[str, Any]], session: Session = Depends(get_session)) -> MigrationResult:
    created = updated = failed = 0
    for item in payload:
        row_created = False
        try:
            platform = str(item["platform"]).strip()
            name = str(item.get("name") or "").strip()
            market = normalize_market(str(item["market"]))
            handle = str(item.get("handle") or "").strip() or None
            account_id = str(item.get("platform_account_id") or "").strip() or None
            if not handle and not account_id:
                if not name:
                    raise ValueError("name is required when account identity is absent")
                account_id = _legacy_identity(platform, name, market)
            stage = int(item.get("stage", 0))
            if not 0 <= stage <= 6:
                raise ValueError("stage must be between 0 and 6")
            row = {"platform": platform, "handle": handle, "platform_account_id": account_id}
            kol = _find_existing(session, row)
            if kol is None:
                kol = Kol(
                    platform=platform,
                    handle=handle,
                    platform_account_id=account_id,
                    country=market,
                )
                session.add(kol)
                session.flush()
                row_created = True
            kol.name = name or None
            kol.followers = _followers(item.get("followers"))
            data = item.get("data") or {}
            persist_assessment(session, kol, {k: data[k] for k in COMMERCIAL_KEYS if k in data}, {k: data[k] for k in RISK_KEYS if k in data}, source="legacy-local-storage")
            workflow = session.get(KolWorkflow, kol.id)
            if workflow is None:
                workflow = KolWorkflow(kol_id=kol.id)
                session.add(workflow)
            workflow.stage = stage
            session.commit()
            if row_created:
                created += 1
            else:
                updated += 1
        except (KeyError, TypeError, ValueError, SQLAlchemyError):
            session.rollback()
            failed += 1
    return MigrationResult(created=created, updated=updated, failed=failed)
