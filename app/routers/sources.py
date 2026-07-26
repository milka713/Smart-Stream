from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.repositories.sources import SourceRepository

router = APIRouter(prefix="/sources", tags=["sources"])


class SourceCreate(BaseModel):
    url: str
    name: str | None = None
    interval_min: int = 15


@router.post("/", status_code=201)
def create_source(data: SourceCreate, db: Session = Depends(get_db)):
    repo = SourceRepository(db)
    source = repo.create(url=data.url, name=data.name, interval_min=data.interval_min)
    db.commit()
    return source


@router.get("/")
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
