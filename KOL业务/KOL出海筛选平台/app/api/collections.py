from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import CollectionJob
from app.schemas import (
    CollectionCreateResponse,
    CollectionJobResponse,
    CollectionRequest,
)
from app.services.collection import (
    normalize_collection_request,
    run_collection_job,
    validate_collection_options,
)

router = APIRouter(prefix="/collections", tags=["Collections"])


@router.post("", response_model=CollectionCreateResponse, status_code=201)
def create_collection_job(
    payload: CollectionRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    session: Session = Depends(get_session),
) -> CollectionCreateResponse:
    try:
        keywords, platforms, languages, markets = normalize_collection_request(payload)
        validate_collection_options(platforms, languages, markets)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job = CollectionJob(
        status="queued",
        keywords=keywords,
        platforms=platforms,
        languages=languages,
        markets=markets,
        limit_per_platform=payload.limit_per_platform,
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    collectors = getattr(request.app.state, "collection_collectors", None)
    credential_store = getattr(request.app.state, "credential_store", None)
    background_tasks.add_task(
        run_collection_job,
        request.app.state.session_factory,
        job.id,
        collectors,
        credential_store,
    )
    return CollectionCreateResponse(job_id=job.id, status=job.status)


@router.get("/{job_id}", response_model=CollectionJobResponse)
def get_collection_job(
    job_id: int,
    session: Session = Depends(get_session),
) -> CollectionJob:
    job = session.get(CollectionJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Collection job not found")
    return job
