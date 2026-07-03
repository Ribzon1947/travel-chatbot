# Chatbot SQL Database Project

This folder contains the standalone SQL schema for the Travel Chatbot relational database.

## What it does

- Defines the schema for `places`, `destinations`, and `route_pricing`.
- Keeps the SQL schema separate from `app/database.py`.
- Allows the chatbot app to initialize the database from SQL instead of Python-generated DDL.

## How to initialize

### SQLite

```bash
sqlite3 ./chatbot.db < schema.sql
```

### PostgreSQL

```bash
psql "$DATABASE_URL" -f schema.sql
```

## Notes

- The chatbot application reads `DATABASE_URL` from the environment.
- `app/database.py` now loads `database/schema.sql` for schema initialization.
- Route pricing seeding still happens in Python, but the table creation is owned by this SQL project.
