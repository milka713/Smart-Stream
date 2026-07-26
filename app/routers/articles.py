from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Article, ClassifiedArticle

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("/")
def list_articles(
    topic_id: int | None = None,
    source_id: int | None = None,
    matched_only: bool = True,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(Article).join(ClassifiedArticle)

    if matched_only:
        query = query.filter(ClassifiedArticle.matched == True)

    if topic_id:
        query = query.filter(ClassifiedArticle.topic_branch_id == topic_id)

    if source_id:
        query = query.filter(Article.source_id == source_id)

    query = query.order_by(Article.fetched_at.desc()).limit(limit)
    articles = query.all()

    result = []
    for article in articles:
        ca = article.classified_articles[0] if article.classified_articles else None
        topic = None
        digest = None
        matched = False
        if ca:
            topic = ca.topic_branch.name if ca.topic_branch else None
            digest = ca.digest
            matched = ca.matched
        result.append({
            "id": article.id,
            "title": article.title,
            "link": article.link,
            "source_id": article.source_id,
            "matched": matched,
            "topic": topic,
            "digest": digest,
            "fetched_at": article.fetched_at,
        })

    return result
