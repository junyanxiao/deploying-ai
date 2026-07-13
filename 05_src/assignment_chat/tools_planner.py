from __future__ import annotations

from typing import Any
import os

if os.getenv("ASSIGNMENT_CHAT_ENABLE_LANGSMITH", "FALSE").upper() != "TRUE":
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"

from langchain.tools import tool

from utils.logger import get_logger


_logs = get_logger(__name__)


def _budget_level(budget_per_person: float) -> str:
    if budget_per_person <= 0:
        return "free-only"
    if budget_per_person < 20:
        return "small"
    if budget_per_person < 60:
        return "moderate"
    return "comfortable"


def _indoor_priority(weather_condition: str) -> bool:
    condition = (weather_condition or "").lower()
    return any(
        term in condition
        for term in ["rain", "snow", "thunderstorm", "hail", "freezing", "very cold", "hot", "unknown"]
    )


@tool
def build_weekend_plan(
    budget_per_person: float = 0,
    available_hours: float = 3,
    number_of_people: int = 1,
    preference: str = "flexible Toronto activities",
    weather_condition: str = "unknown",
) -> dict[str, Any]:
    """
    Build a structured Toronto weekend planning framework from budget, time,
    group size, preference, and weather condition. Use this whenever the user
    asks for a weekend plan. This tool structures time and budget; it does not
    choose named places.
    """
    errors = []
    notes = []

    try:
        budget = float(budget_per_person)
    except (TypeError, ValueError):
        budget = 0.0
        errors.append("budget_per_person must be a number")

    try:
        hours = float(available_hours)
    except (TypeError, ValueError):
        hours = 0.0
        errors.append("available_hours must be a number")

    try:
        people = int(number_of_people)
    except (TypeError, ValueError):
        people = 0
        errors.append("number_of_people must be an integer")

    clean_preference = (preference or "").strip()
    clean_weather = (weather_condition or "unknown").strip() or "unknown"

    if budget < 0:
        errors.append("budget_per_person cannot be negative")
    if hours <= 0:
        errors.append("available_hours must be greater than zero")
    if people <= 0:
        errors.append("number_of_people must be at least one")
    if not clean_preference:
        clean_preference = "flexible Toronto activities"
        notes.append("No preference was provided, so the plan should stay flexible.")
    if clean_weather.lower() == "unknown":
        notes.append("Weather is unknown, so include an indoor backup option.")

    if errors:
        _logs.info("Planner validation failed: %s", errors)
        return {
            "ok": False,
            "errors": errors,
            "planning_notes": notes,
        }

    budget = max(0.0, budget)
    total_budget = round(budget * people, 2)
    level = _budget_level(budget)

    if hours < 2:
        recommended_stops = 1
    elif hours < 4:
        recommended_stops = 2
    else:
        recommended_stops = 3

    if level in ["free-only", "small"]:
        notes.append("Prioritize free or low-cost stops and keep paid add-ons optional.")
    if level == "free-only":
        recommended_stops = min(recommended_stops, 2)
        notes.append("Use public spaces, libraries, markets, or free-entry destinations.")

    indoor_priority = _indoor_priority(clean_weather)
    if indoor_priority:
        notes.append("Prefer indoor stops or keep outdoor segments short because of the weather condition.")

    travel_buffer = min(45, max(15, int(hours * 10)))
    stop_time = max(30, int(((hours * 60) - travel_buffer) / recommended_stops))

    return {
        "ok": True,
        "total_budget": total_budget,
        "budget_per_person": budget,
        "budget_level": level,
        "available_hours": hours,
        "number_of_people": people,
        "preference": clean_preference,
        "weather_condition": clean_weather,
        "recommended_number_of_stops": recommended_stops,
        "indoor_priority": indoor_priority,
        "suggested_time_allocation": {
            "minutes_per_stop": stop_time,
            "travel_or_break_buffer_minutes": travel_buffer,
        },
        "planning_notes": notes,
    }
