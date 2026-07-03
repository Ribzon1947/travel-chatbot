from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Place(Base):
    __tablename__ = "places"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False, index=True)
    routes = relationship("RoutePricing", back_populates="place", cascade="all, delete-orphan")


class Destination(Base):
    __tablename__ = "destinations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False, index=True)
    routes = relationship("RoutePricing", back_populates="destination", cascade="all, delete-orphan")


class RoutePricing(Base):
    __tablename__ = "route_pricing"

    id = Column(Integer, primary_key=True, index=True)
    place_id = Column(Integer, ForeignKey("places.id"), nullable=False, index=True)
    destination_id = Column(Integer, ForeignKey("destinations.id"), nullable=False, index=True)
    hotel_cost_enc = Column(LargeBinary, nullable=False)
    people_per_room_enc = Column(LargeBinary, nullable=False)
    cab_cost_enc = Column(LargeBinary, nullable=False)
    meal_cost_enc = Column(LargeBinary, nullable=False)
    ticket_cost_enc = Column(LargeBinary, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    place = relationship("Place", back_populates="routes")
    destination = relationship("Destination", back_populates="routes")

    __table_args__ = (
        UniqueConstraint("place_id", "destination_id", name="uq_place_destination"),
    )
