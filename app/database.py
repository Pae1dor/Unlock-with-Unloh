"""SQLAlchemy engine / session setup.

DATABASE_URL works with both PostgreSQL (psycopg2) and SQLite. No Postgres-only
column types are used anywhere in models.py, so SQLite is a drop-in alternative.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    # FastAPI may touch the session from different threads.
    connect_args["check_same_thread"] = False

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401  (register mappers before create_all)

    Base.metadata.create_all(engine)
    _add_missing_columns()


# Columns added to tables that already existed. create_all only creates missing *tables*,
# so these are added here once, on startup (plain ADD COLUMN works on SQLite and PostgreSQL).
_ADDED_COLUMNS = {
    "mail": {"gift_background_key": "VARCHAR(40)"},
}


def _add_missing_columns() -> None:
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if not inspector.has_table(table):
                continue
            have = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
