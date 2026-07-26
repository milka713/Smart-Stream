from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Source


class SourceRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self, active_only: bool = False) -> List[Source]:
        query = self.db.query(Source)
        if active_only:
            query = query.filter(Source.active == True)
        return query.all()

    def get_by_id(self, source_id: int) -> Optional[Source]:
        return self.db.query(Source).filter(Source.id == source_id).first()

    def get_due(self) -> List[Source]:
        """Return active sources that are due for fetching."""
        now = datetime.utcnow()
        sources = self.db.query(Source).filter(Source.active == True).all()
        due = []
        for s in sources:
            if s.last_fetched is None:
                due.append(s)
            else:
                elapsed = (now - s.last_fetched).total_seconds() / 60
                if elapsed >= s.interval_min:
                    due.append(s)
        return due

    def create(self, url: str, name: Optional[str] = None, interval_min: int = 15) -> Source:
        source = Source(url=url, name=name, interval_min=interval_min)
        self.db.add(source)
        self.db.flush()
        return source

    def update(self, source_id: int, **kwargs) -> Optional[Source]:
        source = self.get_by_id(source_id)
        if source is None:
            return None
        for key, value in kwargs.items():
            if hasattr(source, key):
                setattr(source, key, value)
        self.db.flush()
        return source

    def delete(self, source_id: int) -> bool:
        source = self.get_by_id(source_id)
        if source is None:
            return False
        self.db.delete(source)
        self.db.flush()
        return True

    def mark_fetched(self, source: Source) -> None:
        source.last_fetched = datetime.utcnow()
        self.db.flush()
