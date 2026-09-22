from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


def _normalize_url(url: str) -> str:
    """Accept a plain 'postgres://' / 'postgresql://' URL (what Neon, Render, etc.
    hand you) and route it through the psycopg (v3) driver we actually installed."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


database_url = _normalize_url(settings.database_url)
is_sqlite = database_url.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}
engine = create_engine(database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

if is_sqlite:
    # SQLite's built-in lower()/LIKE only case-fold ASCII, so ILIKE search would
    # miss non-Latin text (e.g. Cyrillic "Вода" wouldn't match "вода"). Replace
    # lower() with Python's Unicode-aware version on every new connection.
    @event.listens_for(engine, "connect")
    def _register_unicode_lower(dbapi_connection, _record):
        dbapi_connection.create_function("lower", 1, lambda s: s.lower() if s is not None else None)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
