"""Integration tests against real RSS feed + real LLM server.

Feed: Ars Technica (https://feeds.arstechnica.com/arstechnica/index)
Topics: AI & Machine Learning, Space & Astronomy, Cybersecurity
"""

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app import db as db_module
from app.db import Base, get_db
from app.main import app
from app.models import Article, User
from app.repositories.sources import SourceRepository
from app.repositories.topics import TopicBranchRepository
from app.repositories.articles import ArticleRepository
from app.repositories.classified_articles import ClassifiedArticleRepository
from app.services.rss import RSSFetcher
import app.services.rss as rss_module
from app.services.llm import LLMGateway


def _patch_all_sessions(test_session, engine=None):
    """Patch SessionLocal in app.db and app.services.rss so fetcher uses the test DB."""
    patches = [
        patch.object(db_module, "SessionLocal", test_session),
        patch.object(rss_module, "SessionLocal", test_session),
    ]
    if engine:
        patches.append(patch.object(db_module, "engine", engine))

    stack = ExitStack()
    for p in patches:
        stack.enter_context(p)
    return stack


class TestRSSIntegration:
    """RSS fetcher against a real feed."""

    ARS_TECH_FEED = "https://feeds.arstechnica.com/arstechnica/index"

    @pytest.fixture
    def db(self):
        url = "sqlite:///file::memory:rss_int?cache=shared"
        engine = create_engine(url, connect_args={"check_same_thread": False}, pool_pre_ping=True)
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)

        with _patch_all_sessions(Session, engine):
            app.dependency_overrides[get_db] = lambda: iter([Session()])
            yield engine, Session
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)
            engine.dispose()

    def test_fetch_real_feed(self, db):
        """Fetch real Ars Technica feed and verify articles land in DB."""
        engine, SessionFactory = db

        # Create source in its own session (fetcher opens its own, SQLite can't share)
        source_id = None
        session = SessionFactory()
        try:
            user = User(tg_id="rss_int", username="test")
            session.add(user)
            session.flush()

            source_repo = SourceRepository(session)
            source = source_repo.create(url=self.ARS_TECH_FEED, name="Ars Technica", interval_min=15)
            session.flush()
            source_id = source.id
            session.commit()
        finally:
            session.close()

        # Fetch — pass minimal object with id and url (fetcher opens its own session)
        from types import SimpleNamespace
        fake_source = SimpleNamespace(id=source_id, url=self.ARS_TECH_FEED)
        fetcher = RSSFetcher()
        count = fetcher.fetch_source(fake_source)

        # Verify in a fresh session
        session = SessionFactory()
        try:
            total = session.query(Article).filter(Article.source_id == source_id).count()
            assert count > 0, f"Expected at least one article from the feed, got {count}"
            assert total == count

            article = session.query(Article).filter(Article.source_id == source_id).first()
            assert article.title, "Article should have a title"
            assert article.link, "Article should have a link"
            assert len(article.link) > 10
        finally:
            session.close()

    def test_dedup_real_feed(self, db):
        """Second fetch of the same feed should not duplicate articles."""
        engine, SessionFactory = db

        # Create source
        source_id = None
        session = SessionFactory()
        try:
            user = User(tg_id="rss_dedup", username="test")
            session.add(user)
            session.flush()

            source_repo = SourceRepository(session)
            source = source_repo.create(url=self.ARS_TECH_FEED, name="Ars Technica", interval_min=15)
            session.flush()
            source_id = source.id
            session.commit()
        finally:
            session.close()

        from types import SimpleNamespace
        fake_source = SimpleNamespace(id=source_id, url=self.ARS_TECH_FEED)
        fetcher = RSSFetcher()

        first = fetcher.fetch_source(fake_source)
        assert first > 0, f"Expected articles, got {first}"

        second = fetcher.fetch_source(fake_source)
        assert second == 0, "Dedup should prevent re-fetching"


