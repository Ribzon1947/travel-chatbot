import os
import google.generativeai as genai
from typing import Optional

# Configure the Gemini API key from your Render environment variables
# Ensure you have 'GEMINI_API_KEY' set in your Render dashboard under Environment -> Secret Files/Variables
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

def estimate_transport_fares(origin: str, destination: str) -> Optional[str]:
    """
    Uses Gemini to fetch live or estimated ticket fares for travel routes.
    """
    if not api_key:
         return "Error: Gemini API key is missing from environment variables."

    try:
        # Using the recommended model for general text and data retrieval tasks
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = (
            f"Provide a rough estimate of current transport fares (flights, trains, or buses) "
            f"for traveling from {origin} to {destination}. Include average prices in USD or "
            f"local currency, and mention the standard modes of transport available for this route. "
            f"Keep the response concise and helpful for a traveler."
        )
        
        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        # Catch errors so the chatbot doesn't completely crash if the API fails
        print(f"Error fetching fares: {e}")
        return "I'm sorry, I couldn't fetch the fare estimates for that route right now. Please try again later."