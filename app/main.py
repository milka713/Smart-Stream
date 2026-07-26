from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Smart Stream", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}
