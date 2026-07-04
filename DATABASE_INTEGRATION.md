# Database Integration Guide

## How to Integrate the Database into the Chatbot

### Step 1: Initialize Database on Startup

In `app/main.py`, the lifespan function should initialize the database:

```python
from app.database import init_db
from app.user_manager import get_or_create_user
from app.analytics import update_daily_analytics

@asynccontextmanager
async def lifespan(_: FastAPI):
    loop = asyncio.get_event_loop()
    
    # Initialize database schema
    await loop.run_in_executor(None, init_db)
    
    # Optional: Update daily analytics on startup
    await loop.run_in_executor(None, update_daily_analytics)
    
    yield
```

### Step 2: Middleware for Request Tracking

Add a middleware to track API requests and user activity:

```python
from fastapi import Request
from app.analytics import log_api_request
from app.user_manager import update_user_activity
import time

@app.middleware("http")
async def track_requests(request: Request, call_next):
    start_time = time.time()
    
    # Extract user_id if available
    user_id = request.headers.get("X-User-ID")
    
    try:
        response = await call_next(request)
        process_time = int((time.time() - start_time) * 1000)
        
        # Log request
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            log_api_request,
            request.url.path,
            request.method,
            user_id,
            None,
            response.status_code,
            process_time
        )
        
        # Update user activity
        if user_id:
            await loop.run_in_executor(None, update_user_activity, user_id)
        
        return response
    except Exception as e:
        process_time = int((time.time() - start_time) * 1000)
        if user_id:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                log_error,
                type(e).__name__,
                str(e),
                traceback.format_exc(),
                user_id,
                request.url.path
            )
        raise
```

### Step 3: Session Management in Chat Endpoint

Modify the chat endpoint to create sessions and conversations:

```python
from app.user_manager import create_session, create_conversation, add_message, record_trip_calculation
from app.analytics import log_audit_event, increment_destination_query

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest, X_User_ID: str = Header(None)) -> ChatResponse:
    user_id = X_User_ID or "anonymous"
    from_loc = request.from_location or "Default"
    to_loc = request.to_location or "Default"
    
    loop = asyncio.get_event_loop()
    
    # Create or get session
    session_token = await loop.run_in_executor(
        None,
        create_session,
        user_id,
        from_loc,
        to_loc
    )
    
    # Create conversation if needed
    conv_id = await loop.run_in_executor(
        None,
        create_conversation,
        session_token,
        f"Chat: {to_loc}"
    )
    
    # Log user message
    await loop.run_in_executor(
        None,
        add_message,
        conv_id,
        "user",
        request.message
    )
    
    # Track destination interest
    await loop.run_in_executor(None, increment_destination_query, to_loc)
    
    try:
        # Call chatbot
        response_text = await chat(request.message, request.history, from_loc, to_loc)
        
        # Log assistant response
        await loop.run_in_executor(
            None,
            add_message,
            conv_id,
            "assistant",
            response_text
        )
        
        return ChatResponse(response=response_text)
    
    except Exception as e:
        from app.analytics import log_error
        await loop.run_in_executor(
            None,
            log_error,
            "ChatError",
            str(e),
            traceback.format_exc(),
            user_id,
            "/api/chat"
        )
        raise
```

### Step 4: Track Cost Calculations

When the chatbot calculates costs, record them:

```python
# In app/chatbot.py, after calculate_trip_cost tool call:

if fc.name == "calculate_trip_cost":
    result = calculate_trip_cost(**args, destination=to_loc)
    
    # Record calculation
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        record_trip_calculation,
        session_token,
        "single_destination",
        {
            "num_people": result.get("num_people"),
            "kids_under_7": result.get("kids_under_7", 0),
            "num_days": result.get("num_days"),
            "num_nights": result.get("num_nights"),
            "origin": result.get("origin"),
            "destination": result.get("destination"),
            "grand_total": result.get("grand_total"),
            **result  # All calculation details
        }
    )
    
    # Audit log
    await loop.run_in_executor(
        None,
        log_audit_event,
        user_id,
        "trip_calculation",
        "RoutePricing",
        None,  # entity_id
        None,  # old_values
        result  # new_values
    )
```