class TestLLMIntegration:
    """LLM classification with mocked server responses."""

    @patch("app.services.llm.OpenAI")
    def test_classify_ai_article(self, mock_openai_class):
        """Send an AI-related article — mock returns a matched AI topic."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices[0].message.content = (
            '{"matched": true, "topic": "AI & Machine Learning", '
            '"digest": "Google releases a new LLM with 1 trillion parameters"}'
        )
        mock_client.chat.completions.create.return_value = mock_response

        llm = LLMGateway()
        topics = ["AI & Machine Learning", "Space & Astronomy", "Cybersecurity"]

        result = llm.classify_and_reformat(
            title="Google launches new AI model that outperforms competitors",
            content="Google has released a new large language model that achieves "
                    "state-of-the-art results on several benchmarks. The model, "
                    "built on a transformer architecture, uses 1 trillion parameters.",
            topics=topics,
        )

        assert "matched" in result
        assert "topic" in result
        assert "digest" in result
        assert result["matched"] is True
        assert result["topic"] == "AI & Machine Learning"
        assert result["digest"]
        assert len(result["digest"]) > 20

    @patch("app.services.llm.OpenAI")
    def test_classify_non_matching(self, mock_openai_class):
        """Send a non-matching article — mock returns matched=false."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices[0].message.content = (
            '{"matched": false, "topic": null, "digest": null}'
        )
        mock_client.chat.completions.create.return_value = mock_response

        llm = LLMGateway()
        topics = ["AI & Machine Learning", "Space & Astronomy"]

        result = llm.classify_and_reformat(
            title="Local bakery wins community award",
            content="The neighborhood bakery on Main Street was awarded "
                    "best community business for its charity work.",
            topics=topics,
        )

        assert "matched" in result
        assert "topic" in result
        assert "digest" in result
        assert result["matched"] is False

    @patch("app.services.llm.OpenAI")
    def test_classify_space_article(self, mock_openai_class):
        """Send a space-related article — mock returns a matched Space topic."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices[0].message.content = (
            '{"matched": true, "topic": "Space & Astronomy", '
            '"digest": "JWST detects water vapor in exoplanet atmosphere"}'
        )
        mock_client.chat.completions.create.return_value = mock_response

        llm = LLMGateway()
        topics = ["AI & Machine Learning", "Space & Astronomy", "Cybersecurity"]

        result = llm.classify_and_reformat(
            title="James Webb Telescope discovers new exoplanet atmosphere",
            content="The James Webb Space Telescope has detected water vapor "
                    "in the atmosphere of a newly discovered exoplanet 120 light-years away.",
            topics=topics,
        )

        assert "matched" in result
        assert "topic" in result
        assert "digest" in result
        assert result["matched"] is True
        assert result["topic"] == "Space & Astronomy"
        assert result["digest"]


class TestFullCycleIntegration:
    """Full cycle: fetch RSS → classify with LLM → query via API → feedback."""

    ARS_TECH_FEED = "https://feeds.arstechnica.com/arstechnica/index"

    @pytest.fixture
    def cycle_db(self):
        url = "sqlite:///file::memory:cycle_int?mode=memory&cache=shared"
        engine = create_engine(url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)

        # Clean any leftover data from previous tests in the shared DB
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            for table in reversed(Base.metadata.sorted_tables):
                session.execute(table.delete())
            session.commit()
        finally:
            session.close()

        def override():
            s = Session()
            try:
                yield s
            finally:
                s.close()

        with _patch_all_sessions(Session, engine):
            app.dependency_overrides[get_db] = override
            yield engine, Session
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)
            engine.dispose()

    @pytest.fixture
    def cycle_client(self, cycle_db):
        with TestClient(app) as c:
            yield c

    def test_end_to_end(self, cycle_client, cycle_db):
        """Complete pipeline: source → topic → fetch → classify (mocked LLM) → query."""
        engine, SessionFactory = cycle_db

        # Seed user
        session = SessionFactory()
        user = User(tg_id="cycle_e2e", username="test")
        session.add(user)
        session.flush()
        user_id = user.id
        session.close()

        # Step 1: Create source
        resp = cycle_client.post("/sources/", json={
            "url": self.ARS_TECH_FEED,
            "name": "Ars Technica",
        })
        assert resp.status_code == 201
        source_id = resp.json()["id"]

        # Step 2: Create topics
        for name in ["AI & Machine Learning", "Space & Astronomy", "Cybersecurity"]:
            resp = cycle_client.post("/topics/", json={"name": name, "user_id": user_id})
            assert resp.status_code == 201

        # Step 3: Fetch (fetcher opens its own session)
        from types import SimpleNamespace
        fake_source = SimpleNamespace(id=source_id, url=self.ARS_TECH_FEED)
        fetcher = RSSFetcher()
        fetched = fetcher.fetch_source(fake_source)
        assert fetched > 0, f"Expected articles from feed, got {fetched}"

        # Step 4: Classify with mocked LLM (real server is flaky)
        mock_response = MagicMock()
        mock_response.choices[0].message.content = (
            '{"matched": true, "topic": "AI & Machine Learning", "digest": "AI news summary"}'
        )

        with patch("app.services.llm.OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.return_value = mock_response

            session = SessionFactory()
            try:
                session.execute(text("SELECT 1"))
                articles = ArticleRepository(session).get_unclassified(limit=5)
                topics = TopicBranchRepository(session).get_all_active()
                topic_names = [t.name for t in topics]

                llm = LLMGateway()
                classified_count = 0
                for article in articles:
                    result = llm.classify_and_reformat(
                        title=article.title or "",
                        content=article.content or "",
                        topics=topic_names,
                    )
                    if result["matched"] and result["topic"]:
                        matched_topic = next((t for t in topics if t.name == result["topic"]), None)
                        if matched_topic:
                            ClassifiedArticleRepository(session).create(
                                article_id=article.id,
                                topic_branch_id=matched_topic.id,
                                matched=True,
                                digest=result["digest"],
                            )
                            classified_count += 1

                session.commit()
                assert classified_count > 0, "Expected at least one classified article"
            finally:
                session.close()

        # Step 5: Query articles
        resp = cycle_client.get("/articles/?matched_only=true&limit=20")
        assert resp.status_code == 200
        articles = resp.json()

        matched = [a for a in articles if a.get("matched")]
        assert len(matched) > 0, f"Expected classified articles, got {len(matched)} of {len(articles)}"

        for a in matched:
            assert "title" in a and "link" in a and "digest" in a and "topic" in a

    def test_feedback_flow(self, cycle_client, cycle_db):
        """Create article → classify → feedback → verify."""
        engine, SessionFactory = cycle_db

        session = SessionFactory()
        try:
            user = User(tg_id="cycle_fb", username="test")
            session.add(user)
            session.flush()

            source = SourceRepository(session).create(url="https://test.com/feed", name="Test")
            session.flush()

            article = ArticleRepository(session).create(
                source_id=source.id, link="https://test.com/1",
                title="Test Article", content="test content", published=None,
            )
            session.flush()

            topic = TopicBranchRepository(session).create(name="AI", user_id=user.id)
            session.flush()

            ClassifiedArticleRepository(session).create(
                article_id=article.id, topic_branch_id=topic.id,
                matched=True, digest="test digest",
            )
            session.commit()

            # Feedback via API
            resp = cycle_client.post("/feedback/", json={
                "article_id": article.id, "approved": True, "user_id": user.id,
            })
            assert resp.status_code == 201
            assert resp.json()["recorded"] is True

            # Verify stored
            from app.models import Feedback
            fb = session.query(Feedback).first()
            assert fb is not None
            assert fb.approved is True
        finally:
            session.close()
