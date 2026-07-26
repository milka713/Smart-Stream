from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ClassifiedArticle, Feedback

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackCreate(BaseModel):
    article_id: int
    approved: bool
    user_id: int = 1


@router.post("/")
def submit_feedback(data: FeedbackCreate, db: Session = Depends(get_db)):
    ca = db.query(ClassifiedArticle).filter(
        ClassifiedArticle.article_id == data.article_id
    ).first()

    if not ca:
        raise HTTPException(status_code=404, detail="Classified article not found")

    feedback = Feedback(
        classified_article_id=ca.id,
        user_id=data.user_id,
        approved=data.approved,
    )
    db.add(feedback)
    db.commit()
    return {"recorded": True, "approved": data.approved}
