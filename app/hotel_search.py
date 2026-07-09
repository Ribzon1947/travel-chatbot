"""
Hotel Search Data Layer.
Handles fetching real-world data from the Google Places API, caching it locally
via SQLAlchemy, and providing an LLM-powered semantic RAG search over listings.

Pricing: real per-night rates come from Gemini + Google Search grounding
(estimate_live_hotel_price), fetched ONCE per hotel and cached -- not a
flat formula based on Google's price_level tier.

Performance: rate + phone lookups for NEW hotels are fetched CONCURRENTLY
(thread pool) instead of one-by-one, since each is a slow network call and
they are all independent of each other. DB writes stay sequential since a
SQLAlchemy session is not thread-safe.
"""

import json
import logging
import requests
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from google import genai
from app.config import get_settings
from app.database import SessionLocal
from app.models import HotelListing
from app.fare_estimator import estimate_live_hotel_price

logger = logging.getLogger(__name__)

_MAX_WORKERS = 8  # concurrent network calls at once for rate/phone lookups


class HotelSearchError(Exception):
    """Raised when Google Places API cannot return real hotel data."""
    pass


def _fetch_rate_only(name, city):
    try:
        return estimate_live_hotel_price(name, city)
    except Exception as e:
        logger.warning("Live rate lookup failed for %s in %s: %s", name, city, e)
        return None


def _fetch_place_phone(place_id, api_key):
    """Fetch a hotel's contact number via Google Place Details."""
    if not place_id:
        return None
    try:
        url = "https://maps.googleapis.com/maps/api/place/details/json"
        params = {"place_id": place_id, "fields": "formatted_phone_number", "key": api_key}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("result", {}).get("formatted_phone_number")
    except Exception as e:
        logger.warning("Phone lookup failed for place_id %s: %s", place_id, e)
        return None


def _fetch_details_concurrently(pending, city, api_key, need_phone):
    """
    pending: list of dicts, each with at least {"name", "place_id"} for hotels
    that need a fresh rate (and optionally phone) lookup.
    Returns: dict name -> {"rate": int|None, "phone": str|None}
    Runs all lookups in parallel via a thread pool since each is a slow,
    independent network call.
    """
    results = {}
    if not pending:
        return results

    def _fetch_one(item):
        name = item["name"]
        rate = _fetch_rate_only(name, city)
        phone = _fetch_place_phone(item.get("place_id"), api_key) if need_phone else None
        return name, rate, phone

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = [executor.submit(_fetch_one, item) for item in pending]
        for future in as_completed(futures):
            try:
                name, rate, phone = future.result()
                results[name] = {"rate": rate, "phone": phone}
            except Exception as e:
                logger.warning("Concurrent hotel detail fetch failed: %s", e)

    return results


