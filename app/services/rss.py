import logging
import re
from datetime import datetime
from time import mktime
from typing import Any, Dict

import feedparser
import httpx

from app.db import SessionLocal
from app.repositories.articles import ArticleRepository
from app.repositories.sources import SourceRepository

logger = logging.getLogger(__name__)


class RSSFetcher:
    def __init__(self, timeout: int = 30):
        self._timeout = timeout

    def _fetch_feed(self, url: str) -> Any:
        try:
            response = httpx.get(url, timeout=self._timeout, follow_redirects=True)
            response.raise_for_status()
            return feedparser.parse(response.text)
        except Exception as e:
            logger.error(f"Failed to fetch feed {url}: {e}")
            return feedparser.parse("")

    def _parse_published(self, entry) -> datetime | None:
        parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
        if parsed:
            try:
                return datetime.fromtimestamp(mktime(parsed))
            except Exception:
                pass
        return None

    def _strip_html(self, text: str) -> str:
        if not text:
            return ""
        return re.sub(r"<[^>]+>", "", text)

    def _extract_content(self, entry) -> str:
        raw = ""
        if getattr(entry, "content", None):
            raw = entry["content"][0].get("value", "")
        if not raw:
            raw = getattr(entry, "summary", "")
        return self._strip_html(raw)

    def fetch_source(self, source) -> int:
        """Fetch a single source, return count of new articles."""
        feed = self._fetch_feed(source.url)
        if not feed.entries:
            logger.warning(f"No entries in feed {source.url}")
            return 0

        db = SessionLocal()
        try:
            article_repo = ArticleRepository(db)
            new_count = 0

            for entry in feed.entries:
                link = getattr(entry, "link", "")
                title = getattr(entry, "title", "")
                if not link or not title:
                    continue

                if article_repo.exists_by_link(link):
                    continue

                article_repo.create(
                    source_id=source.id,
                    link=link,
                    title=title,
                    content=self._extract_content(entry),
                    published=self._parse_published(entry),
                )
                new_count += 1

            db.commit()
            logger.info(f"Fetched {new_count} new articles from {source.url}")
            return new_count
        except Exception as e:
            db.rollback()
            logger.error(f"Error processing feed {source.url}: {e}")
            return 0
        finally:
            db.close()

    def fetch_all_due(self) -> Dict[str, int]:
        """Fetch all due sources, return {url: new_count} summary."""
        db = SessionLocal()
        try:
            source_repo = SourceRepository(db)
            due_sources = source_repo.get_due()
            results = {}

            for source in due_sources:
                count = self.fetch_source(source)
                results[source.url] = count
                source_repo.mark_fetched(source)

            db.commit()
            return results
        except Exception as e:
            db.rollback()
            logger.error(f"Error in fetch_all_due: {e}")
            return {}
        finally:
            db.close()
