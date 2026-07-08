"""
Live Estimation Layer via Gemini + Google Search Grounding.
Handles dynamic web searches for real-time ticket costs and hotel pricing.
"""

import json
import logging
import os
import re

from google import genai
from google.genai import types

from app.config import get_settings

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        key = get_settings().google_ai_key
        if not key:
            raise RuntimeError("GOOGLE_AI_KEY is not configured. Add it in Render → Environment.")
        _client = genai.Client(api_key=key)
    return _client


def estimate_transport_fares(origin: str, destination: str) -> dict:
    """
    Uses Gemini with Google Search grounding to find CURRENT train and bus
    fares between two cities -- a real web search, not a guess.
    """
    client = _get_client()
    settings = get_settings()

    prompt = f"""Search for current one-way train and bus fares from {origin} to {destination} in India.

Return ONLY a JSON object in this exact format, nothing else, no markdown fences:
{{"train_fares": [<fare numbers in INR>], "bus_fares": [<fare numbers in INR>], "train_avg": <integer>, "bus_avg": <integer>, "overall_avg": <integer>, "sources": [<source names>]}}

If you cannot find fares for one mode, use an empty list and 0 for its average."""

    try:
        response = client.models.generate_content(
            model=settings.agent_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        text = (response.text or "").strip()
        text = re.sub(r"^```json\s*|\s*```$", "", text, flags=re.MULTILINE).strip()

        result = json.loads(text)
        result.setdefault("origin", origin)
        result.setdefault("destination", destination)
        return result

    except Exception as e:
        logger.warning("Fare estimation failed for %s -> %s: %s", origin, destination, e)
        return {
            "error": f"Could not estimate fares: {e}",
            "train_fares": [],
            "bus_fares": [],
            "train_avg": 0,
            "bus_avg": 0,
            "overall_avg": 0,
            "sources": [],
            "origin": origin,
            "destination": destination,
        }


def estimate_live_hotel_price(hotel_name: str, city: str) -> int:
    """Uses Gemini with Google Search grounding to find a real current room rate."""
    client = _get_client()
    settings = get_settings()

    prompt = f"""
    Search for the current average nightly room rate for {hotel_name} in {city}, India.
    Return ONLY a single integer representing the price in INR (Rupees). 
    Do not include symbols, commas, markdown, or extra text. Example: 7500
    If you cannot find it, return 0.
    """
    try:
        response = client.models.generate_content(
            model=settings.agent_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        
        text = (response.text or "").strip()
        # Find the first sequence of numbers in the response text safely
        match = re.search(r"\d+", text)
        if match:
            price = int(match.group())
            return price if price > 0 else 3600
        
        return 3600
    except Exception as e:
        logger.warning("Hotel price estimation failed for %s in %s: %s", hotel_name, city, e)
        return 3600  # Fallback default if search or parsing fails