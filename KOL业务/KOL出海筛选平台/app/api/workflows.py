from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Kol, KolWorkflow, WorkflowHistory
from app.schemas import WorkflowHistoryResponse, WorkflowResponse, WorkflowUpdate

router = APIRouter(prefix="/kols", tags=["Workflows"])


@router.put("/{kol_id}/workflow", response_model=WorkflowResponse)
def update_workflow(kol_id: int, payload: WorkflowUpdate, session: Session = Depends(get_session)) -> KolWorkflow:
    if session.get(Kol, kol_id) is None:
        raise HTTPException(status_code=404, detail="KOL not found")
    workflow = session.get(KolWorkflow, kol_id)
    if workflow is None:
        workflow = KolWorkflow(kol_id=kol_id)
        session.add(workflow)
        session.add(WorkflowHistory(kol_id=kol_id, stage=0))
    workflow.stage = payload.stage
    session.add(WorkflowHistory(kol_id=kol_id, stage=payload.stage))
    session.commit()
    session.refresh(workflow)
    return workflow


@router.get(
    "/{kol_id}/workflow/history",
    response_model=list[WorkflowHistoryResponse],
)
def get_workflow_history(
    kol_id: int,
    session: Session = Depends(get_session),
) -> list[WorkflowHistory]:
    if session.get(Kol, kol_id) is None:
        raise HTTPException(status_code=404, detail="KOL not found")
    return list(
        session.scalars(
            select(WorkflowHistory)
            .where(WorkflowHistory.kol_id == kol_id)
            .order_by(WorkflowHistory.id)
        )
    )
