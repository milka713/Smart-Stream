import logging

from sqlalchemy.orm import Session
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from app.db import SessionLocal
from app.models import ClassifiedArticle, Feedback, Notification, User

logger = logging.getLogger(__name__)


def _send_to_user(bot: Bot, chat_id: int, title: str, digest: str, link: str,
                  topic_name: str, classified_article_id: int) -> None:
    """Send a single article notification to a Telegram user with feedback buttons."""
    text = (
        f"📰 *{title}*\n\n"
        f"{digest}\n\n"
        f"🏷 {topic_name}\n"
        f"📎 [{link}]({link})"
    )

    keyboard = [
        [
            InlineKeyboardButton("✅ Подходит", callback_data=f"feedback:{classified_article_id}:1"),
            InlineKeyboardButton("❌ Не подходит", callback_data=f"feedback:{classified_article_id}:0"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown",
                         reply_markup=reply_markup).result()
        logger.info(f"Sent notification to user {chat_id}: {title[:50]}")
    except Exception as e:
        logger.error(f"Failed to send notification to user {chat_id}: {e}")


def notify_match(bot: Bot, classified_article_id: int, title: str, digest: str,
                 link: str, topic_name: str) -> None:
    """Find all subscribers of the topic this article matched and send them the notification."""
    db = SessionLocal()
    try:
        ca = db.query(ClassifiedArticle).filter(
            ClassifiedArticle.id == classified_article_id
        ).first()
        if not ca:
            return

        users = (
            db.query(Notification)
            .filter(
                Notification.topic_branch_id == ca.topic_branch_id,
                Notification.active == True,
            )
            .join(Notification.user)
            .all()
        )

        for notif in users:
            user = notif.user
            if user and user.tg_id:
                _send_to_user(bot, int(user.tg_id), title, digest or "",
                              link, topic_name, classified_article_id)
    except Exception as e:
        logger.error(f"Error in notify_match: {e}")
    finally:
        db.close()


def record_feedback(tg_id: str, classified_article_id: int, approved: bool) -> bool:
    """Record feedback from a Telegram user for a classified article."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.tg_id == tg_id).first()
        if not user:
            logger.warning(f"No user found for tg_id={tg_id}")
            return False

        ca = db.query(ClassifiedArticle).filter(
            ClassifiedArticle.id == classified_article_id
        ).first()
        if not ca:
            logger.warning(f"No classified article found for id={classified_article_id}")
            return False

        feedback = Feedback(
            classified_article_id=classified_article_id,
            user_id=user.id,
            approved=approved,
        )
        db.add(feedback)
        db.commit()
        logger.info(f"Feedback recorded: user={tg_id}, article={classified_article_id}, approved={approved}")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error recording feedback: {e}")
        return False
    finally:
        db.close()
