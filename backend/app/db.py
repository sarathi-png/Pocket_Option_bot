"""Database engine/session (PRD §7.7). SQLite by default; set DATABASE_URL for PostgreSQL."""
from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    url = get_settings().database_url
    connect_args: dict = {}
    engine_kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        if url in ("sqlite://", "sqlite:///:memory:"):
            # In-memory DB (tests): share ONE connection across sessions,
            # otherwise each connection sees an empty database.
            engine_kwargs["poolclass"] = StaticPool
            engine_kwargs.pop("pool_pre_ping")
        else:
            # Ensure the SQLite directory exists (e.g. ./data/signals.db)
            path = url.split("sqlite:///", 1)[-1] if "sqlite:///" in url else ""
            if path and path != ":memory:":
                directory = os.path.dirname(path)
                if directory:
                    os.makedirs(directory, exist_ok=True)
    return create_engine(url, connect_args=connect_args, **engine_kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    from app import models  # noqa: F401  (register models)

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
