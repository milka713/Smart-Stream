from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import TopicBranch


class TopicBranchRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all_active(self) -> List[TopicBranch]:
        return self.db.query(TopicBranch).filter(TopicBranch.active == True).all()

    def get_by_id(self, topic_id: int) -> Optional[TopicBranch]:
        return self.db.query(TopicBranch).filter(TopicBranch.id == topic_id).first()

    def create(self, name: str, user_id: int) -> TopicBranch:
        topic = TopicBranch(name=name, user_id=user_id)
        self.db.add(topic)
        self.db.flush()
        return topic

    def update(self, topic_id: int, **kwargs) -> Optional[TopicBranch]:
        topic = self.get_by_id(topic_id)
        if topic is None:
            return None
        for key, value in kwargs.items():
            if hasattr(topic, key):
                setattr(topic, key, value)
        self.db.flush()
        return topic

    def delete(self, topic_id: int) -> bool:
        topic = self.get_by_id(topic_id)
        if topic is None:
            return False
        self.db.delete(topic)
        self.db.flush()
        return True
