from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import db as db_module
from app.db import Base, get_db
from app.main import app


# Shared in-memory SQLite URI so all connections see the same DB
TEST_DB_URL = "sqlite:///file::memory:?cache=shared"


@pytest.fixture
def test_db():
    """Shared in-memory SQLite for all test connections."""
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

        app.dependency_overrides[get_db] = override_get_db
        yield test_engine
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


@pytest.fixture
def client(test_db):
    with TestClient(app) as c:
        yield c
