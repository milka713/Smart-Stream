import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import User
from app.db import SessionLocal


def _ensure_user() -> int:
    """Create a default test user if not exists."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.tg_id == "test_topic").first()
        if not user:
            user = User(tg_id="test_topic", username="test")
            db.add(user)
            db.flush()
        return user.id
    finally:
        db.close()


def test_create_topic(client):
    user_id = _ensure_user()
    resp = client.post("/topics/", json={
        "name": "Space News",
        "user_id": user_id,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Space News"
    assert data["active"] is True


def test_list_topics(client):
    user_id = _ensure_user()
    client.post("/topics/", json={"name": "Topic A", "user_id": user_id})
    client.post("/topics/", json={"name": "Topic B", "user_id": user_id})

    resp = client.get(f"/topics/?user_id={user_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2


def test_delete_topic(client):
    user_id = _ensure_user()
    created = client.post("/topics/", json={"name": "To Delete", "user_id": user_id}).json()
    topic_id = created["id"]

    resp = client.delete(f"/topics/{topic_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


def test_delete_topic_not_found(client):
    resp = client.delete("/topics/99999")
    assert resp.status_code == 404
