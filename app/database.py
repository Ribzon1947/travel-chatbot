"""
SQLAlchemy database engine and session.
The relational schema is defined in SQL under the root `database/` project.
"""
import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

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
        if _DB_URL.startswith("sqlite"):
            conn.exec_driver_sql(sql_text)
        else:
            for statement in [s.strip() for s in sql_text.split(";") if s.strip()]:
                conn.execute(text(statement))
