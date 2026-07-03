import json
import logging
from pathlib import Path

from app.database import init_db, SessionLocal
from app.fhe import compile_circuit, encrypt_value
from app.models import Destination, Place, RoutePricing

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]

_DEFAULT_PLACE = "Default"


def _encrypt_row(pricing: dict) -> dict:
    return {
        "hotel_cost_enc":      encrypt_value(pricing["hotel_cost_per_room_per_night"]),
        "people_per_room_enc": encrypt_value(pricing["people_per_room"]),
        "cab_cost_enc":        encrypt_value(pricing["cab_cost_per_day"]),
        "meal_cost_enc":       encrypt_value(pricing["meal_cost_per_person_per_day"]),
        "ticket_cost_enc":     encrypt_value(pricing["ticket_cost_per_person"]),
    }


def _find_by_name(session, model, name: str):
    if not name:
        return None
    row = session.query(model).filter(model.name == name).first()
    if row is not None:
        return row
    lower_name = name.lower()
    return next((r for r in session.query(model).all() if r.name.lower() == lower_name), None)


def _get_or_create_place(session, name: str) -> Place:
    place = _find_by_name(session, Place, name)
    if place is None:
        place = Place(name=name or _DEFAULT_PLACE)
        session.add(place)
        session.flush()
    return place


def _get_or_create_destination(session, name: str) -> Destination:
    dest = _find_by_name(session, Destination, name)
    if dest is None:
        dest = Destination(name=name or _DEFAULT_PLACE)
        session.add(dest)
        session.flush()
    return dest


def _upsert_route(session, origin: str, destination: str, pricing: dict) -> RoutePricing:
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


def main() -> None:
    compile_circuit()
    init_db()

    pricing_path = ROOT / "pricing_data.json"
    if not pricing_path.exists():
        raise FileNotFoundError(f"Missing pricing data: {pricing_path}")

    with pricing_path.open("r", encoding="utf-8") as handle:
        pricing_data = json.load(handle)

    place_names = ["Default"] + [name for name in pricing_data.keys() if name != "Default"]

    with SessionLocal() as session:
        logger.info("Seeding route pricing for %d origins and %d destinations...", len(place_names), len(pricing_data))
        for origin in place_names:
            for destination, pricing in pricing_data.items():
                _upsert_route(session, origin, destination, pricing)
        session.commit()

    logger.info("Route pricing seeding complete.")


if __name__ == "__main__":
    main()
