import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from app.services.rss import RSSFetcher
from app.models import Source, User
from app.db import SessionLocal, Base, engine


def test_rss_fetcher_strip_html():
    fetcher = RSSFetcher()
    assert fetcher._strip_html("<p>Hello <b>world</b></p>") == "Hello world"
    assert fetcher._strip_html("") == ""
    assert fetcher._strip_html(None) == ""


def test_rss_fetcher_parse_published():
    fetcher = RSSFetcher()

    class FakeEntry:
        published_parsed = (2026, 7, 25, 12, 0, 0, 4, 206, 0)
        updated_parsed = None

    entry = FakeEntry()
    result = fetcher._parse_published(entry)
    assert isinstance(result, datetime)
    assert result.year == 2026


def test_rss_fetcher_parse_published_none():
    fetcher = RSSFetcher()

    class FakeEntry:
        published_parsed = None
        updated_parsed = None

    assert fetcher._parse_published(FakeEntry()) is None


@patch("app.services.rss.httpx.get")
def test_rss_fetcher_no_entries(mock_get):
    mock_response = MagicMock()
    mock_response.text = "<?xml version='1.0'?><rss><channel></channel></rss>"
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response

    db = SessionLocal()
    try:
        user = User(tg_id="test_rss", username="test")
        db.add(user)
        db.flush()

        source = Source(url="https://empty.com/feed", name="Empty")
        db.add(source)
        db.flush()

        fetcher = RSSFetcher()
        count = fetcher.fetch_source(source)
        assert count == 0
    finally:
        db.close()


def test_rss_fetcher_dedup():
    db = SessionLocal()
    try:
        from app.repositories.articles import ArticleRepository
        repo = ArticleRepository(db)

        repo.create(source_id=1, link="https://dup.com/1", title="Dup", content="test", published=None)
        db.flush()

        assert repo.exists_by_link("https://dup.com/1") is True
        assert repo.exists_by_link("https://dup.com/2") is False
    finally:
        db.close()
