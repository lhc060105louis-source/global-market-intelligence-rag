from fastapi import APIRouter, Depends
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.database import Base, get_session

router = APIRouter(prefix="/dev", tags=["Development"])


@router.post("/reset-database")
def reset_database(session: Session = Depends(get_session)) -> dict[str, str]:
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(delete(table))
    session.commit()
    return {"status": "reset"}
