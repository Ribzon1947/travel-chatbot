"""
Hotel Search Data Layer.
Handles fetching real-world data from the Google Places API, caching it locally 
via SQLAlchemy, and providing an LLM-powered semantic RAG search over listings.
"""

import json
import logging
import requests
from datetime import datetime

from google import genai
from app.config import get_settings
from app.database import SessionLocal
from app.models import HotelListing

logger = logging.getLogger(__name__)


def search_hotels(city: str, hotel_name: str | None = None) -> list:
    """
    Searches for hotels in a specific city. 
    Checks the local database cache first. If no records are found (or a specific 
    hotel name lookup is requested), it queries the Google Places API and updates the cache.
    """
    session = SessionLocal()
    try:
        # 1. Check local cache first for a general city search
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
                        "rating": getattr(h, "rating", 4.2),
                    }
                    for h in cached_rows
                ]

        # 2. Cache miss or targeted lookup: Fetch fresh data from Google Places API
        settings = get_settings()
        api_key = getattr(settings, "google_maps_key", None) or settings.google_ai_key

        results = []
        status = "OK"
        
        if not api_key:
            logger.warning("No API key configured for Google Places search. Switching to fallback.")
            status = "MISSING_KEY"
        else:
            search_query = f"{hotel_name} in {city}" if hotel_name else f"hotels in {city}"
            url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
            params = {"query": search_query, "key": api_key}

            try:
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                status = data.get("status", "OK")
                if status in ("REQUEST_DENIED", "INVALID_REQUEST", "OVER_QUERY_LIMIT"):
                    # CRITICAL DIAGNOSTIC: Print the explicit error from Google to the terminal
                    logger.error(f"❌ Google Places API Error ({status}): {data.get('error_message', 'Check console billing/permissions')}")
                else:
                    results = data.get("results", [])
            except Exception as api_err:
                logger.error(f"Google Places API request failed: {api_err}")
                status = "FETCH_ERROR"

        # 3. Smart Local Testing Fallback 
        # If Google rejects the key or it's unconfigured, generate clean mock entries so the UI works
        if not results and status != "ZERO_RESULTS":
            logger.warning(f"⚠️ Generating sandbox hotel listings for '{city}' to allow offline testing.")
            results = [
                {
                    "name": f"Grand Grand Palazzo {city}",
                    "formatted_address": f"12 Marine Drive, {city}, India",
                    "rating": 4.7,
                    "price_level": 3
                },
                {
                    "name": f"Sea Breeze Elite Resort & Spa",
                    "formatted_address": f"88 Beach Road, {city}, India",
                    "rating": 4.3,
                    "price_level": 4
                },
                {
                    "name": f"Starlight Comfort Stay",
                    "formatted_address": f"404 Central Avenue, {city}, India",
                    "rating": 3.9,
                    "price_level": 1
                }
            ]

        hotels_list = []
        for item in results:
            name = item.get("name")
            address = item.get("formatted_address", "")
            rating = item.get("rating", 4.0)
            price_level = item.get("price_level", 2)

            # Generate baseline rate based on Google's tier structure (1-4)
            estimated_rate = (price_level if price_level > 0 else 2) * 1800

            # Check for duplicates in the DB to perform an upsert
            existing_listing = session.query(HotelListing).filter(
                HotelListing.city.ilike(city), 
                HotelListing.name.ilike(name)
            ).first()

            if existing_listing:
                existing_listing.description = address
                existing_listing.last_rate_seen = estimated_rate
                existing_listing.last_updated = datetime.utcnow()
                if hasattr(existing_listing, "rating"):
                    existing_listing.rating = rating
                db_hotel = existing_listing
            else:
                db_hotel = HotelListing(
                    city=city,
                    name=name,
                    description=address,
                    amenities="WiFi, AC, Pool, Parking" if price_level >= 3 else "WiFi, AC",
                    last_rate_seen=estimated_rate,
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
                "rate_per_night": estimated_rate,
                "estimated_rate": estimated_rate,
                "rating": rating,
            })

        session.commit()
        return hotels_list

    except Exception as e:
        session.rollback()
        logger.error(f"Error occurred during search_hotels: {e}")
        return []
    finally:
        session.close()


def semantic_hotel_search(query: str, city: str) -> list:
    """
    Performs an intelligent, semantic RAG search over cached hotels.
    Uses Gemini to filter and rank properties matching user criteria.
    """
    session = SessionLocal()
    try:
        cached_rows = session.query(HotelListing).filter(HotelListing.city.ilike(city)).all()
        if not cached_rows:
            search_hotels(city)
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
                "rate_per_night": h.last_rate_seen or 2500,
                "rating": getattr(h, "rating", 4.0)
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


def _fallback_keyword_search(hotels: list, query: str) -> list:
    """Fallback text similarity token matching."""
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