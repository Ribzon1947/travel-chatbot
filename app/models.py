from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, LargeBinary, String, UniqueConstraint, Text, Boolean, REAL, Date
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


# ─── Core Location & Pricing Models ─────────────────────────────────────────

class Place(Base):
    __tablename__ = "places"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    latitude = Column(REAL, nullable=True)
    longitude = Column(REAL, nullable=True)
    country = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    routes = relationship("RoutePricing", back_populates="place", cascade="all, delete-orphan")


class Destination(Base):
    __tablename__ = "destinations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    latitude = Column(REAL, nullable=True)
    longitude = Column(REAL, nullable=True)
    country = Column(String(128), nullable=True)
    region = Column(String(128), nullable=True)
    best_season = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    routes = relationship("RoutePricing", back_populates="destination", cascade="all, delete-orphan")
    popularity = relationship("DestinationPopularity", back_populates="destination", uselist=False, cascade="all, delete-orphan")


class RoutePricing(Base):
    __tablename__ = "route_pricing"

    id = Column(Integer, primary_key=True, index=True)
    place_id = Column(Integer, ForeignKey("places.id", ondelete="CASCADE"), nullable=False, index=True)
    destination_id = Column(Integer, ForeignKey("destinations.id", ondelete="CASCADE"), nullable=False, index=True)
    hotel_cost_enc = Column(LargeBinary, nullable=False)
    people_per_room_enc = Column(LargeBinary, nullable=False)
    cab_cost_enc = Column(LargeBinary, nullable=False)
    meal_cost_enc = Column(LargeBinary, nullable=False)
    ticket_cost_enc = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    place = relationship("Place", back_populates="routes")
    destination = relationship("Destination", back_populates="routes")
    history = relationship("PricingHistory", back_populates="route_pricing", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("place_id", "destination_id", name="uq_place_destination"),
    )


# ─── User Management Models ──────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(255), unique=True, nullable=False)
    email = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True)
    name = Column(String(128), nullable=True)
    preferences = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user")
    api_requests = relationship("ApiRequest", back_populates="user")
    error_logs = relationship("ErrorLog", back_populates="user")


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_token = Column(String(255), unique=True, nullable=False)
    from_location = Column(String(128), nullable=True)
    to_location = Column(String(128), nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    
    user = relationship("User", back_populates="sessions")
    conversations = relationship("ChatConversation", back_populates="session", cascade="all, delete-orphan")
    trip_calculations = relationship("TripCalculation", back_populates="session", cascade="all, delete-orphan")


# ─── Chat History Models ─────────────────────────────────────────────────────

class ChatConversation(Base):
    __tablename__ = "chat_conversations"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_title = Column(String(255), nullable=True)
    message_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    session = relationship("Session", back_populates="conversations")
    messages = relationship("ChatMessage", back_populates="conversation", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_role = Column(String(20), nullable=False)
    message_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    conversation = relationship("ChatConversation", back_populates="messages")


# ─── Trip Calculation History Model ──────────────────────────────────────────

class TripCalculation(Base):
    __tablename__ = "trip_calculations"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    calculation_type = Column(String(50), nullable=False, index=True)
    num_people = Column(Integer, nullable=True)
    kids_under_7 = Column(Integer, default=0)
    num_days = Column(Integer, nullable=True)
    num_nights = Column(Integer, nullable=True)
    origin = Column(String(128), nullable=True)
    destination = Column(String(128), nullable=True)
    destinations_list = Column(Text, nullable=True)
    itinerary = Column(Text, nullable=True)
    grand_total = Column(Integer, nullable=True)
    calculation_data = Column(Text, nullable=True)
    calculated_at = Column(DateTime, default=datetime.utcnow)
    
    session = relationship("Session", back_populates="trip_calculations")


# ─── Audit & Logging Models ──────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(50), nullable=True)
    entity_id = Column(Integer, nullable=True)
    old_values = Column(Text, nullable=True)
    new_values = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    
    user = relationship("User", back_populates="audit_logs")


class ApiRequest(Base):
    __tablename__ = "api_requests"

    id = Column(Integer, primary_key=True, index=True)
    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    request_body = Column(Text, nullable=True)
    response_status = Column(Integer, nullable=True)
    response_time_ms = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    user = relationship("User", back_populates="api_requests")


class ErrorLog(Base):
    __tablename__ = "error_logs"

    id = Column(Integer, primary_key=True, index=True)
    error_type = Column(String(100), nullable=False)
    error_message = Column(Text, nullable=False)
    stack_trace = Column(Text, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    endpoint = Column(String(255), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    user = relationship("User", back_populates="error_logs")


# ─── Pricing History & Versioning Models ────────────────────────────────────

class PricingHistory(Base):
    __tablename__ = "pricing_history"

    id = Column(Integer, primary_key=True, index=True)
    route_pricing_id = Column(Integer, ForeignKey("route_pricing.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    hotel_cost_enc = Column(LargeBinary, nullable=False)
    people_per_room_enc = Column(LargeBinary, nullable=False)
    cab_cost_enc = Column(LargeBinary, nullable=False)
    meal_cost_enc = Column(LargeBinary, nullable=False)
    ticket_cost_enc = Column(LargeBinary, nullable=False)
    changed_by = Column(String(128), nullable=True)
    changed_at = Column(DateTime, default=datetime.utcnow)
    change_reason = Column(Text, nullable=True)
    
    route_pricing = relationship("RoutePricing", back_populates="history")


# ─── Analytics & Aggregation Models ──────────────────────────────────────────

class DailyAnalytics(Base):
    __tablename__ = "daily_analytics"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, unique=True, nullable=False)
    total_users = Column(Integer, default=0)
    active_sessions = Column(Integer, default=0)
    total_calculations = Column(Integer, default=0)
    total_revenue = Column(Integer, default=0)
    avg_trip_cost = Column(Integer, default=0)
    popular_destination = Column(String(128), nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow)


class DestinationPopularity(Base):
    __tablename__ = "destination_popularity"

    id = Column(Integer, primary_key=True, index=True)
    destination_id = Column(Integer, ForeignKey("destinations.id", ondelete="CASCADE"), nullable=False, index=True)
    query_count = Column(Integer, default=0)
    booking_count = Column(Integer, default=0)
    avg_rating = Column(REAL, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow)
    
    destination = relationship("Destination", back_populates="popularity")
