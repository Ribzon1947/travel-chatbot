import os
import google.generativeai as genai
from typing import Dict, Any

# Configure the Gemini API key from your Render environment variables
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

def estimate_transport_fares(origin: str, destination: str) -> Dict[str, Any]:
    """
    Uses Gemini to fetch live or estimated ticket fares for travel routes.
    Returns a dictionary to satisfy the type requirements in chatbot.py.
    """
    if not api_key:
         return {"error": "Gemini API key is missing from environment variables."}

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = (
            f"Provide a rough estimate of current transport fares (flights, trains, or buses) "
            f"for traveling from {origin} to {destination}. Include average prices in USD or "
            f"local currency, and mention the standard modes of transport available for this route. "
            f"Keep the response concise and helpful for a traveler."
        )
        
        response = model.generate_content(prompt)
        
        # Returning a dictionary to fix the Pylance type mismatch
        return {
            "status": "success",
            "estimate": response.text
        }

    except Exception as e:
        print(f"Error fetching fares: {e}")
        return {
            "status": "error",
            "error": "I'm sorry, I couldn't fetch the fare estimates for that route right now."
        }