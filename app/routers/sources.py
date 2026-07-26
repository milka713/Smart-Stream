from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db import get_db
from app.repositories.sources import SourceRepository

router = APIRouter(prefix="/sources", tags=["sources"])


class SourceCreate(BaseModel):
    url: str
    name: str | None = None
    interval_min: int = 15


class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    name: str | None
    interval_min: int
    active: bool
    last_fetched: datetime | None = None


@router.post("/", status_code=201, response_model=SourceResponse)
def create_source(data: SourceCreate, db: Session = Depends(get_db)):
    repo = SourceRepository(db)
    source = repo.create(url=data.url, name=data.name, interval_min=data.interval_min)
    db.commit()
    return source


@router.get("/", response_model=list[SourceResponse])
def list_sources(active_only: bool = False, db: Session = Depends(get_db)):
    repo = SourceRepository(db)
    return repo.get_all(active_only=active_only)


@router.delete("/{source_id}")
def delete_source(source_id: int, db: Session = Depends(get_db)):
    repo = SourceRepository(db)
    if not repo.delete(source_id):
        raise HTTPException(status_code=404, detail="Source not found")
    db.commit()
    return {"deleted": True}
