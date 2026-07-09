"""
SQLAlchemy database engine and session.
The relational schema is defined in SQL under the root `database/` project.
"""
import os
import logging
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)

_DB_URL = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{Path(__file__).parent.parent / 'chatbot.db'}"
)

_connect_args = {"check_same_thread": False} if _DB_URL.startswith("sqlite") else {}
engine = create_engine(_DB_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Initialize the database schema from the SQL project."""
    schema_path = Path(__file__).resolve().parents[1] / "database" / "schema.sql"
    if not schema_path.exists():
        raise FileNotFoundError(f"Could not find database schema: {schema_path}")

    sql_text = schema_path.read_text(encoding="utf-8")
    with engine.begin() as conn:
        for statement in [s.strip() for s in sql_text.split(";") if s.strip()]:
            if _DB_URL.startswith("sqlite"):
                conn.exec_driver_sql(statement)
            else:
                conn.execute(text(statement))

    migrate_schema()


# ── Lightweight migrations for columns added after initial schema.sql ────────
#
# schema.sql handles brand-new databases (CREATE TABLE IF NOT EXISTS), but it
# does NOT retroactively add columns to tables that already exist. Each entry
# below is a column that was added to a model after the table was first
# created. Adding a new entry here is safe to run repeatedly -- SQLite errors
# on a duplicate column, which we catch and ignore.
_PENDING_COLUMN_MIGRATIONS = [
    ("hotel_listings", "phone", "VARCHAR(50)"),
    # Add future new columns here as: ("table_name", "column_name", "SQL_TYPE"),
]


def migrate_schema() -> None:
    """Apply any pending ALTER TABLE ADD COLUMN migrations, safely and idempotently."""
    with engine.begin() as conn:
        for table, column, col_type in _PENDING_COLUMN_MIGRATIONS:
            try:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                logger.info("Migration applied: added %s.%s", table, column)
            except OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    pass  # already applied -- expected on every run after the first
                else:
                    logger.error("Migration failed for %s.%s: %s", table, column, e)
                    raise