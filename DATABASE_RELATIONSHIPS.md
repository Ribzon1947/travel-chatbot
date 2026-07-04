# Database Entity Relationships & Schema Details

## Complete Entity Relationship Diagram

```
                          CORE PRICING DOMAIN
                    ┌─────────────────────────────┐
                    │                             │
                ┌───┴────────┐            ┌──────┴──────┐
              PLACES        DESTINATIONS      │
                │               │           │
                └───────┬───────┘           │
                        │                   │
                   ROUTE_PRICING            │
                        │                   │
                        └────┬──────────────┘
                             │
              ┌──────────────┘
              │
        PRICING_HISTORY
              │
              │
         ┌────┴─────────────────────────────┐
         │                                  │
         │         USER DOMAIN              │
         │                                  │
         │      USERS ──────→ SESSIONS      │
         │        ↑            │   │        │
         │        │            │   │        │
         │        │    ┌───────┘   │        │
         │        │    │           │        │
         │        │    ↓           ↓        │
         │        │  CHAT_CONVERSATIONS    │
         │        │            │           │
         │        │            ↓           │
         │        │       CHAT_MESSAGES    │
         │        │                        │
         │        │  TRIP_CALCULATIONS    │
         │        │       ↑                │
         └────────┼───────┘                │
                  │                        │
                  │  AUDIT DOMAIN          │
                  │                        │
              ┌───┴───────────────┐        │
              │                   │        │
         AUDIT_LOGS          API_REQUESTS  │
              │                   │        │
              └───────┬───────────┘        │
                      │                    │
                      │                    │
                  ERROR_LOGS ──────────────┘
                      │
                      │
         ┌────────────┘
         │
    ANALYTICS DOMAIN
         │
    ┌────┴─────────────────┐
    │                      │
DAILY_ANALYTICS    DESTINATION_POPULARITY
    │                      │
    └──────────────────────┘
```

## Table Relationships in Detail

### Core Pricing Domain

```
┌──────────┐
│  PLACES  │ (id, name, country, latitude, longitude, created_at, updated_at)
└─────┬────┘
      │ 1
      │
      │ N
┌─────▼──────────────┐
│ ROUTE_PRICING      │ (id, place_id→places, destination_id→destinations, *_enc, created_at, updated_at)
├────────────────────┤
│ Unique: (place_id, destination_id)
└─────┬──────────────┘
      │
      │ 1
      │
      │ N
┌─────▼────────────────────┐
│ PRICING_HISTORY          │ (id, route_pricing_id→route_pricing, version, *_enc, changed_by, changed_at, change_reason)
└──────────────────────────┘


┌────────────────┐
│ DESTINATIONS   │ (id, name, country, region, best_season, latitude, longitude, created_at, updated_at)
└────┬───────────┘
     │ 1
     │
     │ N
 ┌───▼───────────────────────────┐
 │ DESTINATION_POPULARITY        │ (id, destination_id→destinations(UNIQUE), query_count, booking_count, avg_rating, last_updated)
 └────────────────────────────────┘
```

### User & Session Domain

```
┌────────────────────────────────────────────────────────────┐
│ USERS                                                      │
│ (id, user_id(UNIQUE), email, phone, name, preferences,    │
│  created_at, last_active, is_active)                       │
└────┬───────────────────────────────────────────────────────┘
     │ 1
     │
     │ N (0 or many sessions per user)
     │
┌────▼─────────────────────────────────────────────┐
│ SESSIONS                                         │
│ (id, user_id→users, session_token(UNIQUE),       │
│  from_location, to_location, started_at,        │
│  ended_at, duration_seconds, is_active)         │
├──────────────────────────────────────────────────┤
│ Indexes: user_id, is_active, session_token      │
└────┬────────────────────────────────────────────┘
     │
     ├─────────────────┬──────────────────┐
     │ 1               │ 1                │
     │                 │                  │
     │ N               │ N                │ N
     │                 │                  │
┌────▼──────────────────────┐  ┌──────────▼────────────────┐
│ CHAT_CONVERSATIONS        │  │ TRIP_CALCULATIONS        │
│ (id, session_id→sessions, │  │ (id, session_id→sessions,│
│  conversation_title,      │  │  calculation_type,       │
│  message_count,           │  │  num_people,             │
│  created_at, updated_at)  │  │  kids_under_7,           │
└────┬───────────────────────┘  │  num_days, num_nights,   │
     │                          │  origin, destination,    │
     │ 1                        │  destinations_list,      │
     │                          │  itinerary,              │
     │ N                        │  grand_total,            │
     │                          │  calculation_data,       │
┌────▼────────────────────────┐ │  calculated_at)          │
│ CHAT_MESSAGES              │ └──────────────────────────┘
│ (id, conversation_id,      │
│  sender_role, message_text,│
│  created_at)               │
└────────────────────────────┘
```

