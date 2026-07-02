"""
SQLAlchemy database setup.
Tables are created automatically on startup (self-compile = Base.metadata.create_all).
"""
import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import Column, Integer, String, LargeBinary, DateTime, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

_DB_URL = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{Path(__file__).parent.parent / 'chatbot.db'}"
)

_connect_args = {"check_same_thread": False} if _DB_URL.startswith("sqlite") else {}
engine = create_engine(_DB_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class DestinationRow(Base):
    """One row per travel destination; pricing fields stored as FHE ciphertext."""
    __tablename__ = "destinations"

    id                  = Column(Integer, primary_key=True, index=True)
    name                = Column(String(128), unique=True, nullable=False, index=True)
    hotel_cost_enc      = Column(LargeBinary, nullable=False)
    people_per_room_enc = Column(LargeBinary, nullable=False)
    cab_cost_enc        = Column(LargeBinary, nullable=False)
    meal_cost_enc       = Column(LargeBinary, nullable=False)
    ticket_cost_enc     = Column(LargeBinary, nullable=False)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def init_db() -> None:
    """Create all tables that do not yet exist (idempotent, safe to call on every startup)."""
    Base.metadata.create_all(bind=engine)
