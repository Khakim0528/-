from collections.abc import Iterator

from sqlalchemy import create_engine, event, inspect, text
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
# pool_pre_ping: check a pooled connection is alive before using it, and transparently
# reconnect if not. Without this, a connection Neon dropped while idle (it does this
# on its free tier) surfaces as a random OperationalError on the next request.
engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
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


def run_light_migrations() -> None:
    """`Base.metadata.create_all()` only creates brand-new tables — it won't add a
    column to a `users` table that already has rows from before that column existed
    (e.g. on Render/Neon after this update shipped). Add it by hand if missing.

    New signups get `email_verified=False` explicitly from the ORM regardless of this
    column default (registration always sets it). The default here only backfills
    *existing* rows, so accounts created before this feature shipped — including the
    admin account — aren't retroactively locked out; only genuinely new registrations
    go through the code flow."""
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("users")}
    if "email_verified" in columns:
        return
    default = "1" if is_sqlite else "TRUE"
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT {default}"))
