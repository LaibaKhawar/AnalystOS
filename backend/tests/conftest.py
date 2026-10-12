"""Shared fixtures. Tests run against a real PostgreSQL (pgvector) database: TEST_DATABASE_URL."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

from cryptography.fernet import Fernet

_TMP = Path(tempfile.mkdtemp(prefix="analystos-tests-"))
os.environ.setdefault("TEST_DATABASE_URL", "postgresql+psycopg://analystos:analystos@localhost:5434/analystos_test")
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["ENVIRONMENT"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-0123456789abcdef"
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["DATA_DIR"] = str(_TMP / "data")
os.environ["LOG_JSON"] = "false"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["EMBEDDING_BASE_URL"] = ""
os.environ["SANDBOX_TIMEOUT_SECONDS"] = "8"

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_engine, get_session_factory  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "evals" / "data"


@pytest.fixture(scope="session", autouse=True)
def _database() -> Iterator[None]:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture
def db() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
        with get_engine().begin() as conn:
            conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def settings():  # type: ignore[no-untyped-def]
    return get_settings()


@pytest.fixture
def data_dir() -> Path:
    return DATA


def docker_available() -> bool:
    try:
        from app.services.sandbox.docker_runner import DockerSandbox

        return DockerSandbox().available()[0]
    except Exception:
        return False
