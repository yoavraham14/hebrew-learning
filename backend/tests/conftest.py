import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  — registers all tables on Base.metadata
from app.db import Base, get_db
from app.main import app


@pytest.fixture()
def test_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session(test_engine):
    session_local = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, future=True)
    session = session_local()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(test_engine):
    session_local = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, future=True)

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # No `with` block: this deliberately skips FastAPI's lifespan (startup/
    # shutdown) handlers, so the real bootstrap-generation-on-empty-bank
    # and the APScheduler top-up job never run against a real Postgres
    # during tests — only the SQLite test DB via the override above.
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()
