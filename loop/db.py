"""Database engine, session factory, and the declarative Base.

One database, not a database plus a bolted-on vector store: vectors live in
pgvector alongside everything else (see README > Embed and cluster).
"""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from loop.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.postgres_dsn,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope: commit on success, roll back on error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency — yields a session, always closes it."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
