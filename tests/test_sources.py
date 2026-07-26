import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models import User, Source
from app.db import get_db, SessionLocal as RealSessionLocal


@pytest.fixture
def db_session():
    """Provide a real DB session for test setup."""
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _setup_user(db: Session) -> User:
    user = User(tg_id="test_src", username="test")
    db.add(user)
    db.flush()
    return user


def test_create_source(client):
    resp = client.post("/sources/", json={
        "url": "https://example.com/feed.xml",
        "name": "Test Feed",
        "interval_min": 10,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["url"] == "https://example.com/feed.xml"
    assert data["name"] == "Test Feed"
    assert data["active"] is True


def test_create_source_defaults(client):
    resp = client.post("/sources/", json={
        "url": "https://example.com/rss",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["interval_min"] == 15
    assert data["name"] is None


def test_list_sources(client):
    # Create two sources
    client.post("/sources/", json={"url": "https://a.com/feed", "name": "A"})
    client.post("/sources/", json={"url": "https://b.com/feed", "name": "B"})

    resp = client.get("/sources/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2


def test_delete_source(client):
    created = client.post("/sources/", json={"url": "https://del.com/feed"}).json()
    source_id = created["id"]

    resp = client.delete(f"/sources/{source_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    # Verify it's gone
    resp = client.get("/sources/")
    urls = [s["url"] for s in resp.json()]
    assert "https://del.com/feed" not in urls


def test_delete_source_not_found(client):
    resp = client.delete("/sources/99999")
    assert resp.status_code == 404
