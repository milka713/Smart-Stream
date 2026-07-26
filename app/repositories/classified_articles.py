from typing import Optional

from sqlalchemy.orm import Session

from app.models import ClassifiedArticle


class ClassifiedArticleRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        article_id: int,
        topic_branch_id: int,
        matched: bool,
        digest: Optional[str] = None,
    ) -> ClassifiedArticle:
        ca = ClassifiedArticle(
            article_id=article_id,
            topic_branch_id=topic_branch_id,
            matched=matched,
            digest=digest,
        )
        self.db.add(ca)
        self.db.flush()
        return ca
