from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.db import get_db
from app.models import Article, ClassifiedArticle, TopicBranch

router = APIRouter(prefix="/articles", tags=["articles"])


class ArticleResponse(BaseModel):
    id: int
    title: str
    link: str
    source_id: int
    matched: bool = False
    topic: str | None = None
    digest: str | None = None
    fetched_at: datetime

    model_config = {"from_attributes": True}


@router.get("/", response_model=list[ArticleResponse])
def list_articles(
    topic_id: int | None = None,
    source_id: int | None = None,
    matched_only: bool = True,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    ca_alias = aliased(ClassifiedArticle)
    tb_alias = aliased(TopicBranch)

    stmt = (
        select(
            Article.id,
            Article.title,
            Article.link,
            Article.source_id,
            Article.fetched_at,
            ca_alias.matched,
            ca_alias.digest,
            tb_alias.name.label("topic"),
        )
        .select_from(Article)
        .outerjoin(ca_alias, ca_alias.article_id == Article.id)
        .outerjoin(tb_alias, tb_alias.id == ca_alias.topic_branch_id)
        .order_by(Article.fetched_at.desc())
        .limit(limit)
    )

    if matched_only:
        stmt = stmt.filter(
            (ca_alias.matched == True) | (ca_alias.id.is_(None))
        )

    if topic_id:
        stmt = stmt.filter(ca_alias.topic_branch_id == topic_id)

    if source_id:
        stmt = stmt.filter(Article.source_id == source_id)

    rows = db.execute(stmt).all()

    result = []
    for r in rows:
        result.append(
            ArticleResponse(
                id=r.id,
                title=r.title,
                link=r.link,
                source_id=r.source_id,
                matched=r.matched if r.matched is not None else False,
                topic=r.topic,
                digest=r.digest,
                fetched_at=r.fetched_at,
            )
        )

    return result
