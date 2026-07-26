import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import db as db_module
from app.bot.handlers import (
    start_handler,
    topics_handler,
    add_topic_handler,
    del_topic_handler,
    articles_handler,
    feed_handler,
    feedback_callback_handler,
)
from app.bot.notifier import record_feedback
from app.db import Base
from app.models import User, TopicBranch, Notification, ClassifiedArticle, Article, Feedback

TEST_DB_URL = "sqlite:///file::memory:?cache=shared"


@pytest.fixture
def bot_db():
    """In-memory SQLite for bot handler tests — patches app.db so handlers use it too."""
    test_engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    TestSession = sessionmaker(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    with patch.object(db_module, "engine", test_engine), \
         patch.object(db_module, "SessionLocal", TestSession):

        def override_get_db():
            session = TestSession()
            try:
                yield session
            finally:
                session.close()

        session = TestSession()
        try:
            yield session
        finally:
            session.close()
            Base.metadata.drop_all(bind=test_engine)
            test_engine.dispose()


def _mock_telegram_user(tg_id: int = 12345, username: str = "testuser", first_name: str = "Test") -> MagicMock:
    user = MagicMock()
    user.id = tg_id
    user.username = username
    user.first_name = first_name
    return user


def _mock_message(text: str = "/start") -> MagicMock:
    msg = MagicMock()
    msg.text = text
    msg.reply_text = AsyncMock(return_value=None)
    return msg


def _mock_update(message: MagicMock | None = None, callback_query: MagicMock | None = None) -> MagicMock:
    update = MagicMock()
    update.effective_user = _mock_telegram_user()
    update.message = message or _mock_message()
    update.callback_query = callback_query
    return update


def _mock_context() -> MagicMock:
    return MagicMock()


@pytest.mark.asyncio
async def test_start_handler_registers_user(bot_db):
    update = _mock_update()
    context = _mock_context()

    with patch("app.bot.handlers._get_db", return_value=bot_db):
        await start_handler(update, context)

    user = bot_db.query(User).filter(User.tg_id == "12345").first()
    assert user is not None
    assert user.username == "testuser"
    update.message.reply_text.assert_called_once()
    response = update.message.reply_text.call_args[0][0]
    assert "Привет" in response
    assert "Smart Stream" in response


@pytest.mark.asyncio
async def test_start_handler_idempotent(bot_db):
    # Pre-create user
    user = User(tg_id="12345", username="testuser")
    bot_db.add(user)
    bot_db.commit()

    update = _mock_update()
    context = _mock_context()

    with patch("app.bot.handlers._get_db", return_value=bot_db):
        await start_handler(update, context)

    users = bot_db.query(User).filter(User.tg_id == "12345").all()
    assert len(users) == 1


@pytest.mark.asyncio
async def test_topics_handler_no_topics(bot_db):
    user = User(tg_id="12345", username="testuser")
    bot_db.add(user)
    bot_db.commit()

    update = _mock_update()
    context = _mock_context()

    with patch("app.bot.handlers._get_db", return_value=bot_db):
        await topics_handler(update, context)

    update.message.reply_text.assert_called_once()
    response = update.message.reply_text.call_args[0][0]
    assert "нет тем" in response.lower() or "нет" in response.lower()


@pytest.mark.asyncio
async def test_topics_handler_lists_topics(bot_db):
    user = User(tg_id="12345", username="testuser")
    bot_db.add(user)
    bot_db.flush()

    topic = TopicBranch(name="ИИ", user_id=user.id)
    bot_db.add(topic)
    bot_db.commit()

    update = _mock_update()
    context = _mock_context()

    with patch("app.bot.handlers._get_db", return_value=bot_db):
        await topics_handler(update, context)

    response = update.message.reply_text.call_args[0][0]
    assert "ИИ" in response


@pytest.mark.asyncio
async def test_topics_handler_not_registered(bot_db):
    update = _mock_update()
    context = _mock_context()

    with patch("app.bot.handlers._get_db", return_value=bot_db):
        await topics_handler(update, context)

    response = update.message.reply_text.call_args[0][0]
    assert "/start" in response


@pytest.mark.asyncio
async def test_add_topic_handler_creates_topic(bot_db):
    user = User(tg_id="12345", username="testuser")
    bot_db.add(user)
    bot_db.commit()
    user_id = user.id

    update = _mock_update(_mock_message("/add_topic Квантовые компьютеры"))
    context = _mock_context()

    with patch("app.bot.handlers._get_db", return_value=bot_db):
        await add_topic_handler(update, context)

    topic = bot_db.query(TopicBranch).filter(
        TopicBranch.name == "Квантовые компьютеры",
        TopicBranch.user_id == user_id,
    ).first()
    assert topic is not None
    assert topic.active is True


@pytest.mark.asyncio
async def test_add_topic_handler_with_hyphen(bot_db):
    user = User(tg_id="12345", username="testuser")
    bot_db.add(user)
    bot_db.commit()

    update = _mock_update(_mock_message("/add-topic Квантовые компьютеры"))
    context = _mock_context()

    with patch("app.bot.handlers._get_db", return_value=bot_db):
        await add_topic_handler(update, context)

    topic = bot_db.query(TopicBranch).filter(
        TopicBranch.name == "Квантовые компьютеры",
    ).first()
    assert topic is not None


@pytest.mark.asyncio
async def test_add_topic_handler_no_name(bot_db):
    user = User(tg_id="12345", username="testuser")
    bot_db.add(user)
    bot_db.commit()

    update = _mock_update(_mock_message("/add_topic"))
    context = _mock_context()

    with patch("app.bot.handlers._get_db", return_value=bot_db):
        await add_topic_handler(update, context)

    response = update.message.reply_text.call_args[0][0]
    assert "Использование" in response


@pytest.mark.asyncio
async def test_add_topic_handler_not_registered(bot_db):
    update = _mock_update(_mock_message("/add_topic Тест"))
    context = _mock_context()

    with patch("app.bot.handlers._get_db", return_value=bot_db):
        await add_topic_handler(update, context)

    response = update.message.reply_text.call_args[0][0]
    assert "/start" in response


@pytest.mark.asyncio
async def test_del_topic_handler_deletes_topic(bot_db):
    user = User(tg_id="12345", username="testuser")
    bot_db.add(user)
    bot_db.flush()

    topic = TopicBranch(name="Удалить", user_id=user.id)
    bot_db.add(topic)
    bot_db.commit()
    topic_id = topic.id

    update = _mock_update(_mock_message(f"/del_topic {topic_id}"))
    context = _mock_context()

    with patch("app.bot.handlers._get_db", return_value=bot_db):
        await del_topic_handler(update, context)

    remaining = bot_db.query(TopicBranch).filter(TopicBranch.id == topic_id).first()
    assert remaining is None


@pytest.mark.asyncio
async def test_del_topic_handler_not_found(bot_db):
    user = User(tg_id="12345", username="testuser")
    bot_db.add(user)
    bot_db.commit()

    update = _mock_update(_mock_message("/del_topic 999"))
    context = _mock_context()

    with patch("app.bot.handlers._get_db", return_value=bot_db):
        await del_topic_handler(update, context)

    response = update.message.reply_text.call_args[0][0]
    assert "не найдена" in response.lower() or "не найдена" in response


@pytest.mark.asyncio
async def test_del_topic_handler_other_user_topic(bot_db):
    user1 = User(tg_id="111", username="user1")
    user2 = User(tg_id="222", username="user2")
    bot_db.add_all([user1, user2])
    bot_db.flush()

    topic = TopicBranch(name="Чужая", user_id=user1.id)
    bot_db.add(topic)
    bot_db.commit()

    update = _mock_update(_mock_message(f"/del_topic {topic.id}"))
    update.effective_user = _mock_telegram_user(tg_id=222, username="user2", first_name="User2")
    context = _mock_context()

    with patch("app.bot.handlers._get_db", return_value=bot_db):
        await del_topic_handler(update, context)

    response = update.message.reply_text.call_args[0][0]
    assert "не найдена" in response.lower() or "не принадлежит" in response.lower()


@pytest.mark.asyncio
async def test_articles_handler_no_articles(bot_db):
    user = User(tg_id="12345", username="testuser")
    bot_db.add(user)
    bot_db.commit()

    update = _mock_update()
    update.message.text = "/articles"
    context = _mock_context()

    with patch("app.bot.handlers._get_db", return_value=bot_db):
        await articles_handler(update, context)

    response = update.message.reply_text.call_args[0][0]
    assert "нет" in response.lower()


@pytest.mark.asyncio
async def test_articles_handler_not_registered(bot_db):
    update = _mock_update()
    update.message.text = "/articles"
    context = _mock_context()

    with patch("app.bot.handlers._get_db", return_value=bot_db):
        await articles_handler(update, context)

    response = update.message.reply_text.call_args[0][0]
    assert "/start" in response


@pytest.mark.asyncio
async def test_feed_on_creates_notifications(bot_db):
    user = User(tg_id="12345", username="testuser")
    bot_db.add(user)
    bot_db.flush()
    user_id = user.id

    topic1 = TopicBranch(name="Тема1", user_id=user_id)
    topic2 = TopicBranch(name="Тема2", user_id=user_id)
    bot_db.add_all([topic1, topic2])
    bot_db.commit()

    update = _mock_update(_mock_message("/feed on"))
    context = _mock_context()

    with patch("app.bot.handlers._get_db", return_value=bot_db):
        await feed_handler(update, context)

    notifs = bot_db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.active == True,
    ).all()
    assert len(notifs) == 2