### Step 5: Admin Endpoints for Analytics

Add admin endpoints to view analytics:

```python
@app.get("/admin/analytics/daily")
async def get_daily_stats(date: str = None, authorization: str = Header(None)):
    await require_admin(authorization)
    
    loop = asyncio.get_event_loop()
    from datetime import datetime
    target_date = datetime.strptime(date, "%Y-%m-%d").date() if date else None
    
    stats = await loop.run_in_executor(
        None,
        get_daily_analytics,
        target_date
    )
    return stats

@app.get("/admin/analytics/destinations")
async def get_dest_popularity(limit: int = 10, authorization: str = Header(None)):
    await require_admin(authorization)
    
    loop = asyncio.get_event_loop()
    from app.analytics import get_destination_popularity
    
    results = await loop.run_in_executor(
        None,
        get_destination_popularity,
        limit
    )
    return [{"destination": r.destination.name, "queries": r.query_count, "bookings": r.booking_count} for r in results]

@app.get("/admin/analytics/audit-logs")
async def get_audit(user_id: str = None, limit: int = 100, authorization: str = Header(None)):
    await require_admin(authorization)
    
    loop = asyncio.get_event_loop()
    from app.analytics import get_audit_logs
    
    logs = await loop.run_in_executor(
        None,
        get_audit_logs,
        user_id,
        None,
        limit
    )
    return logs

@app.get("/admin/analytics/errors")
async def get_errors(limit: int = 100, authorization: str = Header(None)):
    await require_admin(authorization)
    
    loop = asyncio.get_event_loop()
    from app.analytics import get_error_logs
    
    logs = await loop.run_in_executor(None, get_error_logs, None, limit)
    return logs

@app.get("/admin/user-stats/{user_id}")
async def get_user_stats(user_id: str, authorization: str = Header(None)):
    await require_admin(authorization)
    
    loop = asyncio.get_event_loop()
    from app.user_manager import get_user_statistics
    
    stats = await loop.run_in_executor(None, get_user_statistics, user_id)
    return stats
```

### Step 6: Periodic Analytics Update (Background Task)

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta

scheduler = AsyncIOScheduler()

async def update_analytics_job():
    """Run daily analytics update at midnight"""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, update_daily_analytics)
    logger.info("Daily analytics updated")

@app.on_event("startup")
async def start_scheduler():
    scheduler.add_job(update_analytics_job, 'cron', hour=0, minute=0)
    scheduler.start()

@app.on_event("shutdown")
async def shutdown_scheduler():
    scheduler.shutdown()
```

### Step 7: Error Handling

Wrap operations with error logging:

```python
import traceback
from app.analytics import log_error

async def safe_operation(user_id: str, operation_name: str, func, *args, **kwargs):
    """Safely execute operation with error logging"""
    try:
        return await func(*args, **kwargs)
    except Exception as e:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            log_error,
            type(e).__name__,
            str(e),
            traceback.format_exc(),
            user_id,
            f"/{operation_name}"
        )
        raise
