"""
monitor.py — Main entry point for the badminton slot monitor.

Two modes (controlled by the WEEKLY_SUMMARY env variable):

  • Normal (every 10 min):
      - Fetch available slots
      - Compare against Postgres to find NEW slots since the last run
      - Send a Telegram alert only if there are new slots
      - Save newly notified slots to Postgres

  • Weekly summary (WEEKLY_SUMMARY=true, runs every Friday at 5pm Paris):
      - Fetch all currently available slots
      - Send a full Telegram summary regardless of what was already notified
      - Does NOT update the Postgres table (we still want incremental alerts
        to work correctly after the weekly summary)
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from db import get_notified_keys, mark_slots_notified
from notifier import notify_multiple_slots, notify_weekly_summary
from scraper import Slot, fetch_all_weeks

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Days to monitor (English names)
MONITORED_DAYS: set[str] = {
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
}

# Time slots to monitor (start–end in HH:MM-HH:MM format)
MONITORED_TIMES: set[str] = {
    "18:00-19:00",
    "19:00-20:00",
    "20:00-21:00",
    "21:00-22:00",
}

# Number of weeks to scrape
WEEKS_TO_SCRAPE = 3

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Mapping English day names → French for notifications
_EN_TO_FR_DAYS: dict[str, str] = {
    "Monday": "Lundi",
    "Tuesday": "Mardi",
    "Wednesday": "Mercredi",
    "Thursday": "Jeudi",
    "Friday": "Vendredi",
    "Saturday": "Samedi",
    "Sunday": "Dimanche",
}

_MONTH_FR: dict[int, str] = {
    1: "janvier", 2: "février", 3: "mars", 4: "avril",
    5: "mai", 6: "juin", 7: "juillet", 8: "août",
    9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre",
}


def _is_monitored(slot: Slot) -> bool:
    """Return True if *slot* matches monitored days/times and has availability."""
    return (
        slot.day_name in MONITORED_DAYS
        and slot.time_slot in MONITORED_TIMES
        and slot.available_courts > 0
    )


def _slot_key(slot: Slot) -> str:
    """Unique deduplication key: date + time range."""
    return f"{slot.date}_{slot.time_slot}"


def _format_date_label(slot: Slot) -> str:
    """Build a human-readable date label like 'Mardi 12 mars'."""
    try:
        dt = datetime.strptime(slot.date, "%Y-%m-%d")
        day_fr = _EN_TO_FR_DAYS.get(slot.day_name, slot.day_name)
        month_fr = _MONTH_FR.get(dt.month, str(dt.month))
        return f"{day_fr} {dt.day} {month_fr}"
    except ValueError:
        return slot.raw_date_label


def _to_notification_data(slots: list[Slot]) -> list[dict]:
    return [
        {
            "date": s.date,
            "date_label": _format_date_label(s),
            "time_slot": s.time_slot,
            "available_courts": s.available_courts,
        }
        for s in slots
    ]


# ---------------------------------------------------------------------------
# Run modes
# ---------------------------------------------------------------------------

def run_incremental(dry_run: bool = False) -> None:
    """
    Every-10-min mode: only notify about slots not seen before.
    Saves newly notified slots to Postgres.
    """
    logger.info("Mode: INCREMENTAL")

    all_slots = fetch_all_weeks(weeks=WEEKS_TO_SCRAPE)
    if not all_slots:
        logger.warning("No slots returned from scraper — exiting")
        return

    matching = [s for s in all_slots if _is_monitored(s)]
    logger.info(
        "Found %d matching slots (days=%s, times=%s)",
        len(matching),
        ", ".join(sorted(MONITORED_DAYS)),
        ", ".join(sorted(MONITORED_TIMES)),
    )

    if not matching:
        logger.info("No available slots match the monitoring criteria")
        return

    # Fetch already-notified keys from Postgres (also cleans stale rows)
    notified_keys = get_notified_keys()

    new_slots = [s for s in matching if _slot_key(s) not in notified_keys]

    if not new_slots:
        logger.info("No new slots since last run — nothing to send ✓")
        return

    logger.info("%d new slot(s) to notify:", len(new_slots))
    for s in new_slots:
        logger.info("  • %s  %s  (%d court(s))", s.date, s.time_slot, s.available_courts)

    notification_data = _to_notification_data(new_slots)

    if dry_run:
        logger.info("[DRY RUN] Would send Telegram alert for %d slot(s)", len(new_slots))
        for item in notification_data:
            logger.info("  → %s | %s | %d court(s)", item["date_label"], item["time_slot"], item["available_courts"])
    else:
        success = notify_multiple_slots(notification_data)
        if not success:
            logger.error("Failed to send Telegram notification — DB not updated (will retry next run)")
            return

    # Persist to Postgres only after successful send (or dry run)
    if not dry_run:
        mark_slots_notified([(s.date, s.time_slot) for s in new_slots])

    logger.info("Incremental run complete ✓")


def run_weekly_summary(dry_run: bool = False) -> None:
    """
    Friday 5pm mode: send a full summary of ALL currently available slots.
    Does NOT update the Postgres table — incremental deduplication is unaffected.
    """
    logger.info("Mode: WEEKLY SUMMARY")

    all_slots = fetch_all_weeks(weeks=WEEKS_TO_SCRAPE)
    if not all_slots:
        logger.warning("No slots returned from scraper — exiting")
        return

    matching = [s for s in all_slots if _is_monitored(s)]
    logger.info("Found %d available slot(s) for weekly summary", len(matching))

    if not matching:
        logger.info("No available slots to report this week")
        return

    notification_data = _to_notification_data(matching)

    if dry_run:
        logger.info("[DRY RUN] Weekly summary — %d slot(s):", len(matching))
        for item in notification_data:
            logger.info("  → %s | %s | %d court(s)", item["date_label"], item["time_slot"], item["available_courts"])
    else:
        success = notify_weekly_summary(notification_data)
        if not success:
            logger.error("Failed to send weekly Telegram summary")
            return

    logger.info("Weekly summary run complete ✓")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monitor badminton slot availability and send Telegram alerts."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log available slots without sending Telegram notifications.",
    )
    args = parser.parse_args()

    load_dotenv()

    logger.info("=" * 60)
    logger.info("Badminton Slot Monitor — starting run")
    logger.info("=" * 60)

    weekly = os.environ.get("WEEKLY_SUMMARY", "").lower() in ("1", "true", "yes")

    try:
        if weekly:
            run_weekly_summary(dry_run=args.dry_run)
        else:
            run_incremental(dry_run=args.dry_run)
    except Exception:
        logger.exception("Unexpected error during monitor run")
        sys.exit(1)


if __name__ == "__main__":
    main()
