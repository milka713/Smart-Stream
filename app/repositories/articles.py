from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Article


class ArticleRepository:
    def __init__(self, db: Session):
        self.db = db

    def exists_by_link(self, link: str) -> bool:
        return self.db.query(Article).filter(Article.link == link).first() is not None

    def create(
        self,
        source_id: int,
        link: str,
        title: str,
        content: Optional[str],
        published: Optional[datetime],
    ) -> Article:
        article = Article(
            source_id=source_id,
            link=link,
            title=title,
            content=content,
            published=published,
        )
        self.db.add(article)
        self.db.flush()
        return article

    def get_unclassified(self, limit: int = 50) -> List[Article]:
        """Return articles that have no classified_articles yet."""
        return (
            self.db.query(Article)
            .outerjoin(Article.classified_articles)
            .filter(Article.classified_articles.any().not_())
            .limit(limit)
            .all()
        )
