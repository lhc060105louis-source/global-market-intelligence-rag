from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Kol, Shortlist, ShortlistItem
from app.schemas import (
    ShortlistCreate,
    ShortlistItemCreate,
    ShortlistItemResponse,
    ShortlistResponse,
)
from app.services.exporter import export_shortlist

router = APIRouter(prefix="/shortlists", tags=["Shortlists"])


def _get_shortlist(session: Session, shortlist_id: int) -> Shortlist:
    shortlist = session.get(Shortlist, shortlist_id)
    if shortlist is None:
        raise HTTPException(status_code=404, detail="Shortlist not found")
    return shortlist


@router.post("", response_model=ShortlistResponse, status_code=201)
def create_shortlist(
    payload: ShortlistCreate,
    session: Session = Depends(get_session),
) -> Shortlist:
    target_country = payload.target_country.upper() if payload.target_country else None
    if target_country not in {None, "UK", "DE"}:
        raise HTTPException(status_code=422, detail="target_country must be UK or DE")
    shortlist = Shortlist(
        name=payload.name,
        target_country=target_country,
        notes=payload.notes,
    )
    session.add(shortlist)
    session.commit()
    session.refresh(shortlist)
    return shortlist


@router.get("", response_model=list[ShortlistResponse])
def list_shortlists(
    session: Session = Depends(get_session),
) -> list[Shortlist]:
    return list(
        session.scalars(select(Shortlist).order_by(Shortlist.created_at.desc()))
    )


@router.get("/{shortlist_id}", response_model=ShortlistResponse)
def get_shortlist(
    shortlist_id: int,
    session: Session = Depends(get_session),
) -> Shortlist:
    return _get_shortlist(session, shortlist_id)


@router.post(
    "/{shortlist_id}/items",
    response_model=ShortlistItemResponse,
    status_code=201,
)
def add_shortlist_item(
    shortlist_id: int,
    payload: ShortlistItemCreate,
    session: Session = Depends(get_session),
) -> ShortlistItem:
    _get_shortlist(session, shortlist_id)
    if session.get(Kol, payload.kol_id) is None:
        raise HTTPException(status_code=404, detail="KOL not found")
    existing = session.scalar(
        select(ShortlistItem).where(
            ShortlistItem.shortlist_id == shortlist_id,
            ShortlistItem.kol_id == payload.kol_id,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="KOL is already shortlisted")
    item = ShortlistItem(
        shortlist_id=shortlist_id,
        kol_id=payload.kol_id,
        priority=payload.priority,
        recommendation=payload.recommendation,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.delete("/{shortlist_id}/items/{kol_id}", status_code=204)
def remove_shortlist_item(
    shortlist_id: int,
    kol_id: int,
    session: Session = Depends(get_session),
) -> Response:
    item = session.scalar(
        select(ShortlistItem).where(
            ShortlistItem.shortlist_id == shortlist_id,
            ShortlistItem.kol_id == kol_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Shortlist item not found")
    session.delete(item)
    session.commit()
    return Response(status_code=204)


@router.get("/{shortlist_id}/export")
def download_shortlist(
    shortlist_id: int,
    session: Session = Depends(get_session),
) -> StreamingResponse:
    shortlist = _get_shortlist(session, shortlist_id)
    filename = quote(f"{shortlist.name}.xlsx")
    return StreamingResponse(
        export_shortlist(shortlist),
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
