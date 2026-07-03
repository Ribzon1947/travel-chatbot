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

## Seeding encrypted route pricing

Run the Python seeder from the chatbot project root:

```bash
python database/seed.py
```

This script will:

- compile the FHE circuit with `app/fhe.py`
- create the tables from `database/schema.sql`
- read pricing values from `pricing_data.json`
- encrypt each route cost field
- insert origin-destination rows into `places`, `destinations`, and `route_pricing`

## Notes

- The chatbot application reads `DATABASE_URL` from the environment.
- `app/database.py` now loads `database/schema.sql` for schema initialization.
- Route pricing seeding now has a dedicated Python script that produces encrypted route rows.
