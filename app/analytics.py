"""
Analytics and reporting layer for the chatbot.
Handles audit logs, API tracking, error logging, and analytics aggregation.
"""
import logging
import json
from datetime import datetime, date
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import AuditLog, ApiRequest, ErrorLog, DailyAnalytics, DestinationPopularity, Destination

logger = logging.getLogger(__name__)


# ─── Audit Logging ──────────────────────────────────────────────────────────

def log_audit_event(
    user_id: Optional[str],
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    old_values: Optional[Dict] = None,
    new_values: Optional[Dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> None:
    """Log an audit event."""
    db = SessionLocal()
    try:
        from app.user_manager import get_or_create_user
        
        user_obj = None
        if user_id:
            user_obj = get_or_create_user(db, user_id)
        
        audit_log = AuditLog(
            user_id=user_obj.id if user_obj else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_values=json.dumps(old_values) if old_values else None,
            new_values=json.dumps(new_values) if new_values else None,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.add(audit_log)
        db.commit()
        logger.debug(f"Audit log: {action} by {user_id}")
    except Exception as e:
        logger.error(f"Error logging audit event: {e}")
        db.rollback()
    finally:
        db.close()


def get_audit_logs(
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 100
) -> list:
    """Retrieve audit logs with optional filters."""
    db = SessionLocal()
    try:
        query = db.query(AuditLog)
        
        if user_id:
            from app.user_manager import get_user_by_id
            user = get_user_by_id(user_id)
            if user:
                query = query.filter(AuditLog.user_id == user.id)
        
        if action:
            query = query.filter(AuditLog.action == action)
        
        return query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
    finally:
        db.close()


# ─── API Request Logging ────────────────────────────────────────────────────

def log_api_request(
    endpoint: str,
    method: str,
    user_id: Optional[str] = None,
    request_body: Optional[str] = None,
    response_status: Optional[int] = None,
    response_time_ms: Optional[int] = None
) -> None:
    """Log an API request."""
    db = SessionLocal()
    try:
        from app.user_manager import get_or_create_user
        
        user_obj = None
        if user_id:
            user_obj = get_or_create_user(db, user_id)
        
        api_req = ApiRequest(
            endpoint=endpoint,
            method=method,
            user_id=user_obj.id if user_obj else None,
            request_body=request_body,
            response_status=response_status,
            response_time_ms=response_time_ms
        )
        db.add(api_req)
        db.commit()
        logger.debug(f"API request: {method} {endpoint} ({response_status})")
    except Exception as e:
        logger.error(f"Error logging API request: {e}")
        db.rollback()
    finally:
        db.close()


def get_api_requests(
    endpoint: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = 100
) -> list:
    """Retrieve API request logs."""
    db = SessionLocal()
    try:
        query = db.query(ApiRequest)
        
        if endpoint:
            query = query.filter(ApiRequest.endpoint.like(f"%{endpoint}%"))
        
        if user_id:
            from app.user_manager import get_user_by_id
            user = get_user_by_id(user_id)
            if user:
                query = query.filter(ApiRequest.user_id == user.id)
        
        return query.order_by(ApiRequest.timestamp.desc()).limit(limit).all()
    finally:
        db.close()


# ─── Error Logging ──────────────────────────────────────────────────────────

def log_error(
    error_type: str,
    error_message: str,
    stack_trace: Optional[str] = None,
    user_id: Optional[str] = None,
    endpoint: Optional[str] = None
) -> None:
    """Log an error."""
    db = SessionLocal()
    try:
        from app.user_manager import get_or_create_user
        
        user_obj = None
        if user_id:
            user_obj = get_or_create_user(db, user_id)
        
        error_log = ErrorLog(
            error_type=error_type,
            error_message=error_message,
            stack_trace=stack_trace,
            user_id=user_obj.id if user_obj else None,
            endpoint=endpoint
        )
        db.add(error_log)
        db.commit()
        logger.error(f"Error logged: {error_type} - {error_message}")
    except Exception as e:
        logger.error(f"Error logging error: {e}")
        db.rollback()
    finally:
        db.close()


def get_error_logs(
    error_type: Optional[str] = None,
    limit: int = 100
) -> list:
    """Retrieve error logs."""
    db = SessionLocal()
    try:
        query = db.query(ErrorLog)
        
        if error_type:
            query = query.filter(ErrorLog.error_type == error_type)
        
        return query.order_by(ErrorLog.timestamp.desc()).limit(limit).all()
    finally:
        db.close()


# ─── Destination Popularity Tracking ────────────────────────────────────────

def increment_destination_query(destination_name: str) -> None:
    """Increment query count for a destination."""
    db = SessionLocal()
    try:
        dest = db.query(Destination).filter(Destination.name == destination_name).first()
        if dest:
            pop = db.query(DestinationPopularity).filter(
                DestinationPopularity.destination_id == dest.id
            ).first()
            if pop:
                pop.query_count += 1
                pop.last_updated = datetime.utcnow()
            else:
                pop = DestinationPopularity(
                    destination_id=dest.id,
                    query_count=1
                )
                db.add(pop)
            db.commit()
    except Exception as e:
        logger.error(f"Error incrementing destination query count: {e}")
        db.rollback()
    finally:
        db.close()


def increment_destination_booking(destination_name: str) -> None:
    """Increment booking count for a destination."""
    db = SessionLocal()
    try:
        dest = db.query(Destination).filter(Destination.name == destination_name).first()
        if dest:
            pop = db.query(DestinationPopularity).filter(
                DestinationPopularity.destination_id == dest.id
            ).first()
            if pop:
                pop.booking_count += 1
                pop.last_updated = datetime.utcnow()
            else:
                pop = DestinationPopularity(
                    destination_id=dest.id,
                    booking_count=1
                )
                db.add(pop)
            db.commit()
    except Exception as e:
        logger.error(f"Error incrementing destination booking count: {e}")
        db.rollback()
    finally:
        db.close()


def get_destination_popularity(limit: int = 10) -> list:
    """Get most popular destinations."""
    db = SessionLocal()
    try:
        return db.query(DestinationPopularity).order_by(
            DestinationPopularity.query_count.desc()
        ).limit(limit).all()
    finally:
        db.close()


# ─── Daily Analytics ────────────────────────────────────────────────────────

def update_daily_analytics(target_date: Optional[date] = None) -> None:
    """Update daily analytics for a given date."""
    db = SessionLocal()
    try:
        from app.user_manager import get_user_sessions
        from sqlalchemy import func
        
        if target_date is None:
            target_date = date.today()
        
        # Query data for the day
        from app.models import Session as DBSession
        
        total_users = db.query(func.count(func.distinct(DBSession.user_id))).filter(
            func.date(DBSession.started_at) == target_date
        ).scalar() or 0
        
        active_sessions = db.query(func.count(DBSession.id)).filter(
            func.date(DBSession.started_at) == target_date,
            DBSession.is_active == True
        ).scalar() or 0
        
        from app.models import TripCalculation
        total_calculations = db.query(func.count(TripCalculation.id)).filter(
            func.date(TripCalculation.calculated_at) == target_date
        ).scalar() or 0
        
        total_revenue = db.query(func.sum(TripCalculation.grand_total)).filter(
            func.date(TripCalculation.calculated_at) == target_date
        ).scalar() or 0
        
        avg_trip_cost = db.query(func.avg(TripCalculation.grand_total)).filter(
            func.date(TripCalculation.calculated_at) == target_date
        ).scalar() or 0
        
        # Get most popular destination for the day
        from app.models import ChatMessage, ChatConversation
        popular_dest = db.query(
            func.substr(ChatMessage.message_text, 1, 50)
        ).join(ChatConversation).filter(
            func.date(ChatMessage.created_at) == target_date
        ).limit(1).scalar()
        
        # Upsert daily analytics
        analytics = db.query(DailyAnalytics).filter(DailyAnalytics.date == target_date).first()
        if analytics:
            analytics.total_users = total_users
            analytics.active_sessions = active_sessions
            analytics.total_calculations = total_calculations
            analytics.total_revenue = int(total_revenue) if total_revenue else 0
            analytics.avg_trip_cost = int(avg_trip_cost) if avg_trip_cost else 0
            analytics.popular_destination = popular_dest
        else:
            analytics = DailyAnalytics(
                date=target_date,
                total_users=total_users,
                active_sessions=active_sessions,
                total_calculations=total_calculations,
                total_revenue=int(total_revenue) if total_revenue else 0,
                avg_trip_cost=int(avg_trip_cost) if avg_trip_cost else 0,
                popular_destination=popular_dest
            )
            db.add(analytics)
        
        db.commit()
        logger.info(f"Updated daily analytics for {target_date}")
    except Exception as e:
        logger.error(f"Error updating daily analytics: {e}")
        db.rollback()
    finally:
        db.close()


def get_daily_analytics(target_date: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """Get daily analytics for a specific date."""
    db = SessionLocal()
    try:
        if target_date is None:
            target_date = date.today()
        
        analytics = db.query(DailyAnalytics).filter(DailyAnalytics.date == target_date).first()
        if analytics:
            return {
                "date": analytics.date,
                "total_users": analytics.total_users,
                "active_sessions": analytics.active_sessions,
                "total_calculations": analytics.total_calculations,
                "total_revenue": analytics.total_revenue,
                "avg_trip_cost": analytics.avg_trip_cost,
                "popular_destination": analytics.popular_destination
            }
        return None
    finally:
        db.close()
