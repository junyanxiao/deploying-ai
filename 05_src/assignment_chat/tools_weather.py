from __future__ import annotations

from datetime import date
from typing import Any
import os

if os.getenv("ASSIGNMENT_CHAT_ENABLE_LANGSMITH", "FALSE").upper() != "TRUE":
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"

from langchain.tools import tool
import requests

from utils.logger import get_logger


_logs = get_logger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT_SECONDS = 8


WEATHER_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    56: "light freezing drizzle",
    57: "dense freezing drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "heavy freezing rain",
    71: "slight snow fall",
    73: "moderate snow fall",
    75: "heavy snow fall",
    77: "snow grains",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    85: "slight snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


def _condition_from_code(weather_code: int | None) -> str:
    if weather_code is None:
        return "unknown"
    return WEATHER_CODES.get(weather_code, f"weather code {weather_code}")


def _outdoor_guidance(condition: str, precipitation_probability: int | None, temperature: float | None) -> str:
    condition_lower = condition.lower()
    if any(term in condition_lower for term in ["rain", "snow", "thunderstorm", "freezing", "hail"]):
        return "Indoor activities are safer unless the user is prepared for wet or wintry weather."
    if precipitation_probability is not None and precipitation_probability >= 60:
        return "Indoor activities are preferable because precipitation is likely."
    if temperature is not None and temperature <= -5:
        return "Choose indoor activities or short outdoor stops because it is very cold."
    if temperature is not None and temperature >= 30:
        return "Plan shade, water, and indoor breaks because it is hot."
    return "Outdoor activities look reasonable if the user dresses comfortably."


def _safe_get(mapping: dict[str, Any], key: str) -> Any:
    value = mapping.get(key)
    if isinstance(value, list) and value:
        return value[0]
    return value


def _resolve_location(city: str) -> dict[str, Any] | None:
    params = {
        "name": city or "Toronto",
        "count": 1,
        "language": "en",
        "format": "json",
    }
    response = requests.get(GEOCODING_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    data = response.json()
    results = data.get("results", [])
    if not results:
        return None
    return results[0]


@tool
def get_weather(city: str = "Toronto", forecast_days: int = 1) -> dict[str, Any]:
    """
    Get current and short forecast weather for a city, defaulting to Toronto.

    Returns parsed, structured weather fields rather than raw API JSON.
    """
    try:
        forecast_days = max(1, min(int(forecast_days), 3))
    except (TypeError, ValueError):
        forecast_days = 1

    requested_city = city or "Toronto"
    try:
        location = _resolve_location(requested_city)
        if not location:
            return {
                "ok": False,
                "message": f"I could not resolve the location '{requested_city}'.",
                "requested_city": requested_city,
            }

        params = {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "current": (
                "temperature_2m,apparent_temperature,precipitation,rain,showers,"
                "snowfall,weather_code,wind_speed_10m,wind_direction_10m"
            ),
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": "auto",
            "forecast_days": forecast_days,
        }
        response = requests.get(FORECAST_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except requests.Timeout:
        _logs.warning("Weather API request timed out for %s", requested_city)
        return {
            "ok": False,
            "message": "The weather service timed out. Please try again shortly.",
            "requested_city": requested_city,
        }
    except requests.RequestException as exc:
        _logs.warning("Weather API request failed for %s: %s", requested_city, exc)
        return {
            "ok": False,
            "message": "The weather service is temporarily unavailable.",
            "requested_city": requested_city,
        }
    except (KeyError, ValueError, TypeError) as exc:
        _logs.warning("Weather API response could not be parsed for %s: %s", requested_city, exc)
        return {
            "ok": False,
            "message": "The weather service returned data I could not read safely.",
            "requested_city": requested_city,
        }

    current = data.get("current", {}) or {}
    daily = data.get("daily", {}) or {}
    current_code = current.get("weather_code")
    current_condition = _condition_from_code(current_code)
    precipitation_probability = _safe_get(daily, "precipitation_probability_max")
    temperature = current.get("temperature_2m")

    resolved_location = {
        "name": location.get("name"),
        "admin1": location.get("admin1"),
        "country": location.get("country"),
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
    }

    return {
        "ok": True,
        "requested_city": requested_city,
        "resolved_location": resolved_location,
        "retrieved_for": date.today().isoformat(),
        "current": {
            "time": current.get("time"),
            "temperature_c": temperature,
            "apparent_temperature_c": current.get("apparent_temperature"),
            "condition": current_condition,
            "weather_code": current_code,
            "precipitation_mm": current.get("precipitation"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
            "wind_direction_degrees": current.get("wind_direction_10m"),
        },
        "forecast": {
            "dates": daily.get("time", []),
            "conditions": [_condition_from_code(code) for code in daily.get("weather_code", [])],
            "temperature_max_c": daily.get("temperature_2m_max", []),
            "temperature_min_c": daily.get("temperature_2m_min", []),
            "precipitation_probability_max_percent": daily.get("precipitation_probability_max", []),
        },
        "activity_guidance": _outdoor_guidance(
            current_condition,
            precipitation_probability,
            temperature,
        ),
    }
