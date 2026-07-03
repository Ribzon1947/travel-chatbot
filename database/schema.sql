-- Schema for the Travel Chatbot relational database
-- This SQL file lives in the chatbot project and is used to initialize the database schema.

CREATE TABLE IF NOT EXISTS places (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(128) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS destinations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(128) NOT NULL UNIQUE
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
    updated_at DATETIME,
    FOREIGN KEY(place_id) REFERENCES places(id),
    FOREIGN KEY(destination_id) REFERENCES destinations(id),
    UNIQUE(place_id, destination_id)
);