### Audit & Logging Domain

```
From USERS:

┌──────────────┐      ┌─────────────────────────────────────────────────┐
│    USERS     │────→ │ AUDIT_LOGS                                      │
└──────────────┘ 1    │ (id, user_id→users(nullable), action, entity_  │
                  N   │  type, entity_id, old_values, new_values,      │
                      │  timestamp, ip_address, user_agent)            │
                      └─────────────────────────────────────────────────┘


┌──────────────┐      ┌────────────────────────────────────────┐
│    USERS     │────→ │ API_REQUESTS                           │
└──────────────┘ 1    │ (id, endpoint, method, user_id→users,  │
                  N   │  request_body, response_status,        │
                      │  response_time_ms, timestamp)          │
                      └────────────────────────────────────────┘


┌──────────────┐      ┌───────────────────────────────────────┐
│    USERS     │────→ │ ERROR_LOGS                            │
└──────────────┘ 1    │ (id, error_type, error_message,       │
                  N   │  stack_trace, user_id→users(nullable),│
                      │  endpoint, timestamp)                 │
                      └───────────────────────────────────────┘
```

### Analytics Domain

```
┌───────────────────────────────────────┐
│ DAILY_ANALYTICS (1 per day)           │
│ (id, date(UNIQUE), total_users,       │
│  active_sessions, total_calculations, │
│  total_revenue, avg_trip_cost,        │
│  popular_destination, recorded_at)    │
├───────────────────────────────────────┤
│ Aggregated from: SESSIONS,            │
│ TRIP_CALCULATIONS, CHAT_MESSAGES      │
└───────────────────────────────────────┘


From DESTINATIONS:

┌────────────────────┐      ┌──────────────────────────────────────┐
│  DESTINATIONS      │────→ │ DESTINATION_POPULARITY (see above)   │
└────────────────────┘ 1    └──────────────────────────────────────┘
                         (repeating from pricing domain)
```

## Cardinality Summary

| Relationship | Type | Notes |
|-------------|------|-------|
| PLACES → ROUTE_PRICING | 1:N | One place can have many pricing routes |
| DESTINATIONS → ROUTE_PRICING | 1:N | One destination can have many pricing routes |
| ROUTE_PRICING → PRICING_HISTORY | 1:N | Track all pricing changes |
| DESTINATIONS → DESTINATION_POPULARITY | 1:1 | One popularity record per destination |
| USERS → SESSIONS | 1:N | User can have multiple sessions |
| SESSIONS → CHAT_CONVERSATIONS | 1:N | Session can have multiple conversations |
| CHAT_CONVERSATIONS → CHAT_MESSAGES | 1:N | Conversation can have many messages |
| SESSIONS → TRIP_CALCULATIONS | 1:N | Session can have many calculations |
| USERS → AUDIT_LOGS | 1:N | User actions tracked in audit logs |
| USERS → API_REQUESTS | 1:N | User API calls tracked |
| USERS → ERROR_LOGS | 1:N (nullable) | User-related errors logged |

## Foreign Key Constraints

All foreign key relationships use **ON DELETE CASCADE** where appropriate:

```sql
place_id → places(id)          -- Cascade delete routes when place is deleted
destination_id → destinations(id) -- Cascade delete routes when destination is deleted
route_pricing_id → route_pricing(id) -- Cascade delete history when pricing is deleted
user_id → users(id)            -- Cascade delete sessions, conversations, calculations
session_id → sessions(id)      -- Cascade delete conversations, calculations
conversation_id → chat_conversations(id) -- Cascade delete messages
```

