import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import Base, engine
from app.routers import (
    sources_router,
    topics_router,
    articles_router,
    feedback_router,
)
from app.scheduler import start_scheduler, stop_scheduler
from app.services.llm import LLMGateway

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Smart Stream", lifespan=lifespan)
app.include_router(sources_router)
app.include_router(topics_router)
app.include_router(articles_router)
app.include_router(feedback_router)


@app.get("/health")
async def health():
    llm_healthy = LLMGateway().health_check()
    return {
        "status": "ok",
        "llm": "ok" if llm_healthy else "unreachable",
    }
