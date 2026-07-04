-- ═══════════════════════════════════════════════════════════════════════════════
-- Travel Chatbot Relational Database Schema
-- Comprehensive schema with pricing, users, sessions, chat history, and audit logs
-- ═══════════════════════════════════════════════════════════════════════════════

-- ─── Core Location & Pricing Tables ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS places (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(128) NOT NULL UNIQUE,
    description TEXT,
    latitude REAL,
    longitude REAL,
    country VARCHAR(128),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS destinations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(128) NOT NULL UNIQUE,
    description TEXT,
    latitude REAL,
    longitude REAL,
    country VARCHAR(128),
    region VARCHAR(128),
    best_season VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS route_pricing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id INTEGER NOT NULL,
    destination_id INTEGER NOT NULL,
    hotel_cost_enc BLOB NOT NULL,
    people_per_room_enc BLOB NOT NULL,
    cab_cost_enc BLOB NOT NULL,
    meal_cost_enc BLOB NOT NULL,
    ticket_cost_enc BLOB NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(place_id) REFERENCES places(id) ON DELETE CASCADE,
    FOREIGN KEY(destination_id) REFERENCES destinations(id) ON DELETE CASCADE,
    UNIQUE (place_id, destination_id)
);

-- ─── User Management Tables ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id VARCHAR(255) NOT NULL UNIQUE,
    email VARCHAR(255),
    phone VARCHAR(20),
    name VARCHAR(128),
    preferences TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_active DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    session_token VARCHAR(255) NOT NULL UNIQUE,
    from_location VARCHAR(128),
    to_location VARCHAR(128),
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at DATETIME,
    duration_seconds INTEGER,
    is_active BOOLEAN DEFAULT 1,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ─── Chat History Tables ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS chat_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    conversation_title VARCHAR(255),
    message_count INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    sender_role VARCHAR(20) NOT NULL,
    message_text TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(conversation_id) REFERENCES chat_conversations(id) ON DELETE CASCADE
);

-- ─── Trip Calculation History ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS trip_calculations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    calculation_type VARCHAR(50) NOT NULL,
    num_people INTEGER,
    kids_under_7 INTEGER DEFAULT 0,
    num_days INTEGER,
    num_nights INTEGER,
    origin VARCHAR(128),
    destination VARCHAR(128),
    destinations_list TEXT,
    itinerary TEXT,
    grand_total INTEGER,
    calculation_data TEXT,
    calculated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- ─── Audit & Logging Tables ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50),
    entity_id INTEGER,
    old_values TEXT,
    new_values TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(45),
    user_agent TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS api_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint VARCHAR(255) NOT NULL,
    method VARCHAR(10) NOT NULL,
    user_id INTEGER,
    request_body TEXT,
    response_status INTEGER,
    response_time_ms INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS error_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    error_type VARCHAR(100) NOT NULL,
    error_message TEXT NOT NULL,
    stack_trace TEXT,
    user_id INTEGER,
    endpoint VARCHAR(255),
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- ─── Pricing History & Versioning ───────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pricing_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_pricing_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    hotel_cost_enc BLOB NOT NULL,
    people_per_room_enc BLOB NOT NULL,
    cab_cost_enc BLOB NOT NULL,
    meal_cost_enc BLOB NOT NULL,
    ticket_cost_enc BLOB NOT NULL,
    changed_by VARCHAR(128),
    changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    change_reason TEXT,
    FOREIGN KEY(route_pricing_id) REFERENCES route_pricing(id) ON DELETE CASCADE
);

-- ─── Analytics & Aggregation Tables ────────────────────────────────────────

CREATE TABLE IF NOT EXISTS daily_analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL UNIQUE,
    total_users INTEGER DEFAULT 0,
    active_sessions INTEGER DEFAULT 0,
    total_calculations INTEGER DEFAULT 0,
    total_revenue INTEGER DEFAULT 0,
    avg_trip_cost INTEGER DEFAULT 0,
    popular_destination VARCHAR(128),
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS destination_popularity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    destination_id INTEGER NOT NULL,
    query_count INTEGER DEFAULT 0,
    booking_count INTEGER DEFAULT 0,
    avg_rating REAL DEFAULT 0,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(destination_id) REFERENCES destinations(id) ON DELETE CASCADE
);

-- ─── Indexes for Performance ────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_route_pricing_place ON route_pricing(place_id);
CREATE INDEX IF NOT EXISTS idx_route_pricing_destination ON route_pricing(destination_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(is_active);
CREATE INDEX IF NOT EXISTS idx_chat_conversations_session ON chat_conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation ON chat_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_trip_calculations_session ON trip_calculations(session_id);
CREATE INDEX IF NOT EXISTS idx_trip_calculations_type ON trip_calculations(calculation_type);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_api_requests_timestamp ON api_requests(timestamp);
CREATE INDEX IF NOT EXISTS idx_api_requests_user ON api_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_error_logs_timestamp ON error_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_pricing_history_route ON pricing_history(route_pricing_id);
CREATE INDEX IF NOT EXISTS idx_destination_popularity_destination ON destination_popularity(destination_id);
