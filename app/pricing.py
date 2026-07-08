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

from app.database import SessionLocal, init_db
from app.models import Place, Destination, RoutePricing
from app.fhe import compile_circuit, encrypt_value, decrypt_value, encryption_mode
from app.cache import pricing_cache
from app.fare_estimator import estimate_transport_fares

logger = logging.getLogger(__name__)

_DEFAULT_PLACE = "Default"
_DEFAULT_PRICING = {
    "hotel_cost_per_room_per_night": 2000,
    "people_per_room": 2,
    "cab_cost_per_day": 3000,
    "meal_cost_per_person_per_day": 700,
    "ticket_cost_per_person": 2500,
}

_PLACE_NAMES = [
    "Default",
    "Goa",
    "Manali",
    "Shimla",
    "Jaipur",
    "Kerala",
    "Latvaria",
]

_INITIAL_DATA = {
    "Default": dict(_DEFAULT_PRICING),
    "Goa":    {"hotel_cost_per_room_per_night": 3000, "people_per_room": 2, "cab_cost_per_day": 4000, "meal_cost_per_person_per_day": 800, "ticket_cost_per_person": 2500},
    "Manali": {"hotel_cost_per_room_per_night": 2500, "people_per_room": 2, "cab_cost_per_day": 5000, "meal_cost_per_person_per_day": 600, "ticket_cost_per_person": 2500},
    "Shimla": {"hotel_cost_per_room_per_night": 2200, "people_per_room": 2, "cab_cost_per_day": 4300, "meal_cost_per_person_per_day": 650, "ticket_cost_per_person": 2500},
    "Jaipur": {"hotel_cost_per_room_per_night": 1800, "people_per_room": 2, "cab_cost_per_day": 3000, "meal_cost_per_person_per_day": 600, "ticket_cost_per_person": 2500},
    "Kerala": {"hotel_cost_per_room_per_night": 2800, "people_per_room": 2, "cab_cost_per_day": 3700, "meal_cost_per_person_per_day": 750, "ticket_cost_per_person": 2500},
    "Latvaria": {"hotel_cost_per_room_per_night": 15000, "people_per_room": 1, "cab_cost_per_day": 3300, "meal_cost_per_person_per_day": 5000, "ticket_cost_per_person": 2500},
}


@contextmanager
def _db():
    init_db()
    tmp = SessionLocal()
    try:
        if tmp.query(RoutePricing).count() == 0:
            logger.info("Seeding initial pricing data into DB (first-run)")
            for place in _PLACE_NAMES:
                for destination, pricing in _INITIAL_DATA.items():
                    _seed_route(tmp, place, destination, pricing)
            tmp.commit()
    except Exception:
        tmp.rollback()
        raise
    finally:
        tmp.close()

    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _encrypt_row(pricing):
    return {
        "hotel_cost_enc":      encrypt_value(pricing["hotel_cost_per_room_per_night"]),
        "people_per_room_enc": encrypt_value(pricing["people_per_room"]),
        "cab_cost_enc":        encrypt_value(pricing["cab_cost_per_day"]),
        "meal_cost_enc":       encrypt_value(pricing["meal_cost_per_person_per_day"]),
        "ticket_cost_enc":     encrypt_value(pricing["ticket_cost_per_person"]),
    }


def _decrypt_route(row):
    return {
        "hotel_cost_per_room_per_night": decrypt_value(cast(bytes, row.hotel_cost_enc)),
        "people_per_room":               decrypt_value(cast(bytes, row.people_per_room_enc)),
        "cab_cost_per_day":              decrypt_value(cast(bytes, row.cab_cost_enc)),
        "meal_cost_per_person_per_day":  decrypt_value(cast(bytes, row.meal_cost_enc)),
        "ticket_cost_per_person":        decrypt_value(cast(bytes, row.ticket_cost_enc)),
    }


def _find_by_name(session, model, name):
    if not name:
        return None
    row = session.query(model).filter(model.name == name).first()
    if row is not None:
        return row
    lower_name = name.lower()
    return next(
        (r for r in session.query(model).all() if r.name.lower() == lower_name),
        None,
    )


def _get_or_create_place(session, name):
    place = _find_by_name(session, Place, name)
    if place is None:
        place = Place(name=name or _DEFAULT_PLACE)
        session.add(place)
        session.flush()
    return place


def _get_or_create_destination(session, name):
    dest = _find_by_name(session, Destination, name)
    if dest is None:
        dest = Destination(name=name or "Default")
        session.add(dest)
        session.flush()
    return dest


