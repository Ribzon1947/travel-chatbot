"""
User and session management layer for the chatbot.
Handles user creation, session tracking, and conversation history.
"""
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import User, Session as DBSession, ChatConversation, ChatMessage, TripCalculation

logger = logging.getLogger(__name__)


# ─── User Management ─────────────────────────────────────────────────────────

def get_or_create_user(session: Session, user_id: str, email: str = None, name: str = None) -> User:
    """Get existing user or create a new one."""
    user = session.query(User).filter(User.user_id == user_id).first()
    if user is None:
        user = User(
            user_id=user_id,
            email=email,
            name=name,
            preferences="{}"
        )
        session.add(user)
        session.flush()
        logger.info(f"Created new user: {user_id}")
    return user


def update_user_activity(user_id: str) -> None:
    """Update user's last_active timestamp."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if user:
            user.last_active = datetime.utcnow()
            db.commit()
    except Exception as e:
        logger.error(f"Error updating user activity: {e}")
        db.rollback()
    finally:
        db.close()


def get_user_by_id(user_id: str) -> Optional[User]:
    """Retrieve a user by their user_id."""
    db = SessionLocal()
    try:
        return db.query(User).filter(User.user_id == user_id).first()
    finally:
        db.close()


# ─── Session Management ──────────────────────────────────────────────────────

def create_session(user_id: str, from_location: str = None, to_location: str = None) -> str:
    """Create a new session for a user."""
    db = SessionLocal()
    try:
        user = get_or_create_user(db, user_id)
        session_token = str(uuid.uuid4())
        
        session = DBSession(
            user_id=user.id,
            session_token=session_token,
            from_location=from_location,
            to_location=to_location,
            is_active=True
        )
        db.add(session)
        db.commit()
        logger.info(f"Created session {session_token} for user {user_id}")
        return session_token
    except Exception as e:
        logger.error(f"Error creating session: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def end_session(session_token: str) -> None:
    """End an active session."""
    db = SessionLocal()
    try:
        session = db.query(DBSession).filter(DBSession.session_token == session_token).first()
        if session:
            session.ended_at = datetime.utcnow()
            session.is_active = False
            session.duration_seconds = int((session.ended_at - session.started_at).total_seconds())
            db.commit()
            logger.info(f"Ended session {session_token}")
    except Exception as e:
        logger.error(f"Error ending session: {e}")
        db.rollback()
    finally:
        db.close()


def get_session(session_token: str) -> Optional[DBSession]:
    """Retrieve a session by token."""
    db = SessionLocal()
    try:
        return db.query(DBSession).filter(DBSession.session_token == session_token).first()
    finally:
        db.close()


def get_user_sessions(user_id: str, limit: int = 10) -> list:
    """Get recent sessions for a user."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if user:
            return db.query(DBSession).filter(
                DBSession.user_id == user.id
            ).order_by(DBSession.started_at.desc()).limit(limit).all()
        return []
    finally:
        db.close()


# ─── Chat Conversation Management ────────────────────────────────────────────

def create_conversation(session_token: str, title: str = None) -> Optional[int]:
    """Create a new chat conversation within a session."""
    db = SessionLocal()
    try:
        session = db.query(DBSession).filter(DBSession.session_token == session_token).first()
        if not session:
            logger.warning(f"Session not found: {session_token}")
            return None
        
        conversation = ChatConversation(
            session_id=session.id,
            conversation_title=title or f"Conversation {datetime.utcnow().isoformat()}",
            message_count=0
        )
        db.add(conversation)
        db.commit()
        logger.info(f"Created conversation {conversation.id} in session {session_token}")
        return conversation.id
    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def add_message(conversation_id: int, sender_role: str, message_text: str) -> Optional[int]:
    """Add a message to a conversation."""
    db = SessionLocal()
    try:
        conversation = db.query(ChatConversation).filter(ChatConversation.id == conversation_id).first()
        if not conversation:
            logger.warning(f"Conversation not found: {conversation_id}")
            return None
        
        message = ChatMessage(
            conversation_id=conversation_id,
            sender_role=sender_role,
            message_text=message_text
        )
        db.add(message)
        conversation.message_count += 1
        conversation.updated_at = datetime.utcnow()
        db.commit()
        return message.id
    except Exception as e:
        logger.error(f"Error adding message: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def get_conversation_history(conversation_id: int) -> list:
    """Retrieve all messages in a conversation."""
    db = SessionLocal()
    try:
        return db.query(ChatMessage).filter(
            ChatMessage.conversation_id == conversation_id
        ).order_by(ChatMessage.created_at).all()
    finally:
        db.close()


def get_session_conversations(session_token: str) -> list:
    """Get all conversations in a session."""
    db = SessionLocal()
    try:
        session = db.query(DBSession).filter(DBSession.session_token == session_token).first()
        if session:
            return db.query(ChatConversation).filter(
                ChatConversation.session_id == session.id
            ).order_by(ChatConversation.created_at.desc()).all()
        return []
    finally:
        db.close()


# ─── Trip Calculation History ────────────────────────────────────────────────

def record_trip_calculation(
    session_token: str,
    calculation_type: str,
    calculation_data: dict
) -> Optional[int]:
    """Record a trip calculation for later reference."""
    db = SessionLocal()
    try:
        session = db.query(DBSession).filter(DBSession.session_token == session_token).first()
        if not session:
            logger.warning(f"Session not found: {session_token}")
            return None
        
        import json
        trip_calc = TripCalculation(
            session_id=session.id,
            calculation_type=calculation_type,
            num_people=calculation_data.get("num_people"),
            kids_under_7=calculation_data.get("kids_under_7", 0),
            num_days=calculation_data.get("num_days"),
            num_nights=calculation_data.get("num_nights"),
            origin=calculation_data.get("origin"),
            destination=calculation_data.get("destination"),
            destinations_list=json.dumps(calculation_data.get("destinations_list", [])),
            itinerary=json.dumps(calculation_data.get("itinerary", [])),
            grand_total=calculation_data.get("grand_total"),
            calculation_data=json.dumps(calculation_data)
        )
        db.add(trip_calc)
        db.commit()
        return trip_calc.id
    except Exception as e:
        logger.error(f"Error recording trip calculation: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def get_session_calculations(session_token: str) -> list:
    """Get all trip calculations in a session."""
    db = SessionLocal()
    try:
        session = db.query(DBSession).filter(DBSession.session_token == session_token).first()
        if session:
            return db.query(TripCalculation).filter(
                TripCalculation.session_id == session.id
            ).order_by(TripCalculation.calculated_at.desc()).all()
        return []
    finally:
        db.close()


# ─── Session Statistics ──────────────────────────────────────────────────────

def get_user_statistics(user_id: str) -> dict:
    """Get statistics for a user."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            return {}
        
        total_sessions = db.query(DBSession).filter(DBSession.user_id == user.id).count()
        active_sessions = db.query(DBSession).filter(
            DBSession.user_id == user.id,
            DBSession.is_active == True
        ).count()
        total_messages = db.query(ChatMessage).join(ChatConversation).join(DBSession).filter(
            DBSession.user_id == user.id
        ).count()
        total_calculations = db.query(TripCalculation).join(DBSession).filter(
            DBSession.user_id == user.id
        ).count()
        
        return {
            "user_id": user_id,
            "name": user.name,
            "email": user.email,
            "created_at": user.created_at,
            "last_active": user.last_active,
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "total_messages": total_messages,
            "total_calculations": total_calculations
        }
    finally:
        db.close()