def search_hotels(city, hotel_name=None):
    """
    Searches for hotels in a specific city.
    Checks the local database cache first. If no records are found (or a specific
    hotel name lookup is requested), it queries the Google Places API and updates the cache.
    Raises HotelSearchError if Google rejects the request -- NEVER fabricates data.
    """
    session = SessionLocal()
    try:
        if not hotel_name:
            cached_rows = session.query(HotelListing).filter(HotelListing.city.ilike(city)).all()
            if cached_rows:
                return [
                    {
                        "name": h.name,
                        "city": h.city,
                        "address": h.description,
                        "description": h.description,
                        "amenities": h.amenities or "WiFi, AC, Room Service",
                        "rate_per_night": h.last_rate_seen,
                        "estimated_rate": h.last_rate_seen,
                        "rating": getattr(h, "rating", None),
                    }
                    for h in cached_rows
                ]

        settings = get_settings()
        api_key = getattr(settings, "google_maps_key", None) or settings.google_ai_key

        if not api_key:
            raise HotelSearchError(
                "No Google API key configured (set GOOGLE_MAPS_KEY or GOOGLE_AI_KEY on Render)."
            )

        search_query = f"{hotel_name} in {city}" if hotel_name else f"hotels in {city}"
        url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
        params = {"query": search_query, "key": api_key}

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
        except Exception as api_err:
            raise HotelSearchError(f"Google Places API request failed: {api_err}") from api_err

        status = data.get("status", "OK")
        if status in ("REQUEST_DENIED", "INVALID_REQUEST", "OVER_QUERY_LIMIT"):
            error_msg = data.get(
                "error_message",
                "Check that the API key is correct, billing is enabled, and 'Places API' (legacy) is enabled in Google Cloud Console."
            )
            raise HotelSearchError(f"Google Places API error ({status}): {error_msg}")

        results = data.get("results", [])
        if status == "ZERO_RESULTS" or not results:
            return []  # Genuinely no hotels found -- not an error, and NOT fake data.

        # Look up existing cache rows in ONE query instead of one-per-hotel
        names = [item.get("name") for item in results]
        existing_rows = session.query(HotelListing).filter(
            HotelListing.city.ilike(city), HotelListing.name.in_(names)
        ).all()
        existing_by_name = {row.name: row for row in existing_rows}

        # Figure out which hotels genuinely need a fresh (slow) rate lookup
        pending = [
            {"name": item.get("name"), "place_id": item.get("place_id")}
            for item in results
            if not (existing_by_name.get(item.get("name")) and existing_by_name[item.get("name")].last_rate_seen)
        ]
        fetched = _fetch_details_concurrently(pending, city, api_key, need_phone=False)

        hotels_list = []
        for item in results:
            name = item.get("name")
            address = item.get("formatted_address", "")
            rating = item.get("rating")
            price_level = item.get("price_level", 2)

            existing_listing = existing_by_name.get(name)
            if existing_listing and existing_listing.last_rate_seen:
                real_rate = existing_listing.last_rate_seen
            else:
                real_rate = fetched.get(name, {}).get("rate")

            if existing_listing:
                existing_listing.description = address
                existing_listing.last_rate_seen = real_rate
                existing_listing.last_updated = datetime.utcnow()
                if hasattr(existing_listing, "rating"):
                    existing_listing.rating = rating
                db_hotel = existing_listing
            else:
                db_hotel = HotelListing(
                    city=city,
                    name=name,
                    description=address,
                    amenities="WiFi, AC, Pool, Parking" if price_level and price_level >= 3 else "WiFi, AC",
                    last_rate_seen=real_rate,
                    last_updated=datetime.utcnow()
                )
                if hasattr(db_hotel, "rating"):
                    db_hotel.rating = rating
                session.add(db_hotel)

            hotels_list.append({
                "name": name,
                "city": city,
                "address": address,
                "description": address,
                "amenities": db_hotel.amenities,
                "rate_per_night": real_rate,
                "estimated_rate": real_rate,
                "rating": rating,
            })

        session.commit()
        return hotels_list

    except HotelSearchError:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        logger.error(f"Error occurred during search_hotels: {e}")
        raise HotelSearchError(f"Unexpected error during hotel search: {e}") from e
    finally:
        session.close()


def search_hotels_page(city, page_token=None):
    """
    Paginated hotel search using Google Places Text Search's native pagination.
    Returns (hotels_list, next_page_token). Real per-night rates and phone
    numbers for NEW hotels are fetched concurrently, not one-by-one.
    """
    settings = get_settings()
    api_key = getattr(settings, "google_maps_key", None) or settings.google_ai_key
    if not api_key:
        raise HotelSearchError("No Google API key configured (set GOOGLE_MAPS_KEY or GOOGLE_AI_KEY on Render).")

    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {"key": api_key}
    if page_token:
        params["pagetoken"] = page_token
    else:
        params["query"] = f"hotels in {city}"

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        
        if page_token and data.get("status") == "INVALID_REQUEST":
            for delay in (2, 3, 5):
                time.sleep(delay)
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                if data.get("status") != "INVALID_REQUEST":
                    break

    except Exception as api_err:
        raise HotelSearchError(f"Google Places API request failed: {api_err}") from api_err

    status = data.get("status", "OK")
    if status in ("REQUEST_DENIED", "INVALID_REQUEST", "OVER_QUERY_LIMIT"):
        if page_token and status == "INVALID_REQUEST":
            error_msg = "The pagination token expired or wasn't ready yet. Please try clicking Next again."
        else:
            error_msg = data.get("error_message", "Check API key, billing, and that 'Places API' (legacy) is enabled.")
        raise HotelSearchError(f"Google Places API error ({status}): {error_msg}")

    results = data.get("results", [])
    next_page_token = data.get("next_page_token")

    session = SessionLocal()
    hotels_list = []
    try:
        names = [item.get("name") for item in results]
        existing_rows = session.query(HotelListing).filter(
            HotelListing.city.ilike(city), HotelListing.name.in_(names)
        ).all()
        existing_by_name = {row.name: row for row in existing_rows}

        # Only fetch rate/phone concurrently for hotels missing that data
        pending = [
            {"name": item.get("name"), "place_id": item.get("place_id")}
            for item in results
            if not (
                existing_by_name.get(item.get("name"))
                and existing_by_name[item.get("name")].last_rate_seen
                and getattr(existing_by_name[item.get("name")], "phone", None)
            )
        ]
        fetched = _fetch_details_concurrently(pending, city, api_key, need_phone=True)

        for item in results:
            name = item.get("name")
            address = item.get("formatted_address", "")
            rating = item.get("rating")
            price_level = item.get("price_level", 2)

            existing = existing_by_name.get(name)
            if existing and existing.last_rate_seen:
                real_rate = existing.last_rate_seen
            else:
                real_rate = fetched.get(name, {}).get("rate")

            if existing and getattr(existing, "phone", None):
                phone = existing.phone
            else:
                phone = fetched.get(name, {}).get("phone")

            if existing:
                existing.description = address
                existing.last_rate_seen = real_rate
                existing.last_updated = datetime.utcnow()
                existing.phone = phone
                if hasattr(existing, "rating"):
                    existing.rating = rating
                db_hotel = existing
            else:
                db_hotel = HotelListing(
                    city=city, name=name, description=address,
                    amenities="WiFi, AC, Pool, Parking" if price_level and price_level >= 3 else "WiFi, AC",
                    last_rate_seen=real_rate, phone=phone,
                    last_updated=datetime.utcnow()
                )
                if hasattr(db_hotel, "rating"):
                    db_hotel.rating = rating
                session.add(db_hotel)

            hotels_list.append({
                "name": name, "city": city, "address": address, "description": address,
                "amenities": db_hotel.amenities, "rate_per_night": real_rate,
                "estimated_rate": real_rate, "rating": rating, "phone": phone or "N/A",
            })

        session.commit()
    except Exception as e:
        session.rollback()
        raise HotelSearchError(f"Error caching hotel page: {e}") from e
    finally:
        session.close()

    return hotels_list, next_page_token


