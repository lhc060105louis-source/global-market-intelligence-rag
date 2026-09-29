from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import ImportJob
from app.schemas import ImportJobResponse, ImportResult
from app.services.importer import import_file

router = APIRouter(prefix="/imports", tags=["Imports"])


@router.post("", response_model=ImportResult, status_code=201)
async def upload_import(
    file: UploadFile,
    session: Session = Depends(get_session),
) -> ImportResult:
    filename = file.filename or ""
    if Path(filename).suffix.lower() not in {".csv", ".xlsx"}:
        raise HTTPException(status_code=415, detail="Only CSV and XLSX are supported")
    try:
        job = import_file(session, filename, await file.read())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ImportResult(
        job_id=job.id,
        total_rows=job.total_rows,
        created=job.created_count,
        updated=job.updated_count,
        failed=job.failed_count,
    )


@router.get("/{job_id}", response_model=ImportJobResponse)
def get_import_job(
    job_id: int,
    session: Session = Depends(get_session),
) -> ImportJob:
    job = session.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")
    return job