**Exception:** `user_id` in AUDIT_LOGS, API_REQUESTS, ERROR_LOGS uses **ON DELETE SET NULL** to preserve logs even if user is deleted.

## Indexes for Performance

```
Core Pricing:
├─ places: name (UNIQUE), country
├─ destinations: name (UNIQUE), country, region
├─ route_pricing: place_id, destination_id, (place_id, destination_id)
├─ pricing_history: route_pricing_id
└─ destination_popularity: destination_id (UNIQUE)

User & Session:
├─ users: user_id (UNIQUE), email
├─ sessions: user_id, is_active, session_token (UNIQUE)
├─ chat_conversations: session_id
├─ chat_messages: conversation_id, created_at
└─ trip_calculations: session_id, calculation_type

Audit & Logging:
├─ audit_logs: user_id, timestamp, entity_type
├─ api_requests: timestamp, user_id, endpoint
└─ error_logs: timestamp, error_type

Analytics:
├─ daily_analytics: date (UNIQUE)
└─ destination_popularity: destination_id (UNIQUE)
```

## Query Examples

### Get user's trip calculation history
```sql
SELECT tc.* FROM trip_calculations tc
JOIN sessions s ON tc.session_id = s.id
JOIN users u ON s.user_id = u.id
WHERE u.user_id = 'user_123'
ORDER BY tc.calculated_at DESC;
```

### Get conversation history for a session
```sql
SELECT cm.* FROM chat_messages cm
JOIN chat_conversations cc ON cm.conversation_id = cc.id
JOIN sessions s ON cc.session_id = s.id
WHERE s.session_token = 'session_token_abc'
ORDER BY cm.created_at ASC;
```

### Get audit trail for an entity
```sql
SELECT * FROM audit_logs
WHERE entity_type = 'RoutePricing' 
  AND entity_id = 1
ORDER BY timestamp DESC;
```

### Get daily analytics with destination popularity
```sql
SELECT da.*, dp.destination_id, dp.query_count, dp.booking_count
FROM daily_analytics da
LEFT JOIN destination_popularity dp ON da.popular_destination = d.name
WHERE da.date = '2024-01-15'
ORDER BY dp.query_count DESC;
```

### Get user activity statistics
```sql
SELECT 
    u.user_id,
    u.name,
    COUNT(DISTINCT s.id) as total_sessions,
    SUM(s.duration_seconds) as total_session_time,
    COUNT(DISTINCT tc.id) as total_calculations,
    SUM(tc.grand_total) as total_revenue
FROM users u
LEFT JOIN sessions s ON u.id = s.user_id
LEFT JOIN trip_calculations tc ON s.id = tc.session_id
WHERE u.user_id = 'user_123'
GROUP BY u.id;
```

## Data Flow

1. **User initiates request** → CREATE `users` record (if new)
2. **Session starts** → CREATE `sessions` record with token
3. **Chat interaction** → CREATE `chat_conversations` + `chat_messages`
4. **Cost calculation** → CREATE `trip_calculations` record
5. **Admin action** → CREATE `audit_logs` record
6. **API request** → CREATE `api_requests` record
7. **Error occurs** → CREATE `error_logs` record
8. **End of day** → UPDATE `daily_analytics` with aggregated metrics
9. **Destination searched** → UPDATE `destination_popularity`

## Backup & Recovery

Key tables to prioritize in backups:
1. **CRITICAL**: route_pricing, users, sessions, chat_messages, trip_calculations
2. **IMPORTANT**: chat_conversations, audit_logs, destination_popularity
3. **OPTIONAL**: daily_analytics (can be regenerated), api_requests, error_logs (for debugging only)

## Scaling Strategies

- **Partitioning**: chat_messages and api_requests by date
- **Read Replicas**: For analytics queries (daily_analytics, audit_logs)
- **Archival**: Move old api_requests/error_logs to archive table after 90 days
- **Aggregation**: Pre-compute popular destinations weekly