@pytest.mark.asyncio
async def test_feed_off_deactivates_notifications(bot_db):
    user = User(tg_id="12345", username="testuser")
    bot_db.add(user)
    bot_db.flush()
    user_id = user.id

    topic = TopicBranch(name="Тема", user_id=user_id)
    bot_db.add(topic)
    bot_db.flush()
    topic_id = topic.id

    notif = Notification(user_id=user_id, topic_branch_id=topic_id, active=True)
    bot_db.add(notif)
    bot_db.commit()
    notif_id = notif.id

    update = _mock_update(_mock_message("/feed off"))
    context = _mock_context()

    with patch("app.bot.handlers._get_db", return_value=bot_db):
        await feed_handler(update, context)

    updated = bot_db.query(Notification).filter(Notification.id == notif_id).first()
    assert updated is not None
    assert updated.active is False


@pytest.mark.asyncio
async def test_feed_handler_invalid_command(bot_db):
    user = User(tg_id="12345", username="testuser")
    bot_db.add(user)
    bot_db.commit()

    update = _mock_update(_mock_message("/feed"))
    context = _mock_context()

    with patch("app.bot.handlers._get_db", return_value=bot_db):
        await feed_handler(update, context)

    response = update.message.reply_text.call_args[0][0]
    assert "Использование" in response


