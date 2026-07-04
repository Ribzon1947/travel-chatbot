# Chatbot Relational Database Design

## Architecture Overview

The Travel Chatbot database is a comprehensive relational system designed as a separate entity that integrates with the main chatbot application. It spans 6 logical domains with 15+ interconnected tables.

### Domain Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    CHATBOT DATABASE SYSTEM                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 1. CORE LOCATION & PRICING DOMAIN                       │  │
│  │    - places, destinations, route_pricing               │  │
│  │    - pricing_history, destination_popularity           │  │
│  │    └─→ Manages travel location data and encryption     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           ↓                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 2. USER MANAGEMENT DOMAIN                               │  │
│  │    - users, sessions                                    │  │
│  │    └─→ Tracks user identity and session lifecycle      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           ↓                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 3. CONVERSATION DOMAIN                                  │  │
│  │    - chat_conversations, chat_messages                 │  │
│  │    └─→ Stores chat history and multi-turn interactions │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           ↓                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 4. CALCULATION TRACKING DOMAIN                          │  │
│  │    - trip_calculations                                  │  │
│  │    └─→ Records all cost calculations for analysis       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           ↓                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 5. AUDIT & LOGGING DOMAIN                               │  │
│  │    - audit_logs, api_requests, error_logs              │  │
│  │    └─→ Complete operational transparency               │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           ↓                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 6. ANALYTICS & REPORTING DOMAIN                         │  │
│  │    - daily_analytics, destination_popularity           │  │
│  │    └─→ Aggregated insights for business intelligence   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Entity Relationship Diagram (Conceptual)

```
PLACES ─────────────────┐
                        │
                    ROUTE_PRICING ──── DESTINATIONS
                        ↓                      │
                   PRICING_HISTORY      DESTINATION_
                                       POPULARITY
                        
USERS ──────────────────────── SESSIONS ─────── CHAT_
                                   │          CONVERSATIONS
                                   │              │
                                   │              ├──→ CHAT_
                                   │                   MESSAGES
                                   │
                            TRIP_CALCULATIONS
                                   │
                            AUDIT_LOGS, API_REQUESTS, ERROR_LOGS
                            
DAILY_ANALYTICS (aggregated from all sources)
```

## Table Specifications

### Domain 1: Core Location & Pricing

#### `places`
- **Purpose**: Origin/source locations for trips
- **Key Columns**:
  - `id` (PK)
  - `name` (UNIQUE)
  - `country`, `latitude`, `longitude`
- **Indexes**: name (unique), country
- **Relationships**: ← route_pricing

#### `destinations`
- **Purpose**: Travel destination locations
- **Key Columns**:
  - `id` (PK)
  - `name` (UNIQUE)
  - `country`, `region`, `best_season`
  - `latitude`, `longitude`
- **Indexes**: name (unique), country, region
- **Relationships**: ← route_pricing, ← destination_popularity

#### `route_pricing`
- **Purpose**: Encrypted pricing matrix for place→destination routes
- **Key Columns**:
  - `id` (PK)
  - `place_id` (FK) → places
  - `destination_id` (FK) → destinations
  - `hotel_cost_enc`, `people_per_room_enc`, `cab_cost_enc`, `meal_cost_enc`, `ticket_cost_enc` (BLOB - encrypted)
  - `created_at`, `updated_at`
- **Constraints**: UNIQUE(place_id, destination_id)
- **Indexes**: place_id, destination_id
- **Relationships**: → places, → destinations, ← pricing_history

#### `pricing_history`
- **Purpose**: Audit trail for pricing changes
- **Key Columns**:
  - `id` (PK)
  - `route_pricing_id` (FK) → route_pricing
  - `version` (INT)
  - `*_enc` fields (same as route_pricing)
  - `changed_by`, `changed_at`, `change_reason`
- **Relationships**: → route_pricing

#### `destination_popularity`
- **Purpose**: Track popularity metrics
- **Key Columns**:
  - `id` (PK)
  - `destination_id` (FK) → destinations (UNIQUE)
  - `query_count`, `booking_count`
  - `avg_rating` (REAL)
  - `last_updated`
- **Relationships**: → destinations

### Domain 2: User Management

#### `users`
- **Purpose**: User account and profile management
- **Key Columns**:
  - `id` (PK)
  - `user_id` (UNIQUE) - external user identifier
  - `email`, `phone`, `name`
  - `preferences` (JSON TEXT)
  - `created_at`, `last_active`
  - `is_active` (BOOLEAN)
- **Indexes**: user_id (unique), email
- **Relationships**: ← sessions, ← audit_logs, ← api_requests, ← error_logs

#### `sessions`
- **Purpose**: Track individual user sessions
- **Key Columns**:
  - `id` (PK)
  - `user_id` (FK) → users
  - `session_token` (UNIQUE)
  - `from_location`, `to_location`
  - `started_at`, `ended_at`
  - `duration_seconds`
  - `is_active` (BOOLEAN)
- **Indexes**: user_id, session_token (unique), is_active
- **Relationships**: → users, ← chat_conversations, ← trip_calculations

### Domain 3: Conversation

#### `chat_conversations`
- **Purpose**: Group related messages into conversations
- **Key Columns**:
  - `id` (PK)
  - `session_id` (FK) → sessions
  - `conversation_title`
  - `message_count`
  - `created_at`, `updated_at`
- **Indexes**: session_id
- **Relationships**: → sessions, ← chat_messages