```

## Example: Complete Chat Flow

```python
@app.post("/api/chat")
async def chat_endpoint(
    request: ChatRequest,
    X_User_ID: str = Header(None)
) -> ChatResponse:
    user_id = X_User_ID or f"anonymous_{uuid.uuid4()}"
    from_loc = request.from_location or "Default"
    to_loc = request.to_location or "Default"
    
    loop = asyncio.get_event_loop()
    
    try:
        # 1. Create session
        session_token = await loop.run_in_executor(
            None, create_session, user_id, from_loc, to_loc
        )
        
        # 2. Create conversation
        conv_id = await loop.run_in_executor(
            None, create_conversation, session_token, f"Chat to {to_loc}"
        )
        
        # 3. Log incoming message
        await loop.run_in_executor(
            None, add_message, conv_id, "user", request.message
        )
        
        # 4. Track destination interest
        await loop.run_in_executor(
            None, increment_destination_query, to_loc
        )
        
        # 5. Get chat response
        response_text = await chat(
            request.message,
            request.history,
            from_loc,
            to_loc
        )
        
        # 6. Log response message
        await loop.run_in_executor(
            None, add_message, conv_id, "assistant", response_text
        )
        
        # 7. Log audit event
        await loop.run_in_executor(
            None, log_audit_event,
            user_id, "chat_message",
            "ChatMessage", conv_id,
            None, {"role": "assistant", "text": response_text}
        )
        
        # 8. Return response
        return ChatResponse(response=response_text)
        
    except Exception as e:
        await loop.run_in_executor(
            None, log_error,
            type(e).__name__, str(e),
            traceback.format_exc(),
            user_id, "/api/chat"
        )
        raise HTTPException(
            status_code=500,
            detail="Chat processing failed"
        )
```

## Configuration

Add to `app/config.py`:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./chatbot.db"
    
    # Analytics
    enable_analytics: bool = True
    analytics_update_hour: int = 0  # Midnight UTC
    
    # Audit
    enable_audit_logging: bool = True
    audit_retention_days: int = 90
    
    # Error logging
    enable_error_logging: bool = True
    error_retention_days: int = 30
    
    class Config:
        env_file = ".env"

settings = Settings()
```

## Testing

Example test for database operations:

```python
import pytest
from app.user_manager import create_session, create_conversation, add_message
from app.analytics import get_daily_analytics
from datetime import date

def test_user_session_flow():
    # Create session
    session_token = create_session("test_user_123", "Delhi", "Goa")
    assert session_token is not None
    
    # Create conversation
    conv_id = create_conversation(session_token, "Test Conversation")
    assert conv_id is not None
    
    # Add messages
    msg_id = add_message(conv_id, "user", "Test message")
    assert msg_id is not None
    
    # Verify message was stored
    conv_history = get_conversation_history(conv_id)
    assert len(conv_history) > 0
    assert conv_history[-1].message_text == "Test message"

def test_daily_analytics():
    # Update analytics
    update_daily_analytics(date.today())
    
    # Retrieve analytics
    stats = get_daily_analytics(date.today())
    assert stats is not None
    assert "total_users" in stats
```

## Monitoring & Maintenance

### Monitor Key Metrics

```python
from app.analytics import get_daily_analytics
from datetime import date

# Daily health check
stats = get_daily_analytics(date.today())
print(f"Active Users: {stats['total_users']}")
print(f"Total Calculations: {stats['total_calculations']}")
print(f"Average Trip Cost: Rs {stats['avg_trip_cost']:,}")
```

### Cleanup Old Logs

```python
from app.database import SessionLocal
from app.models import ApiRequest, ErrorLog
from datetime import datetime, timedelta

def cleanup_old_logs(days_to_keep=90):
    """Remove logs older than specified days"""
    db = SessionLocal()
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        
        # Clean API requests
        db.query(ApiRequest).filter(ApiRequest.timestamp < cutoff_date).delete()
        
        # Clean error logs
        db.query(ErrorLog).filter(ErrorLog.timestamp < cutoff_date).delete()
        
        db.commit()
        print(f"Cleaned logs older than {cutoff_date}")
    finally:
        db.close()
```

## Performance Tips

1. **Indexes**: All lookup columns are indexed - queries are fast
2. **Batch Operations**: Group database operations to reduce I/O
3. **Async Execution**: Use `loop.run_in_executor()` to avoid blocking event loop
4. **Read Replicas**: For analytics queries, use read-only replicas
5. **Caching**: Cache destination popularity data (updated daily)
6. **Archival**: Move old logs to archive tables after retention period
