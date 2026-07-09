"""Shared pytest setup for CI.

Important:
- Keeps provider calls offline by default.
- Uses memory cache for FastAPI startup unless a test explicitly checks Redis.
- Uses the PostgreSQL/pgvector sidecar from GitHub Actions for integration tests.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make `backend.*` and `module.*` imports work on GitHub runners.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Safe defaults for tests. Real secrets are never required for CI.
os.environ.setdefault("CACHE_BACKEND", "memory")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/postgres")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("REDIS_DB", "1")
os.environ.setdefault("GEMINI_API_KEY", "")
os.environ.setdefault("SARVAM_API_KEY", "")
os.environ.setdefault("CARTESIA_API_KEY", "")
os.environ.setdefault("DEEPGRAM_API_KEY", "")
os.environ.setdefault("AIC_SDK_LICENSE", "")

import pytest
from sqlalchemy import text


@pytest.fixture(scope="session")
def db_schema():
    """Create a clean PostgreSQL/pgvector schema for integration tests."""
    database_url = os.getenv("DATABASE_URL", "")
    is_safe_db = (
        "test" in database_url.lower()
        or "ci" in database_url.lower()
        or os.getenv("CI", "").lower() == "true"
    )
    if not is_safe_db:
        raise RuntimeError(
            "Refusing to run destructive integration DB cleanup. "
            "Use a test/CI database only, for example app_test_db."
        )

    from backend.database import Base, engine
    import backend.models.agent  # noqa: F401
    import backend.models.kb  # noqa: F401

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        # Clean test DB safely. SQLAlchemy drop_all can fail when old FK tables exist.
        # This is ONLY for CI/test database, never production.
        conn.execute(text("""
        DO $$
        DECLARE
            r RECORD;
        BEGIN
            FOR r IN (
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
            ) LOOP
                EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
            END LOOP;
        END $$;
        """))

        Base.metadata.create_all(bind=conn)

    yield

    with engine.begin() as conn:
        Base.metadata.drop_all(bind=conn)


@pytest.fixture()
def db_session(db_schema):
    """Fresh SQLAlchemy session with table cleanup between API tests."""
    from backend.database import SessionLocal
    from backend.models.agent import Agent
    from backend.models.kb import KBChunk

    db = SessionLocal()
    try:
        db.query(KBChunk).delete()
        db.query(Agent).delete()
        db.commit()
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture()
def app_client(db_session):
    """FastAPI TestClient backed by the test database."""
    from fastapi.testclient import TestClient
    from backend.main import app

    with TestClient(app) as client:
        yield client