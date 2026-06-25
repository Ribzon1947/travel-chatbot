"""
Pricing data layer.
Storage:    SQLite via SQLAlchemy (chatbot.db)
Encryption: Zama FHE (concrete-python) — or AES-256-GCM on Windows
Cache:      In-memory TTL cache (5 min) with auto-eviction janitor
"""
import math
import logging
from contextlib import contextmanager

from app.database import SessionLocal, DestinationRow, init_db
from app.fhe import compile_circuit, encrypt_value, decrypt_value, encryption_mode
from app.cache import pricing_cache

logger = logging.getLogger(__name__)

_DEFAULT_PRICING = {
    "hotel_cost_per_room_per_night": 2000,
    "people_per_room": 2,
    "cab_cost_per_day": 3000,
    "meal_cost_per_person_per_day": 700,
}

_INITIAL_DATA: dict[str, dict] = {
    "Default": dict(_DEFAULT_PRICING),
    "Goa":    {"hotel_cost_per_room_per_night": 3000, "people_per_room": 2, "cab_cost_per_day": 4000, "meal_cost_per_person_per_day": 800},
    "Manali": {"hotel_cost_per_room_per_night": 2500, "people_per_room": 2, "cab_cost_per_day": 5000, "meal_cost_per_person_per_day": 600},
    "Shimla": {"hotel_cost_per_room_per_night": 2200, "people_per_room": 2, "cab_cost_per_day": 4300, "meal_cost_per_person_per_day": 650},
    "Jaipur": {"hotel_cost_per_room_per_night": 1800, "people_per_room": 2, "cab_cost_per_day": 3000, "meal_cost_per_person_per_day": 600},
    "Kerala": {"hotel_cost_per_room_per_night": 2800, "people_per_room": 2, "cab_cost_per_day": 3700, "meal_cost_per_person_per_day": 750},
}


# ── Internal helpers ──────────────────────────────────────────────────────────

@contextmanager
def _db():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _encrypt_row(pricing: dict) -> dict:
    return {
        "hotel_cost_enc":      encrypt_value(pricing["hotel_cost_per_room_per_night"]),
        "people_per_room_enc": encrypt_value(pricing["people_per_room"]),
        "cab_cost_enc":        encrypt_value(pricing["cab_cost_per_day"]),
        "meal_cost_enc":       encrypt_value(pricing["meal_cost_per_person_per_day"]),
    }


def _decrypt_row(row: DestinationRow) -> dict:
    return {
        "hotel_cost_per_room_per_night": decrypt_value(row.hotel_cost_enc),
        "people_per_room":               decrypt_value(row.people_per_room_enc),
        "cab_cost_per_day":              decrypt_value(row.cab_cost_enc),
        "meal_cost_per_person_per_day":  decrypt_value(row.meal_cost_enc),
    }


# ── Startup ───────────────────────────────────────────────────────────────────

def startup() -> None:
    """
    Called once when the app starts:
    1. Compile the Zama FHE circuit (self-compile).
    2. Create DB tables if they do not exist.
    3. Seed initial destination data if the table is empty.
    """
    mode = compile_circuit()
    logger.info("Encryption mode: %s", mode)

    init_db()
    logger.info("Database tables ready.")

    with _db() as session:
        if session.query(DestinationRow).count() == 0:
            logger.info("Seeding %d initial destinations…", len(_INITIAL_DATA))
            for name, pricing in _INITIAL_DATA.items():
                enc = _encrypt_row(pricing)
                session.add(DestinationRow(name=name, **enc))


# ── Public API ────────────────────────────────────────────────────────────────

def get_all_destinations() -> dict:
    cached = pricing_cache.get("__all__")
    if cached is not None:
        return cached

    with _db() as session:
        rows = session.query(DestinationRow).order_by(DestinationRow.name).all()
        result = {row.name: _decrypt_row(row) for row in rows}

    pricing_cache.set("__all__", result)
    return result


def get_destination_pricing(destination: str) -> dict:
    cache_key = f"dest:{destination}"
    cached = pricing_cache.get(cache_key)
    if cached is not None:
        return cached

    with _db() as session:
        row = (
            session.query(DestinationRow)
            .filter(DestinationRow.name == destination)
            .first()
        )
        if row is None:
            # Case-insensitive fallback
            row = next(
                (r for r in session.query(DestinationRow).all()
                 if r.name.lower() == destination.lower()),
                None,
            )
        pricing = _decrypt_row(row) if row else _get_default(session)

    pricing_cache.set(cache_key, pricing)
    return pricing


def _get_default(session) -> dict:
    row = session.query(DestinationRow).filter(DestinationRow.name == "Default").first()
    return _decrypt_row(row) if row else _DEFAULT_PRICING


def upsert_destination(destination: str, pricing: dict) -> dict:
    enc = _encrypt_row(pricing)

    with _db() as session:
        row = (
            session.query(DestinationRow)
            .filter(DestinationRow.name == destination)
            .first()
        )
        if row is None:
            row = DestinationRow(name=destination)
            session.add(row)
        for field, value in enc.items():
            setattr(row, field, value)

    pricing_cache.invalidate(f"dest:{destination}")
    pricing_cache.invalidate("__all__")
    return pricing


def delete_destination(destination: str) -> bool:
    if destination == "Default":
        return False

    with _db() as session:
        row = (
            session.query(DestinationRow)
            .filter(DestinationRow.name == destination)
            .first()
        )
        if row is None:
            return False
        session.delete(row)

    pricing_cache.invalidate(f"dest:{destination}")
    pricing_cache.invalidate("__all__")
    return True


# ── Calculation helpers (unchanged logic) ─────────────────────────────────────

def compare_destinations(
    destinations: list[str],
    num_people: int,
    num_days: int,
    num_nights: int | None = None,
) -> list[dict]:
    results = [
        calculate_trip_cost(num_people, num_days, dest, num_nights)
        for dest in destinations
    ]
    results.sort(key=lambda x: x["grand_total"])
    return results


def calculate_trip_cost(
    num_people: int,
    num_days: int,
    destination: str = "Default",
    num_nights: int | None = None,
) -> dict:
    p = get_destination_pricing(destination)
    rooms = math.ceil(num_people / p["people_per_room"])

    if num_nights is None or num_days == num_nights:
        billing_units = float(num_days)
    else:
        remaining_days = max(num_days - num_nights, 0)
        billing_units = float(num_nights) + remaining_days * 0.5

    hotel = rooms * p["hotel_cost_per_room_per_night"] * billing_units
    cab   = p["cab_cost_per_day"] * num_days
    meals = p["meal_cost_per_person_per_day"] * num_people * billing_units

    return {
        "destination":   destination,
        "num_people":    num_people,
        "num_days":      num_days,
        "num_nights":    num_nights if num_nights is not None else num_days,
        "billing_units": billing_units,
        "rooms_needed":  rooms,
        "hotel_total":   round(hotel),
        "cab_total":     round(cab),
        "meals_total":   round(meals),
        "grand_total":   round(hotel + cab + meals),
    }
