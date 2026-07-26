import asyncio
import logging
import threading

from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from app.config import settings
from app.bot.handlers import (
    start_handler,
    topics_handler,
    add_topic_handler,
    del_topic_handler,
    articles_handler,
    feed_handler,
    feedback_callback_handler,
)

logger = logging.getLogger(__name__)

_application: Application | None = None
_thread: threading.Thread | None = None


def _build_application() -> Application:
    """Build and configure the Telegram bot application."""
    app = (
        Application.builder()
        .token(settings.tg_bot_token)
        .build()
    )

    # Command handlers
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("topics", topics_handler))
    app.add_handler(CommandHandler("add_topic", add_topic_handler))
    app.add_handler(CommandHandler("del_topic", del_topic_handler))
    app.add_handler(CommandHandler("articles", articles_handler))
    app.add_handler(CommandHandler("feed", feed_handler))

    # Callback handlers (inline buttons)
    app.add_handler(CallbackQueryHandler(feedback_callback_handler, pattern=r"^feedback:"))

    return app


def start_bot() -> None:
    """Start the Telegram bot in a background thread."""
    global _application, _thread

    if not settings.tg_bot_token:
        logger.warning("TG_BOT_TOKEN not set — Telegram bot disabled")
        return

    if _application and _thread and _thread.is_alive():
        logger.info("Telegram bot already running")
        return

    _application = _build_application()

    async def _async_run() -> None:
        drop_pending = True
        while True:
            try:
                await _application.initialize()
                await _application.start()
                logger.info("Starting Telegram bot polling...")
                await _application.updater.start_polling(  # type: ignore[union-attr]
                    drop_pending_updates=drop_pending,
                    timeout=30,
                )
            except Exception as e:
                logger.warning(f"Bot polling lost ({e}), reconnecting in 5s...")
                drop_pending = False
            finally:
                try:
                    await _application.updater.stop()  # type: ignore[union-attr]
                    await _application.stop()  # type: ignore[misc]
                    await _application.shutdown()  # type: ignore[misc]
                except Exception:
                    pass
                await asyncio.sleep(5)

    def _run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_async_run())
        except Exception as e:
            logger.error(f"Telegram bot error: {e}")
        finally:
            try:
                loop.run_until_complete(_application.shutdown())  # type: ignore[misc]
            except Exception:
                pass
            loop.close()

    _thread = threading.Thread(target=_run, daemon=True, name="tg-bot")
    _thread.start()
    logger.info("Telegram bot started")


def get_bot():
    """Get the Telegram Bot instance (for use by the scheduler notifier)."""
    if _application:
        return _application.bot
    return None


async def stop_bot() -> None:
    """Shutdown the Telegram bot."""
    global _application

    if _application:
        try:
            await _application.stop()  # type: ignore[misc]
            await _application.shutdown()  # type: ignore[misc]
            logger.info("Telegram bot stopped")
        except Exception as e:
            logger.error(f"Error stopping Telegram bot: {e}")
