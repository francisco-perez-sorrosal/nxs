from datetime import datetime

def get_local_datetime(fmt: str | None = None) -> dict:
    """Retrieves the current local date and time.

    Args:
        fmt: Optional datetime format string (strftime syntax).
             If omitted, defaults to the ISO 8601 format: '%Y-%m-%dT%H:%M:%S'.

    Returns:
        Success:
            {
                "status": "success",
                "datetime": "2025-11-19T14:32:10",
                "timezone": "UTC+01:00"
            }

        Error:
            {"status": "error", "error_message": "..."}
    """

    default_format = "%Y-%m-%dT%H:%M:%S"
    chosen_format = fmt if fmt else default_format

    now = datetime.now()

    try:
        formatted = now.strftime(chosen_format)
    except Exception as exc:
        return {
            "status": "error",
            "error_message": f"Invalid datetime format '{fmt}': {exc}"
        }

    # Extract timezone offset if available
    tzinfo = now.astimezone().strftime("%z")  # e.g. "+0200"
    if tzinfo:
        tzinfo = f"UTC{tzinfo[:3]}:{tzinfo[3:]}"  # Convert "+0200" → "UTC+02:00"
    else:
        tzinfo = "Unknown"

    return {
        "status": "success",
        "datetime": formatted,
        "timezone": tzinfo,
    }