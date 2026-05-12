from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from research_radar.config import Settings, get_settings
from research_radar.models import Base


def _sqlite_path(database_url: str) -> Path | None:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return None
    raw_path = database_url.removeprefix(prefix)
    if raw_path in (":memory:", ""):
        return None
    return Path(raw_path)


def make_engine(settings: Settings | None = None) -> Engine:
    settings = settings or get_settings()
    sqlite_path = _sqlite_path(settings.database_url)
    if sqlite_path is not None:
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    connect_args = (
        {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    )
    return create_engine(settings.database_url, connect_args=connect_args, future=True)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db(session_engine: Engine | None = None) -> None:
    Base.metadata.create_all(bind=session_engine or engine)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
