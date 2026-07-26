from app.routers.sources import router as sources_router
from app.routers.topics import router as topics_router
from app.routers.articles import router as articles_router
from app.routers.feedback import router as feedback_router

__all__ = ["sources_router", "topics_router", "articles_router", "feedback_router"]
