import logging
import re

from sqlalchemy.orm import Session
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

from app.db import SessionLocal
from app.models import User, TopicBranch, Notification, ClassifiedArticle, Article, Feedback
from app.repositories.topics import TopicBranchRepository
from app.bot.notifier import record_feedback

logger = logging.getLogger(__name__)


def _get_db() -> Session:
    return SessionLocal()


def _ensure_user(db: Session, telegram_user) -> User | None:
    """Find or create a User from a Telegram user object."""
    tg_id = str(telegram_user.id)
    user = db.query(User).filter(User.tg_id == tg_id).first()
    if not user:
        user = User(tg_id=tg_id, username=telegram_user.username or telegram_user.first_name)
        db.add(user)
        db.flush()
    return user


# ── Commands ──────────────────────────────────────────────────────────────────────


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start — register user and greet."""
    telegram_user = update.effective_user
    if not telegram_user:
        return

    db = _get_db()
    try:
        user = _ensure_user(db, telegram_user)
        db.commit()
        await update.message.reply_text(  # type: ignore[union-attr]
            f"Привет, {telegram_user.first_name}! Добро пожаловать в Smart Stream.\n\n"
            f"Команды:\n"
            f"/topics — ваши темы\n"
            f"/add-topic <название> — добавить тему\n"
            f"/del-topic <id> — удалить тему\n"
            f"/articles — последние новости\n"
            f"/feed on — включить рассылку\n"
            f"/feed off — выключить рассылку"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error in /start: {e}")
        await update.message.reply_text("Ошибка при регистрации, попробуйте позже.")  # type: ignore[union-attr]
    finally:
        db.close()


async def topics_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /topics — list user's topic branches."""
    telegram_user = update.effective_user
    if not telegram_user:
        return

    db = _get_db()
    try:
        user = db.query(User).filter(User.tg_id == str(telegram_user.id)).first()
        if not user:
            await update.message.reply_text("Сначала нажмите /start")  # type: ignore[union-attr]
            return

        topics = db.query(TopicBranch).filter(
            TopicBranch.user_id == user.id,
            TopicBranch.active == True,
        ).all()

        if not topics:
            await update.message.reply_text(  # type: ignore[union-attr]
                "У вас пока нет тем.\nДобавьте: /add-topic <название>"
            )
            return

        lines = ["Ваши темы:"]
        for t in topics:
            lines.append(f"  {t.id}. {t.name}")

        await update.message.reply_text("\n".join(lines))  # type: ignore[union-attr]
    except Exception as e:
        logger.error(f"Error in /topics: {e}")
        await update.message.reply_text("Ошибка при получении списка тем.")  # type: ignore[union-attr]
    finally:
        db.close()


async def add_topic_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /add-topic <name> — create a topic branch for the user."""
    telegram_user = update.effective_user
    if not telegram_user:
        return

    text = (update.message or update.callback_query).text or ""  # type: ignore[union-attr]
    match = re.match(r"/add[_-]topic\s+(.+)", text, re.IGNORECASE)
    if not match:
        await update.message.reply_text("Использование: /add_topic <название>")  # type: ignore[union-attr]
        return

    topic_name = match.group(1).strip()
    if len(topic_name) > 512:
        await update.message.reply_text("Название темы слишком длинное (макс. 512 симв.).")  # type: ignore[union-attr]
        return

    db = _get_db()
    try:
        user = db.query(User).filter(User.tg_id == str(telegram_user.id)).first()
        if not user:
            await update.message.reply_text("Сначала нажмите /start")  # type: ignore[union-attr]
            return

        repo = TopicBranchRepository(db)
        topic = repo.create(name=topic_name, user_id=user.id)
        db.commit()

        msg = update.message or update.edited_message
        if msg:
            await msg.reply_text(f"Тема создана: {topic_name} (id={topic.id})")
    except Exception as e:
        db.rollback()
        logger.error(f"Error in /add-topic: {e}")
        await update.message.reply_text("Ошибка при создании темы.")  # type: ignore[union-attr]
    finally:
        db.close()


async def del_topic_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /del-topic <id> — delete user's topic branch."""
    telegram_user = update.effective_user
    if not telegram_user:
        return

    text = (update.message or update.callback_query).text or ""  # type: ignore[union-attr]
    match = re.match(r"/del[_-]topic\s+(\d+)", text)
    if not match:
        await update.message.reply_text("Использование: /del_topic <id>")  # type: ignore[union-attr]
        return

    topic_id = int(match.group(1))

    db = _get_db()
    try:
        user = db.query(User).filter(User.tg_id == str(telegram_user.id)).first()
        if not user:
            await update.message.reply_text("Сначала нажмите /start")  # type: ignore[union-attr]
            return

        topic = db.query(TopicBranch).filter(
            TopicBranch.id == topic_id,
            TopicBranch.user_id == user.id,
        ).first()

        if not topic:
            await update.message.reply_text("Тема не найдена или вам не принадлежит.")  # type: ignore[union-attr]
            return

        db.delete(topic)
        db.commit()
        await update.message.reply_text("Тема удалена.")  # type: ignore[union-attr]
    except Exception as e:
        db.rollback()
        logger.error(f"Error in /del-topic: {e}")
        await update.message.reply_text("Ошибка при удалении темы.")  # type: ignore[union-attr]
    finally:
        db.close()