#### `chat_messages`
- **Purpose**: Individual chat messages
- **Key Columns**:
  - `id` (PK)
  - `conversation_id` (FK) → chat_conversations
  - `sender_role` (VARCHAR: "user", "assistant", "system")
  - `message_text` (TEXT)
  - `created_at`
- **Indexes**: conversation_id, created_at
- **Relationships**: → chat_conversations

### Domain 4: Calculation Tracking

#### `trip_calculations`
- **Purpose**: Record all cost calculations for auditing and analysis
- **Key Columns**:
  - `id` (PK)
  - `session_id` (FK) → sessions
  - `calculation_type` (VARCHAR: "single_destination", "compare_destinations", "multi_city_trip")
  - `num_people`, `kids_under_7`, `num_days`, `num_nights`
  - `origin`, `destination`
  - `destinations_list` (JSON - for compare)
  - `itinerary` (JSON - for multi-city)
  - `grand_total`
  - `calculation_data` (JSON - full details)
  - `calculated_at`
- **Indexes**: session_id, calculation_type
- **Relationships**: → sessions

### Domain 5: Audit & Logging

#### `audit_logs`
- **Purpose**: Complete audit trail of user actions
- **Key Columns**:
  - `id` (PK)
  - `user_id` (FK) → users (NULL for system actions)
  - `action` (VARCHAR: "create", "update", "delete", "calculate", etc.)
  - `entity_type` (VARCHAR: "RoutePricing", "Destination", "Session", etc.)
  - `entity_id`
  - `old_values` (JSON)
  - `new_values` (JSON)
  - `timestamp`
  - `ip_address`, `user_agent`
- **Indexes**: user_id, timestamp, entity_type
- **Relationships**: → users

#### `api_requests`
- **Purpose**: Track API performance and usage
- **Key Columns**:
  - `id` (PK)
  - `endpoint` (VARCHAR)
  - `method` (VARCHAR: "GET", "POST", "PUT", "DELETE")
  - `user_id` (FK) → users (nullable)
  - `request_body` (TEXT)
  - `response_status` (INT)
  - `response_time_ms`
  - `timestamp`
- **Indexes**: timestamp, user_id, endpoint
- **Relationships**: → users

#### `error_logs`
- **Purpose**: Log exceptions and errors
- **Key Columns**:
  - `id` (PK)
  - `error_type` (VARCHAR: "ValidationError", "EncryptionError", "DatabaseError", etc.)
  - `error_message` (TEXT)
  - `stack_trace` (TEXT)
  - `user_id` (FK) → users (nullable)
  - `endpoint` (VARCHAR)
  - `timestamp`
- **Indexes**: timestamp, error_type
- **Relationships**: → users

### Domain 6: Analytics & Reporting

#### `daily_analytics`
- **Purpose**: Aggregated daily metrics
- **Key Columns**:
  - `id` (PK)
  - `date` (DATE, UNIQUE)
  - `total_users` (INT)
  - `active_sessions` (INT)
  - `total_calculations` (INT)
  - `total_revenue` (INT - sum of grand_totals)
  - `avg_trip_cost` (INT - average grand_total)
  - `popular_destination` (VARCHAR)
  - `recorded_at`
- **Relationships**: Aggregated data (no direct FK)

## Connection Strategy

The database connects to the main chatbot application through these touchpoints:

### 1. **Pricing Integration** (`app/pricing.py`)
- Reads encrypted pricing from `route_pricing`
- Logs calculations to `trip_calculations`
- Updates `destination_popularity`

### 2. **Chat Integration** (`app/chatbot.py`)
- Records conversations in `chat_conversations` and `chat_messages`
- Associates with `sessions` via session tokens
- References in `audit_logs`

### 3. **User Context** (middleware/session management)
- Creates/updates `users` and `sessions`
- Tracks `last_active` on each request
- Links all activities to user_id

### 4. **Analytics Collection** (background jobs or request handlers)
- Logs every API request to `api_requests`
- Logs errors to `error_logs`
- Records audit events to `audit_logs`

## Python Integration

### SQLAlchemy Models
All tables have corresponding ORM models in `app/models.py` with proper relationships defined.

### Management Modules

**`app/user_manager.py`** - User and Session Operations
```python
create_session(user_id, from_location, to_location)
create_conversation(session_token, title)
add_message(conversation_id, sender_role, message_text)
record_trip_calculation(session_token, calculation_type, data)
get_user_statistics(user_id)
```

**`app/analytics.py`** - Audit, Logging, and Analytics
```python
log_audit_event(user_id, action, entity_type, ...)
log_api_request(endpoint, method, user_id, ...)
log_error(error_type, error_message, ...)
increment_destination_query(destination)
update_daily_analytics(date)
get_daily_analytics(date)
```

## Key Design Principles

1. **Separation of Concerns** - Each domain handles a specific aspect
2. **Audit Trail** - All important actions are logged
3. **Encryption Ready** - Binary columns support FHE encrypted data
4. **Referential Integrity** - FK constraints with CASCADE on delete
5. **Performance** - Appropriate indexes on all lookup columns
6. **Scalability** - Normalized schema supports growth
7. **Analytics** - Aggregated tables for reporting without impacting transactions

## Initialization

```bash
# SQLite
sqlite3 ./chatbot.db < database/schema.sql

# PostgreSQL
psql "$DATABASE_URL" -f database/schema.sql
```

## Related Documentation

- `schema.sql` - Complete SQL definitions
- `app/models.py` - SQLAlchemy ORM models
- `app/user_manager.py` - User/session operations
- `app/analytics.py` - Audit/analytics operations
- `app/database.py` - Database connection management