@pytest.mark.asyncio
async def test_feedback_callback_approved(bot_db):
    user = User(tg_id="12345", username="testuser")
    bot_db.add(user)
    bot_db.flush()
    user_id = user.id

    topic = TopicBranch(name="Тема", user_id=user_id)
    bot_db.add(topic)
    bot_db.flush()
    topic_id = topic.id

    article = Article(source_id=1, link="http://test.com", title="Test")
    bot_db.add(article)
    bot_db.flush()
    article_id = article.id

    ca = ClassifiedArticle(article_id=article_id, topic_branch_id=topic_id, matched=True)
    bot_db.add(ca)
    bot_db.commit()
    ca_id = ca.id

    callback_query = MagicMock()
    callback_query.data = f"feedback:{ca_id}:1"
    callback_query.from_user = _mock_telegram_user()
    callback_query.answer = AsyncMock(return_value=None)

    update = _mock_update(callback_query=callback_query)
    context = _mock_context()

    with patch("app.bot.notifier.SessionLocal", return_value=bot_db):
        await feedback_callback_handler(update, context)

    feedback = bot_db.query(Feedback).filter(
        Feedback.classified_article_id == ca_id,
        Feedback.user_id == user_id,
        Feedback.approved == True,
    ).first()
    assert feedback is not None