def _get_route(session, origin, destination):
    place = _find_by_name(session, Place, origin) or _find_by_name(session, Place, _DEFAULT_PLACE)
    dest = _find_by_name(session, Destination, destination) or _find_by_name(session, Destination, "Default")
    if place is None or dest is None:
        return None
    route = (
        session.query(RoutePricing)
        .filter(RoutePricing.place_id == place.id, RoutePricing.destination_id == dest.id)
        .first()
    )
    if route is not None:
        return route

    default_place = _find_by_name(session, Place, _DEFAULT_PLACE)
    if default_place is None:
        return None
    return (
        session.query(RoutePricing)
        .filter(RoutePricing.place_id == default_place.id, RoutePricing.destination_id == dest.id)
        .first()
    )


def _seed_route(session, origin, destination, pricing):
    place = _get_or_create_place(session, origin)
    dest = _get_or_create_destination(session, destination)
    route = (
        session.query(RoutePricing)
        .filter(RoutePricing.place_id == place.id, RoutePricing.destination_id == dest.id)
        .first()
    )
    if route is None:
        route = RoutePricing(place=place, destination=dest)
        session.add(route)
    for field, value in _encrypt_row(pricing).items():
        setattr(route, field, value)
    return route


def startup():
    mode = compile_circuit()
    logger.info("Encryption mode: %s", mode)

    init_db()
    logger.info("Database tables ready.")

    with _db() as session:
        if session.query(RoutePricing).count() == 0:
            logger.info("Seeding places, destinations, and route pricing…")
            for place in _PLACE_NAMES:
                for destination, pricing in _INITIAL_DATA.items():
                    _seed_route(session, place, destination, pricing)


def get_all_places():
    """Return all place (origin) names, for the admin dropdown."""
    cache_key = "places:all"
    cached = pricing_cache.get(cache_key)
    if cached is not None:
        return cached

    with _db() as session:
        rows = session.query(Place).order_by(Place.name).all()
        result = [row.name for row in rows]

    pricing_cache.set(cache_key, result)
    return result


def get_all_destinations(origin=None):
    cache_key = f"destinations:{origin or _DEFAULT_PLACE}"
    cached = pricing_cache.get(cache_key)
    if cached is not None:
        return cached

    with _db() as session:
        origin_name = origin or _DEFAULT_PLACE
        place = _find_by_name(session, Place, origin_name) or _get_or_create_place(session, _DEFAULT_PLACE)
        rows = (
            session.query(RoutePricing)
            .join(Destination)
            .filter(RoutePricing.place_id == place.id)
            .order_by(Destination.name)
            .all()
        )
        result = {row.destination.name: _decrypt_route(row) for row in rows}

    pricing_cache.set(cache_key, result)
    return result


def _get_exact_route(session, origin, destination):
    """Look up a route WITHOUT falling back to Default."""
    place = _find_by_name(session, Place, origin)
    dest = _find_by_name(session, Destination, destination)
    if place is None or dest is None:
        return None
    return (
        session.query(RoutePricing)
        .filter(RoutePricing.place_id == place.id, RoutePricing.destination_id == dest.id)
        .first()
    )


def get_route_pricing(origin, destination):
    cache_key = f"route:{origin or _DEFAULT_PLACE}:{destination}"
    cached = pricing_cache.get(cache_key)
    if cached is not None:
        return cached

    live_fetched = False

    with _db() as session:
        exact_route = _get_exact_route(session, origin, destination)

        if exact_route is not None:
            pricing = _decrypt_route(exact_route)
        else:
            fallback_route = _get_route(session, origin, destination)
            pricing = _decrypt_route(fallback_route) if fallback_route else dict(_DEFAULT_PRICING)

            if origin and origin != _DEFAULT_PLACE:
                fare = estimate_transport_fares(origin, destination)
                if fare.get("overall_avg"):
                    pricing = dict(pricing)
                    pricing["ticket_cost_per_person"] = int(fare["overall_avg"])
                    live_fetched = True
                    logger.info(
                        "Live fare fetched for %s -> %s: Rs %s (train avg %s, bus avg %s)",
                        origin, destination, fare["overall_avg"],
                        fare.get("train_avg"), fare.get("bus_avg"),
                    )
                _seed_route(session, origin, destination, pricing)

    if live_fetched:
        pricing_cache.set(cache_key, pricing)
        return pricing

    try:
        orig_ticket = int(pricing.get("ticket_cost_per_person", _DEFAULT_PRICING["ticket_cost_per_person"]))

        avg_cost = (pricing["hotel_cost_per_room_per_night"] +
                    pricing["meal_cost_per_person_per_day"] +
                    pricing["cab_cost_per_day"]) / 3
        avg_default = (_DEFAULT_PRICING["hotel_cost_per_room_per_night"] +
                       _DEFAULT_PRICING["meal_cost_per_person_per_day"] +
                       _DEFAULT_PRICING["cab_cost_per_day"]) / 3
        cost_ratio = avg_cost / avg_default

        derived_ticket = round(_DEFAULT_PRICING["ticket_cost_per_person"] * cost_ratio)
        pricing["ticket_cost_per_person"] = max(orig_ticket, int(derived_ticket))
    except Exception:
        pricing["ticket_cost_per_person"] = pricing.get("ticket_cost_per_person", _DEFAULT_PRICING["ticket_cost_per_person"])

    pricing_cache.set(cache_key, pricing)
    return pricing

