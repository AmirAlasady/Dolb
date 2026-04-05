import time
import random

import requests


def get_current_weather(location: str) -> dict:
    """
    Gets the real, current weather for a specific location using the OpenWeatherMap API.
    
    Args:
        location: The city name, e.g., "San Francisco", "Tokyo".
        
    Returns:
        A dictionary containing the weather information or an error message.
    """
    api_key = "e80566bfe6ab0a0b69d30a2b8bc6bde6"
    base_url = "http://api.openweathermap.org/data/2.5/weather"
    
    print(f"EXECUTING REAL TOOL: get_current_weather for location='{location}'")

    if not api_key:
        print("ERROR: OPENWEATHERMAP_API_KEY not found in environment.")
        return {"error": "Weather service is not configured."}

    params = {
        "q": location,
        "appid": api_key,
        "units": "metric"  # For Celsius. Use "imperial" for Fahrenheit.
    }

    try:
        response = requests.get(base_url, params=params, timeout=10)
        # Raise an exception for bad status codes (4xx or 5xx)
        response.raise_for_status()
        
        data = response.json()
        
        # --- Parse the API response into a clean, simple dictionary ---
        weather_report = {
            "location": data.get("name", location),
            "temperature": f"{data['main']['temp']}°C",
            "feels_like": f"{data['main']['feels_like']}°C",
            "condition": data["weather"][0]["main"],
            "description": data["weather"][0]["description"].capitalize(),
            "humidity": f"{data['main']['humidity']}%",
            "wind_speed": f"{data['wind']['speed']} m/s"
        }
        
        print(f"SUCCESS: Retrieved weather for {location}: {weather_report}")
        return weather_report

    except requests.exceptions.HTTPError as http_err:
        # Handle specific HTTP errors, like 404 Not Found or 401 Unauthorized
        if response.status_code == 404:
            print(f"ERROR: City not found for location: {location}")
            return {"error": f"The city '{location}' could not be found."}
        elif response.status_code == 401:
            print("ERROR: Invalid OpenWeatherMap API key.")
            return {"error": "Authentication with the weather service failed. Please check the API key."}
        else:
            print(f"HTTP error occurred: {http_err}")
            return {"error": f"An HTTP error occurred: {response.status_code}"}
            
    except Exception as e:
        # Handle other errors like network issues
        print(f"An unexpected error occurred: {e}")
        return {"error": "An unexpected error occurred while contacting the weather service."}