@pytest.mark.asyncio
async def test_feedback_callback_rejected(bot_db):
    user = User(tg_id="12345", username="testuser")
    bot_db.add(user)
    bot_db.flush()
    user_id = user.id

    topic = TopicBranch(name="Тема", user_id=user_id)
    bot_db.add(topic)
    bot_db.flush()
    topic_id = topic.id

    article = Article(source_id=1, link="http://test.com", title="Test")
    bot_db.add(article)
    bot_db.flush()
    article_id = article.id

    ca = ClassifiedArticle(article_id=article_id, topic_branch_id=topic_id, matched=True)
    bot_db.add(ca)
    bot_db.commit()
    ca_id = ca.id

    callback_query = MagicMock()
    callback_query.data = f"feedback:{ca_id}:0"
    callback_query.from_user = _mock_telegram_user()
    callback_query.answer = AsyncMock(return_value=None)

    update = _mock_update(callback_query=callback_query)
    context = _mock_context()

    with patch("app.bot.notifier.SessionLocal", return_value=bot_db):
        await feedback_callback_handler(update, context)

    feedback = bot_db.query(Feedback).filter(
        Feedback.classified_article_id == ca_id,
        Feedback.approved == False,
    ).first()
    assert feedback is not None


@pytest.mark.asyncio
async def test_feedback_callback_invalid_data():
    callback_query = MagicMock()
    callback_query.data = "invalid:data"
    callback_query.from_user = _mock_telegram_user()
    callback_query.answer = AsyncMock(return_value=None)

    update = _mock_update(callback_query=callback_query)
    context = _mock_context()

    await feedback_callback_handler(update, context)
    callback_query.answer.assert_called()


@pytest.mark.asyncio
async def test_feedback_callback_no_user(bot_db):
    # tg_id not in DB
    callback_query = MagicMock()
    callback_query.data = "feedback:1:1"
    callback_query.from_user = _mock_telegram_user(tg_id=99999)
    callback_query.answer = AsyncMock(return_value=None)

    update = _mock_update(callback_query=callback_query)
    context = _mock_context()

    await feedback_callback_handler(update, context)
    callback_query.answer.assert_called_with("❌ Ошибка")


def test_record_feedback_success(bot_db):
    user = User(tg_id="12345", username="testuser")
    bot_db.add(user)
    bot_db.flush()
    user_id = user.id

    topic = TopicBranch(name="Тема", user_id=user_id)
    bot_db.add(topic)
    bot_db.flush()
    topic_id = topic.id

    article = Article(source_id=1, link="http://test.com", title="Test")
    bot_db.add(article)
    bot_db.flush()
    article_id = article.id

    ca = ClassifiedArticle(article_id=article_id, topic_branch_id=topic_id, matched=True)
    bot_db.add(ca)
    bot_db.commit()
    ca_id = ca.id

    class FakeSession:
        def __init__(self):
            self._closed = False
        def query(self, model):
            return bot_db.query(model)
        def add(self, obj):
            bot_db.add(obj)
        def commit(self):
            bot_db.commit()
        def rollback(self):
            bot_db.rollback()
        def close(self):
            self._closed = True

    with patch("app.bot.notifier.SessionLocal", return_value=FakeSession()):
        result = record_feedback("12345", ca_id, True)
    assert result is True

    feedback = bot_db.query(Feedback).first()
    assert feedback is not None
    assert feedback.approved is True


def test_record_feedback_user_not_found(bot_db):
    class FakeSession:
        def query(self, model):
            return bot_db.query(model)
        def add(self, obj):
            bot_db.add(obj)
        def commit(self):
            bot_db.commit()
        def rollback(self):
            bot_db.rollback()
        def close(self):
            pass

    with patch("app.bot.notifier.SessionLocal", return_value=FakeSession()):
        result = record_feedback("nonexistent", 1, True)
    assert result is False


def test_record_feedback_article_not_found(bot_db):
    user = User(tg_id="12345", username="testuser")
    bot_db.add(user)
    bot_db.commit()

    class FakeSession:
        def query(self, model):
            return bot_db.query(model)
        def add(self, obj):
            bot_db.add(obj)
        def commit(self):
            bot_db.commit()
        def rollback(self):
            bot_db.rollback()
        def close(self):
            pass

    with patch("app.bot.notifier.SessionLocal", return_value=FakeSession()):
        result = record_feedback("12345", 9999, True)
    assert result is False
