from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db import get_db
from app.repositories.topics import TopicBranchRepository

router = APIRouter(prefix="/topics", tags=["topics"])


class TopicCreate(BaseModel):
    name: str
    user_id: int = 1


class TopicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    user_id: int
    active: bool


@router.post("/", status_code=201, response_model=TopicResponse)
def create_topic(data: TopicCreate, db: Session = Depends(get_db)):
    repo = TopicBranchRepository(db)
    topic = repo.create(name=data.name, user_id=data.user_id)
    db.commit()
    return topic


@router.get("/", response_model=list[TopicResponse])
def list_topics(user_id: int | None = None, db: Session = Depends(get_db)):
    repo = TopicBranchRepository(db)
    topics = repo.get_all_active()
    if user_id:
        topics = [t for t in topics if t.user_id == user_id]
    return topics


@router.delete("/{topic_id}")
def delete_topic(topic_id: int, db: Session = Depends(get_db)):
    repo = TopicBranchRepository(db)
    if not repo.delete(topic_id):
        raise HTTPException(status_code=404, detail="Topic not found")
    db.commit()
    return {"deleted": True}