def get_destination_pricing(destination, origin=_DEFAULT_PLACE):
    return get_route_pricing(origin, destination)


def upsert_destination(destination, pricing, origin=_DEFAULT_PLACE):
    """Create or update pricing for a specific origin -> destination route."""
    enc = _encrypt_row(pricing)

    with _db() as session:
        dest = _get_or_create_destination(session, destination)
        place = _get_or_create_place(session, origin)
        route = (
            session.query(RoutePricing)
            .filter(RoutePricing.place_id == place.id, RoutePricing.destination_id == dest.id)
            .first()
        )
        if route is None:
            route = RoutePricing(place=place, destination=dest)
            session.add(route)
        for field, value in enc.items():
            setattr(route, field, value)

    pricing_cache.clear()
    return pricing


def delete_destination(destination, origin=_DEFAULT_PLACE):
    """
    Delete pricing for a specific origin -> destination route only.
    Does NOT delete the Destination itself, so other origins' pricing
    for the same destination is left untouched.
    """
    if destination == "Default" and origin == "Default":
        return False

    with _db() as session:
        place = _find_by_name(session, Place, origin)
        dest = _find_by_name(session, Destination, destination)
        if place is None or dest is None:
            return False

        route = (
            session.query(RoutePricing)
            .filter(RoutePricing.place_id == place.id, RoutePricing.destination_id == dest.id)
            .first()
        )
        if route is None:
            return False
        session.delete(route)

    pricing_cache.clear()
    return True


def compare_destinations(destinations, num_people, num_days, num_nights=None, from_location=_DEFAULT_PLACE):
    results = [
        calculate_trip_cost(num_people, num_days, dest, from_location, num_nights)
        for dest in destinations
    ]
    results.sort(key=lambda x: x["grand_total"])
    return results


def calculate_trip_cost(num_people, num_days, destination="Default", from_location=_DEFAULT_PLACE, num_nights=None, kids_under_7=0):
    p = get_route_pricing(from_location, destination)

    total_people_for_rooms = num_people + kids_under_7
    people_paying_tickets = num_people

    rooms = math.ceil(total_people_for_rooms / p["people_per_room"])

    if num_nights is None or num_days == num_nights:
        billing_units = float(num_days)
    else:
        remaining_days = max(num_days - num_nights, 0)
        billing_units = float(num_nights) + remaining_days * 0.5

    hotel = rooms * p["hotel_cost_per_room_per_night"] * billing_units
    cab   = p["cab_cost_per_day"] * num_days
    meals = p["meal_cost_per_person_per_day"] * total_people_for_rooms * billing_units
    tickets = p["ticket_cost_per_person"] * people_paying_tickets

    return {
        "origin":            from_location,
        "destination":       destination,
        "num_people":        num_people,
        "kids_under_7":      kids_under_7,
        "total_people":      total_people_for_rooms,
        "num_days":          num_days,
        "num_nights":        num_nights if num_nights is not None else num_days,
        "billing_units":     billing_units,
        "rooms_needed":      rooms,
        "hotel_total":       round(hotel),
        "cab_total":         round(cab),
        "meals_total":       round(meals),
        "ticket_total":      round(tickets),
        "grand_total":       round(hotel + cab + meals + tickets),
    }


def calculate_multi_city_trip(num_people, itinerary, kids_under_7=0):
    grand_total = 0
    total_hotel = 0
    total_cab = 0
    total_meals = 0
    total_tickets = 0
    total_days = 0
    breakdown = []

    for leg in itinerary:
        dest = leg.get("destination", "Default")
        days = leg.get("days", 1)
        nights = leg.get("nights", days)
        total_days += days

        leg_cost = calculate_trip_cost(
            num_people, days, dest, _DEFAULT_PLACE, nights, kids_under_7
        )

        total_hotel += leg_cost["hotel_total"]
        total_cab += leg_cost["cab_total"]
        total_meals += leg_cost["meals_total"]
        total_tickets += leg_cost["ticket_total"]
        grand_total += leg_cost["grand_total"]

        breakdown.append(leg_cost)

    return {
        "num_people": num_people,
        "kids_under_7": kids_under_7,
        "total_people": num_people + kids_under_7,
        "total_destinations": len(itinerary),
        "total_days": total_days,
        "hotel_total": round(total_hotel),
        "cab_total": round(total_cab),
        "meals_total": round(total_meals),
        "ticket_total": round(total_tickets),
        "grand_total": round(grand_total),
        "breakdown": breakdown
    }