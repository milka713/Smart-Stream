import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.db import SessionLocal
from app.bot.bot import get_bot
from app.bot.notifier import notify_match
from app.repositories.articles import ArticleRepository
from app.repositories.classified_articles import ClassifiedArticleRepository
from app.repositories.topics import TopicBranchRepository
from app.services.llm import LLMGateway
from app.services.rss import RSSFetcher

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def _process_new_articles() -> None:
    """Fetch due RSS sources, then classify new articles."""
    # Step 1 — fetch
    fetcher = RSSFetcher()
    fetcher.fetch_all_due()

    # Step 2 — classify unclassified articles
    db = SessionLocal()
    try:
        article_repo = ArticleRepository(db)
        topic_repo = TopicBranchRepository(db)
        classified_repo = ClassifiedArticleRepository(db)

        articles = article_repo.get_unclassified(limit=20)
        topics = topic_repo.get_all_active()

        if not articles:
            return
        if not topics:
            logger.info("No active topics — skipping classification")
            return

        topic_names = [t.name for t in topics]
        topic_map = {t.name: t for t in topics}
        llm = LLMGateway()
        matched_notifications: list[dict] = []

        for article in articles:
            result = llm.classify_and_reformat(
                article.title,
                article.content or "",
                topic_names,
            )

            matched_topic_name = result.get("topic")
            if result.get("matched") and matched_topic_name and matched_topic_name in topic_map:
                tb = topic_map[matched_topic_name]
                ca = classified_repo.create(
                    article_id=article.id,
                    topic_branch_id=tb.id,
                    matched=True,
                    digest=result.get("digest"),
                )
                logger.info(f"Classified article {article.id}: topic={matched_topic_name}")
                matched_notifications.append({
                    "classified_article_id": ca.id,
                    "title": article.title,
                    "digest": result.get("digest") or "",
                    "link": article.link,
                    "topic_name": matched_topic_name,
                })
            else:
                # Mark as processed so we don't retry on next cycle.
                # Uses the first topic as a placeholder — the key signal is matched=False.
                classified_repo.create(
                    article_id=article.id,
                    topic_branch_id=topics[0].id,
                    matched=False,
                )
                logger.info(f"Classified article {article.id}: no match")

        db.commit()

        # Step 3 — notify subscribers via Telegram
        tg_bot = get_bot()
        if tg_bot and matched_notifications:
            for notif in matched_notifications:
                notify_match(bot=tg_bot, **notif)
    except Exception as e:
        db.rollback()
        logger.error(f"Error in _process_new_articles: {e}")
    finally:
        db.close()


def start_scheduler() -> None:
    """Start the background scheduler."""
    if not scheduler.running:
        scheduler.add_job(
            _process_new_articles,
            "interval",
            minutes=settings.rss_cycle_interval_min,
            id="rss_cycle",
        )
        scheduler.start()
        logger.info(f"Scheduler started — RSS cycle every {settings.rss_cycle_interval_min} min")


def stop_scheduler() -> None:
    """Shutdown the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
