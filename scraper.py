"""
scraper.py — Fetches badminton court availability from UCPA Sport Station API.

The UCPA website exposes a JSON API that returns weekly slot data.
We query it for 3 consecutive weeks (current, next, week after next)
and return a structured list of available slots.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_URL = "https://www.ucpa.com/sport-station/api/areas-offers/weekly/alpha_hp"

# Unique identifier for the Paris 19 Badminton area
AREA_ID = "area_1639603560_9977f290-5ded-11ec-96d0-03e553c50e2f"

# French day abbreviations returned by the API → English day names
_FR_DAY_MAP: dict[str, str] = {
    "lundi": "Monday",
    "mardi": "Tuesday",
    "mercredi": "Wednesday",
    "jeudi": "Thursday",
    "vendredi": "Friday",
    "samedi": "Saturday",
    "dimanche": "Sunday",
}

# Request timeout in seconds
REQUEST_TIMEOUT = 30

# User-Agent to mimic a regular browser request
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class Slot:
    """Represents a single bookable time slot."""

    def __init__(
        self,
        date: str,
        day_name: str,
        time_slot: str,
        available_courts: int,
        raw_date_label: str,
    ) -> None:
        self.date = date                        # e.g. "2026-03-10"
        self.day_name = day_name                # e.g. "Monday"
        self.time_slot = time_slot              # e.g. "19:00-20:00"
        self.available_courts = available_courts # e.g. 2
        self.raw_date_label = raw_date_label    # e.g. "10 mars (lun.)"

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "day_name": self.day_name,
            "time_slot": self.time_slot,
            "available_courts": self.available_courts,
        }

    def __repr__(self) -> str:
        return (
            f"Slot(date={self.date!r}, day={self.day_name!r}, "
            f"time={self.time_slot!r}, courts={self.available_courts})"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _monday_of_week(reference: datetime, week_offset: int = 0) -> datetime:
    """Return the Monday of the week that is *week_offset* weeks from *reference*."""
    # Monday = 0 in Python's weekday()
    days_since_monday = reference.weekday()
    monday = reference - timedelta(days=days_since_monday)
    return monday + timedelta(weeks=week_offset)


def _format_date_param(dt: datetime) -> str:
    """Format a datetime as DD-MM-YYYY for the API query parameter."""
    return dt.strftime("%d-%m-%Y")


def _french_time_to_standard(french_time: str) -> str:
    """Convert French time format '19h00' → '19:00'."""
    return french_time.replace("h", ":")


def _parse_date_iso(start_date_str: str) -> str:
    """Convert 'DD/MM/YYYY' → 'YYYY-MM-DD'."""
    try:
        dt = datetime.strptime(start_date_str, "%d/%m/%Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        logger.warning("Could not parse date: %s", start_date_str)
        return start_date_str


def _resolve_day_name(day_of_week_mobile: str) -> str:
    """Map a French day name (lowercase) to its English equivalent."""
    return _FR_DAY_MAP.get(day_of_week_mobile.lower(), day_of_week_mobile)


# ---------------------------------------------------------------------------
# API fetching
# ---------------------------------------------------------------------------

def fetch_week(monday: datetime, session: requests.Session | None = None) -> list[Slot]:
    """
    Fetch all badminton slots for the week starting on *monday*.

    Optionally accepts a *session* for TCP connection reuse across calls.
    Returns a list of Slot objects.
    """
    params = {
        "reservationPeriod": "1",
        "espace": AREA_ID,
        "time": _format_date_param(monday),
    }

    headers = {"User-Agent": USER_AGENT}
    requester = session or requests

    logger.info("Fetching week starting %s …", _format_date_param(monday))

    try:
        response = requester.get(
            API_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("HTTP request failed for week %s: %s", _format_date_param(monday), exc)
        return []

    try:
        data = response.json()
    except ValueError:
        logger.error("Invalid JSON response for week %s", _format_date_param(monday))
        return []

    return _parse_week_response(data)


def _parse_week_response(data: dict[str, Any]) -> list[Slot]:
    """Parse the API JSON response and extract all slots (with and without stock)."""
    slots: list[Slot] = []

    planner = data.get("planner")
    if not planner:
        logger.warning("No 'planner' key in API response")
        return slots

    columns = planner.get("columns", [])

    for column in columns:
        day_name_fr = column.get("dayOfWeekMobile", "")
        day_name = _resolve_day_name(day_name_fr)

        for item in column.get("items", []):
            stock = item.get("stock", 0)

            start_time = _french_time_to_standard(item.get("startTime", ""))
            end_time = _french_time_to_standard(item.get("endTime", ""))
            time_slot = f"{start_time}-{end_time}"

            iso_date = _parse_date_iso(item.get("startDate", ""))
            raw_label = item.get("date", "")

            slot = Slot(
                date=iso_date,
                day_name=day_name,
                time_slot=time_slot,
                available_courts=stock,
                raw_date_label=raw_label,
            )
            slots.append(slot)

    logger.info("  → parsed %d total slots", len(slots))
    return slots


def fetch_all_weeks(weeks: int = 3) -> list[Slot]:
    """
    Fetch slots for *weeks* consecutive weeks starting from the current week.

    Weeks are fetched in parallel using a shared Session for connection reuse.
    Returns a flat list of all Slot objects across all weeks.
    """
    today = datetime.now()
    mondays = [_monday_of_week(today, week_offset=i) for i in range(weeks)]

    results: dict[int, list[Slot]] = {}

    with requests.Session() as session:
        session.headers.update({"User-Agent": USER_AGENT})
        with ThreadPoolExecutor(max_workers=weeks) as executor:
            future_to_offset = {
                executor.submit(fetch_week, monday, session): i
                for i, monday in enumerate(mondays)
            }
            for future in as_completed(future_to_offset):
                offset = future_to_offset[future]
                results[offset] = future.result()

    # Reassemble in chronological order
    all_slots: list[Slot] = []
    for i in range(weeks):
        all_slots.extend(results.get(i, []))

    logger.info("Fetched %d total slots across %d weeks", len(all_slots), weeks)
    return all_slots


# ---------------------------------------------------------------------------
# Quick manual test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    slots = fetch_all_weeks()
    available = [s for s in slots if s.available_courts > 0]
    print(f"\n=== {len(available)} slots with availability ===\n")
    for s in available:
        print(json.dumps(s.to_dict(), indent=2))
