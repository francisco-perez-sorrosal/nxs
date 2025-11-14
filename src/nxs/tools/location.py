import requests

def get_current_location() -> dict:
    """Retrieves approximate geolocation from the machine's public IP address
    using a free, no-auth IP info service.

    Returns:
        Success:
            {
                "status": "success",
                "ip": "8.8.8.8",
                "city": "Mountain View",
                "region": "California",
                "country": "US",
                "latitude": 37.3860,
                "longitude": -122.0838
            }

        Error:
            {"status": "error", "error_message": "..."}
    """

    api_url = "https://ipinfo.io/json"

    try:
        response = requests.get(api_url, timeout=5)
    except Exception as exc:
        return {
            "status": "error",
            "error_message": f"Failed to connect to geolocation service: {exc}",
        }

    if response.status_code != 200:
        return {
            "status": "error",
            "error_message": f"Invalid response from service: {response.status_code}",
        }

    data = response.json()

    # Extract location fields
    ip = data.get("ip")
    city = data.get("city")
    region = data.get("region")
    country = data.get("country")
    loc = data.get("loc")  # "lat,lon"

    if not loc:
        return {
            "status": "error",
            "error_message": "Location data missing from response."
        }

    try:
        latitude, longitude = map(float, loc.split(","))
    except Exception:
        return {
            "status": "error",
            "error_message": "Malformed latitude/longitude format."
        }

    return {
        "status": "success",
        "ip": ip,
        "city": city,
        "region": region,
        "country": country,
        "latitude": latitude,
        "longitude": longitude,
    }