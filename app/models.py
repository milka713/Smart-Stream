import sqlalchemy
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    tg_id = Column(String(64), unique=True, nullable=False, index=True)
    username = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    topic_branches = relationship("TopicBranch", back_populates="user")
    feedbacks = relationship("Feedback", back_populates="user")
    notifications = relationship("Notification", back_populates="user")


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(2048), unique=True, nullable=False, index=True)
    name = Column(String(256), nullable=True)
    interval_min = Column(Integer, default=15, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    last_fetched = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    articles = relationship("Article", back_populates="source")


class TopicBranch(Base):
    __tablename__ = "topic_branches"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(512), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="topic_branches")
    classified_articles = relationship("ClassifiedArticle", back_populates="topic_branch")
    notifications = relationship("Notification", back_populates="topic_branch")


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    link = Column(String(2048), nullable=False, index=True)
    title = Column(String(1024), nullable=False)
    content = Column(Text, nullable=True)
    published = Column(DateTime, nullable=True)
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        sqlalchemy.UniqueConstraint("link", name="uq_article_link"),
    )

    source = relationship("Source", back_populates="articles")
    classified_articles = relationship("ClassifiedArticle", back_populates="article")


class ClassifiedArticle(Base):
    __tablename__ = "classified_articles"

    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey("articles.id"), nullable=False)
    topic_branch_id = Column(Integer, ForeignKey("topic_branches.id"), nullable=False)
    matched = Column(Boolean, nullable=False)
    digest = Column(Text, nullable=True)
    classified_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    article = relationship("Article", back_populates="classified_articles")
    topic_branch = relationship("TopicBranch", back_populates="classified_articles")
    feedbacks = relationship("Feedback", back_populates="classified_article")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    topic_branch_id = Column(Integer, ForeignKey("topic_branches.id"), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="notifications")
    topic_branch = relationship("TopicBranch", back_populates="notifications")

    __table_args__ = (
        sqlalchemy.UniqueConstraint("user_id", "topic_branch_id", name="uq_notification_user_topic"),
    )


class Feedback(Base):
    __tablename__ = "feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    classified_article_id = Column(Integer, ForeignKey("classified_articles.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved = Column(Boolean, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    classified_article = relationship("ClassifiedArticle", back_populates="feedbacks")
    user = relationship("User", back_populates="feedbacks")
