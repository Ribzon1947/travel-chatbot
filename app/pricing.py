"""
Pricing data layer.
Storage:    SQLite via SQLAlchemy (chatbot.db)
Encryption: Zama FHE (concrete-python) — or AES-256-GCM on Windows
Cache:      In-memory TTL cache (5 min) with auto-eviction janitor
"""
import math
import logging
from contextlib import contextmanager
from typing import cast

from app.database import SessionLocal, DestinationRow, init_db
from app.fhe import compile_circuit, encrypt_value, decrypt_value, encryption_mode
from app.cache import pricing_cache

logger = logging.getLogger(__name__)

_DEFAULT_PRICING = {
    "hotel_cost_per_room_per_night": 2000,
    "people_per_room": 2,
    "cab_cost_per_day": 3000,
    "meal_cost_per_person_per_day": 700,
    "ticket_cost_per_person": 2500,
}

_INITIAL_DATA: dict[str, dict] = {
    "Default": dict(_DEFAULT_PRICING),
    "Goa":    {"hotel_cost_per_room_per_night": 3000, "people_per_room": 2, "cab_cost_per_day": 4000, "meal_cost_per_person_per_day": 800, "ticket_cost_per_person": 2500},
    "Manali": {"hotel_cost_per_room_per_night": 2500, "people_per_room": 2, "cab_cost_per_day": 5000, "meal_cost_per_person_per_day": 600, "ticket_cost_per_person": 2500},
    "Shimla": {"hotel_cost_per_room_per_night": 2200, "people_per_room": 2, "cab_cost_per_day": 4300, "meal_cost_per_person_per_day": 650, "ticket_cost_per_person": 2500},
    "Jaipur": {"hotel_cost_per_room_per_night": 1800, "people_per_room": 2, "cab_cost_per_day": 3000, "meal_cost_per_person_per_day": 600, "ticket_cost_per_person": 2500},
    "Kerala": {"hotel_cost_per_room_per_night": 2800, "people_per_room": 2, "cab_cost_per_day": 3700, "meal_cost_per_person_per_day": 750, "ticket_cost_per_person": 2500},
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
        "ticket_cost_enc":     encrypt_value(pricing["ticket_cost_per_person"]),
    }


def _decrypt_row(row: DestinationRow) -> dict:
    return {
        "hotel_cost_per_room_per_night": decrypt_value(cast(bytes, row.hotel_cost_enc)),
        "people_per_room":               decrypt_value(cast(bytes, row.people_per_room_enc)),
        "cab_cost_per_day":              decrypt_value(cast(bytes, row.cab_cost_enc)),
        "meal_cost_per_person_per_day":  decrypt_value(cast(bytes, row.meal_cost_enc)),
        "ticket_cost_per_person":        decrypt_value(cast(bytes, row.ticket_cost_enc)),
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
                row = DestinationRow(name=name)
                row.hotel_cost_enc = enc["hotel_cost_enc"]
                row.people_per_room_enc = enc["people_per_room_enc"]
                row.cab_cost_enc = enc["cab_cost_enc"]
                row.meal_cost_enc = enc["meal_cost_enc"]
                row.ticket_cost_enc = enc["ticket_cost_enc"]
                session.add(row)


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
    tickets = p["ticket_cost_per_person"] * num_people

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
        "ticket_total":  round(tickets),
        "grand_total":   round(hotel + cab + meals + tickets),
    }

def calculate_multi_city_trip(
    num_people: int,
    itinerary: list[dict]
) -> dict:
    """
    itinerary format: [{"destination": "Goa", "days": 3, "nights": 3}, ...]
    """
    grand_total = 0
    total_hotel = 0
    total_cab = 0
    total_meals = 0
    total_tickets = 0
    breakdown = []

    for leg in itinerary:
        dest = leg.get("destination", "Default")
        days = leg.get("days", 1)
        nights = leg.get("nights", days)

        # Reuse your existing single-leg calculator for consistency
        leg_cost = calculate_trip_cost(num_people, days, dest, nights)
        
        # Aggregate totals
        total_hotel += leg_cost["hotel_total"]
        total_cab += leg_cost["cab_total"]
        total_meals += leg_cost["meals_total"]
        total_tickets += leg_cost["ticket_total"]
        grand_total += leg_cost["grand_total"]

        breakdown.append(leg_cost)

    return {
        "num_people": num_people,
        "total_destinations": len(itinerary),
        "total_days": sum(leg.get("days", 0) for leg in itinerary),
        "hotel_total": total_hotel,
        "cab_total": total_cab,
        "meals_total": total_meals,
        "ticket_total": total_tickets,
        "grand_total": grand_total,
        "breakdown": breakdown
    }