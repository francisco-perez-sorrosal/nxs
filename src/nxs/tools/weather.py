"""Weather forecast tool using Open-Meteo API.

This module provides a function to retrieve weather forecasts for any location
using the free Open-Meteo API (no API key required).
"""

import requests
from datetime import datetime


def get_weather(location: str, date: str, unit: str = "C") -> dict:
    """Retrieve weather forecast for a location and date using the Open-Meteo API.

    Args:
        location: Place name (e.g., "New York", "San Francisco").
        date: Date as YYYY-MM-DD.
        unit: "C" for Celsius (default), "F" for Fahrenheit.

    Returns:
        Success:
            {
                "status": "success",
                "location": "...",
                "date": "...",
                "temperature": {"max": 18.2, "min": 10.5},
                "unit": "C",
                "condition": "Partly cloudy"
            }

        Error:
            {"status": "error", "error_message": "..."}
    """

    # Validate date format
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return {"status": "error", "error_message": "Invalid date format. Use YYYY-MM-DD."}

    # Normalize unit
    unit = unit.upper().strip()
    if unit not in ("C", "F"):
        return {"status": "error", "error_message": "Unit must be 'C' or 'F'."}

    # 1. Geocode location (Open-Meteo free geocoder)
    geocode_url = "https://geocoding-api.open-meteo.com/v1/search"
    try:
        geocode_resp = requests.get(
            geocode_url,
            params={"name": location, "count": 1},  # type: ignore[arg-type]
            timeout=10
        )
    except requests.RequestException as e:
        return {"status": "error", "error_message": f"Location lookup failed: {e}"}

    if geocode_resp.status_code != 200:
        return {"status": "error", "error_message": "Location lookup failed."}

    geo_data = geocode_resp.json().get("results")
    if not geo_data:
        return {"status": "error", "error_message": f"Unknown location: {location}"}

    lat = geo_data[0]["latitude"]
    lon = geo_data[0]["longitude"]

    # 2. Query weather forecast
    weather_url = "https://api.open-meteo.com/v1/forecast"
    try:
        weather_resp = requests.get(
            weather_url,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": ["temperature_2m_max", "temperature_2m_min", "weathercode"],
                "timezone": "UTC",
                "start_date": date,
                "end_date": date,
            },
            timeout=10
        )
    except requests.RequestException as e:
        return {"status": "error", "error_message": f"Weather API request failed: {e}"}

    if weather_resp.status_code != 200:
        return {"status": "error", "error_message": "Weather API request failed."}

    w = weather_resp.json()

    # Extract daily data (Open-Meteo returns lists)
    try:
        max_temp_c = w["daily"]["temperature_2m_max"][0]
        min_temp_c = w["daily"]["temperature_2m_min"][0]
        weather_code = w["daily"]["weathercode"][0]
    except (KeyError, IndexError):
        return {"status": "error", "error_message": "No weather data for that date."}

    # Simple mapping of weather codes to text
    CODE_MAP = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",
    }

    condition = CODE_MAP.get(weather_code, "Unknown")

    # Temperature conversion if needed
    if unit == "F":
        max_temp = max_temp_c * 9/5 + 32
        min_temp = min_temp_c * 9/5 + 32
    else:
        max_temp = max_temp_c
        min_temp = min_temp_c

    return {
        "status": "success",
        "location": location,
        "date": date,
        "unit": unit,
        "temperature": {
            "max": round(max_temp, 1),
            "min": round(min_temp, 1)
        },
        "condition": condition,
    }