async def articles_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /articles — show last 5 matched classified articles."""
    telegram_user = update.effective_user
    if not telegram_user:
        return

    db = _get_db()
    try:
        user = db.query(User).filter(User.tg_id == str(telegram_user.id)).first()
        if not user:
            await update.message.reply_text("Сначала нажмите /start")  # type: ignore[union-attr]
            return

        articles = (
            db.query(Article, ClassifiedArticle)
            .join(ClassifiedArticle, ClassifiedArticle.article_id == Article.id)
            .filter(
                ClassifiedArticle.topic_branch_id.in_(
                    db.query(TopicBranch.id).filter(TopicBranch.user_id == user.id)
                ),
                ClassifiedArticle.matched == True,
            )
            .order_by(Article.fetched_at.desc())
            .limit(5)
            .all()
        )

        if not articles:
            await update.message.reply_text("Нет новых новостей по вашим темам.")  # type: ignore[union-attr]
            return

        lines = []
        for article, ca in articles:
            digest = ca.digest or "Без дайджеста"
            lines.append(f"• {article.title}\n  {digest}\n  📎 {article.link}")

        text = "Последние новости:\n\n" + "\n\n".join(lines)

        # Build inline feedback buttons
        keyboard = []
        for article, ca in articles:
            keyboard.append([
                InlineKeyboardButton(
                    f"✅ {article.title[:20]}",
                    callback_data=f"feedback:{ca.id}:1",
                ),
                InlineKeyboardButton(
                    f"❌ {article.title[:20]}",
                    callback_data=f"feedback:{ca.id}:0",
                ),
            ])

        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        await update.message.reply_text(text, reply_markup=reply_markup)  # type: ignore[union-attr]
    except Exception as e:
        logger.error(f"Error in /articles: {e}")
        await update.message.reply_text("Ошибка при получении новостей.")  # type: ignore[union-attr]
    finally:
        db.close()


async def feed_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /feed on|off — toggle article delivery notifications."""
    telegram_user = update.effective_user
    if not telegram_user:
        return

    text = (update.message or update.callback_query).text or ""  # type: ignore[union-attr]
    match = re.match(r"/feed\s+(on|off)", text, re.IGNORECASE)
    if not match:
        await update.message.reply_text("Использование: /feed on | /feed off")  # type: ignore[union-attr]
        return

    action = match.group(1).lower()

    db = _get_db()
    try:
        user = db.query(User).filter(User.tg_id == str(telegram_user.id)).first()
        if not user:
            await update.message.reply_text("Сначала нажмите /start")  # type: ignore[union-attr]
            return

        if action == "on":
            topics = db.query(TopicBranch).filter(TopicBranch.user_id == user.id).all()
            created = 0
            for topic in topics:
                existing = db.query(Notification).filter(
                    Notification.user_id == user.id,
                    Notification.topic_branch_id == topic.id,
                    Notification.active == True,
                ).first()
                if not existing:
                    notif = Notification(user_id=user.id, topic_branch_id=topic.id)
                    db.add(notif)
                    created += 1
            db.commit()
            await update.message.reply_text(  # type: ignore[union-attr]
                f"Рассылка включена ({created} подписок создано)"
            )

        elif action == "off":
            count = db.query(Notification).filter(
                Notification.user_id == user.id,
                Notification.active == True,
            ).update({"active": False})
            db.commit()
            await update.message.reply_text(  # type: ignore[union-attr]
                f"Рассылка выключена ({count} подписок деактивировано)"
            )
    except Exception as e:
        db.rollback()
        logger.error(f"Error in /feed: {e}")
        await update.message.reply_text("Ошибка при изменении рассылки.")  # type: ignore[union-attr]
    finally:
        db.close()


# ── Callback handlers ─────────────────────────────────────────────────────────────


async def feedback_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline feedback button presses (✅ / ❌)."""
    query = update.callback_query
    if not query or not query.data:
        return

    # Parse callback_data: feedback:{classified_article_id}:{approved}
    parts = query.data.split(":")
    if len(parts) != 3 or parts[0] != "feedback":
        await query.answer("Некорректные данные")
        return

    try:
        classified_article_id = int(parts[1])
        approved = parts[2] == "1"
    except (ValueError, IndexError):
        await query.answer("Некорректные данные")
        return

    tg_id = str(query.from_user.id) if query.from_user else None
    if not tg_id:
        await query.answer("Ошибка пользователя")
        return

    success = record_feedback(tg_id, classified_article_id, approved)
    await query.answer("✅ Записано" if success else "❌ Ошибка")
