from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Contract, Kol
from app.schemas import ContractResponse, ContractWrite
from app.sync.outbox import record_mutation

router = APIRouter(prefix="/kols", tags=["Contracts"])


def _require_kol(session: Session, kol_id: int) -> None:
    if session.get(Kol, kol_id) is None:
        raise HTTPException(status_code=404, detail="KOL not found")


@router.post(
    "/{kol_id}/contracts",
    response_model=ContractResponse,
    status_code=201,
)
def create_contract(
    kol_id: int,
    payload: ContractWrite,
    session: Session = Depends(get_session),
) -> Contract:
    _require_kol(session, kol_id)
    contract = Contract(kol_id=kol_id, **payload.model_dump())
    session.add(contract)
    session.flush()
    record_mutation(session, contract, "upsert")
    session.commit()
    session.refresh(contract)
    return contract


@router.get(
    "/{kol_id}/contracts",
    response_model=list[ContractResponse],
)
def list_contracts(
    kol_id: int,
    session: Session = Depends(get_session),
) -> list[Contract]:
    _require_kol(session, kol_id)
    return list(
        session.scalars(
            select(Contract)
            .where(Contract.kol_id == kol_id, Contract.deleted_at.is_(None))
            .order_by(Contract.created_at.desc())
        )
    )