def semantic_hotel_search(query, city):
    """
    Performs an intelligent, semantic RAG search over cached hotels.
    Uses Gemini to filter and rank properties matching user criteria.
    """
    session = SessionLocal()
    try:
        cached_rows = session.query(HotelListing).filter(HotelListing.city.ilike(city)).all()
        if not cached_rows:
            search_hotels(city)  # raises HotelSearchError if Google rejects it -- NEVER fake data
            cached_rows = session.query(HotelListing).filter(HotelListing.city.ilike(city)).all()

        if not cached_rows:
            return []

        hotels_pool = []
        hotel_lookup = {}
        for h in cached_rows:
            hotel_dict = {
                "name": h.name,
                "address": h.description,
                "amenities": h.amenities or "WiFi",
                "rate_per_night": h.last_rate_seen,
                "rating": getattr(h, "rating", None)
            }
            hotels_pool.append(hotel_dict)
            hotel_lookup[h.name.lower().strip()] = hotel_dict

        settings = get_settings()
        if not settings.google_ai_key:
            logger.warning("Google AI key missing. Falling back to keyword search.")
            return _fallback_keyword_search(hotels_pool, query)

        try:
            client = genai.Client(api_key=settings.google_ai_key)

            prompt = f"""
            You are a meticulous travel search assistant.
            Analyze the user's preference query: "{query}"

            Filter and sort the following hotel listings in {city} that best match their description:
            {json.dumps(hotels_pool, indent=2)}

            Respond strictly with a valid JSON array containing the exact names of matching hotels, ordered from best match to worst match.
            Example Response: ["Hotel Alpha", "Hotel Beta"]
            Do not provide any markdown block formatting code, explanation, or extra characters.
            """

            response = client.models.generate_content(
                model=settings.agent_model,
                contents=prompt
            )

            raw_text = response.text.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]

            matched_names = json.loads(raw_text.strip())

            semantic_results = []
            for name in matched_names:
                key = name.lower().strip()
                if key in hotel_lookup:
                    semantic_results.append(hotel_lookup[key])

            if semantic_results:
                return semantic_results

        except Exception as ai_err:
            logger.error(f"Gemini semantic ranking failed, switching to fallback: {ai_err}")

        return _fallback_keyword_search(hotels_pool, query)

    finally:
        session.close()


def _fallback_keyword_search(hotels, query):
    """Fallback text similarity token matching -- still real cached hotels, just unranked by Gemini."""
    scored_hotels = []
    tokens = query.lower().split()

    for h in hotels:
        score = 0
        searchable_blob = f"{h['name']} {h['address']} {h['amenities']}".lower()
        for token in tokens:
            if token in searchable_blob:
                score += 1
        if score > 0 or not tokens:
            scored_hotels.append((score, h))

    scored_hotels.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored_hotels]