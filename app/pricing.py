import math
import json
import os
from pathlib import Path

_GCS_BUCKET = os.environ.get("GCS_BUCKET")
_GCS_BLOB   = "pricing_data.json"

# DATA_DIR lets Render Disk (or any local dir) persist pricing data
_DATA_DIR  = os.environ.get("DATA_DIR")
_DATA_FILE = Path(_DATA_DIR) / "pricing_data.json" if _DATA_DIR else Path(__file__).parent.parent / "pricing_data.json"

_DEFAULT_PRICING = {
    "hotel_cost_per_room_per_night": 2000,
    "people_per_room": 2,
    "cab_cost_per_day": 3000,
    "meal_cost_per_person_per_day": 700,
}

_INITIAL_DATA = {
    "Default": dict(_DEFAULT_PRICING),
    "Goa":    {"hotel_cost_per_room_per_night": 3000, "people_per_room": 2, "cab_cost_per_day": 4000, "meal_cost_per_person_per_day": 800},
    "Manali": {"hotel_cost_per_room_per_night": 2500, "people_per_room": 2, "cab_cost_per_day": 5000, "meal_cost_per_person_per_day": 600},
    "Shimla": {"hotel_cost_per_room_per_night": 2200, "people_per_room": 2, "cab_cost_per_day": 4300, "meal_cost_per_person_per_day": 650},
    "Jaipur": {"hotel_cost_per_room_per_night": 1800, "people_per_room": 2, "cab_cost_per_day": 3000, "meal_cost_per_person_per_day": 600},
    "Kerala": {"hotel_cost_per_room_per_night": 2800, "people_per_room": 2, "cab_cost_per_day": 3700, "meal_cost_per_person_per_day": 750},
}


def _gcs_client():
    from google.cloud import storage
    return storage.Client()


def _load() -> dict:
    if _GCS_BUCKET:
        blob = _gcs_client().bucket(_GCS_BUCKET).blob(_GCS_BLOB)
        if blob.exists():
            return json.loads(blob.download_as_text())
        _save(_INITIAL_DATA)
        return dict(_INITIAL_DATA)

    if _DATA_FILE.exists():
        with open(_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    _save(_INITIAL_DATA)
    return dict(_INITIAL_DATA)


def _save(data: dict) -> None:
    if _GCS_BUCKET:
        blob = _gcs_client().bucket(_GCS_BUCKET).blob(_GCS_BLOB)
        blob.upload_from_string(
            json.dumps(data, indent=2, ensure_ascii=False),
            content_type="application/json",
        )
        return

    with open(_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_all_destinations() -> dict:
    return _load()


def get_destination_pricing(destination: str) -> dict:
    data = _load()
    if destination in data:
        return data[destination]
    for key, val in data.items():
        if key.lower() == destination.lower():
            return val
    return data.get("Default", _DEFAULT_PRICING)


def upsert_destination(destination: str, pricing: dict) -> dict:
    data = _load()
    data[destination] = pricing
    _save(data)
    return data[destination]


def delete_destination(destination: str) -> bool:
    if destination == "Default":
        return False
    data = _load()
    if destination not in data:
        return False
    del data[destination]
    _save(data)
    return True


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
        "destination":    destination,
        "num_people":     num_people,
        "num_days":       num_days,
        "num_nights":     num_nights if num_nights is not None else num_days,
        "billing_units":  billing_units,
        "rooms_needed":   rooms,
        "hotel_total":    round(hotel),
        "cab_total":      round(cab),
        "meals_total":    round(meals),
        "grand_total":    round(hotel + cab + meals),
    }
