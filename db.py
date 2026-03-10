"""
db.py — Postgres-backed persistence for notified slots.

Replaces the local cache.json with a remote database so state is
shared and persisted across all GitHub Actions runs.

Table schema (must already exist):
    CREATE TABLE notified_slots (
        date        DATE         NOT NULL,
        time_slot   VARCHAR(11)  NOT NULL,  -- e.g. "19:00-20:00"
        notified_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        PRIMARY KEY (date, time_slot)
    );
"""

import logging
import os
from datetime import date, datetime

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def _get_connection():
    """Open a connection using DATABASE_URL from the environment."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise EnvironmentError("DATABASE_URL is not set")
    return psycopg2.connect(url)


def ensure_table() -> None:
    """Create the notified_slots table if it doesn't already exist."""
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS notified_slots (
                    date        DATE         NOT NULL,
                    time_slot   VARCHAR(11)  NOT NULL,
                    notified_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (date, time_slot)
                )
            """)
        conn.commit()
    logger.debug("Table notified_slots is ready")


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def get_notified_keys() -> set[str]:
    """
    Return a set of 'YYYY-MM-DD_HH:MM-HH:MM' keys for all future slots
    that have already been notified.

    Automatically removes past entries (dates before today) to keep the
    table small.
    """
    today = date.today()
    ensure_table()
    with _get_connection() as conn:
        with conn.cursor() as cur:
            # Clean up past entries
            cur.execute("DELETE FROM notified_slots WHERE date < %s", (today,))
            logger.info("Cleaned stale DB entries (before %s)", today)

            # Fetch remaining entries
            cur.execute("SELECT date, time_slot FROM notified_slots WHERE date >= %s", (today,))
            rows = cur.fetchall()

    keys = {f"{row[0].strftime('%Y-%m-%d')}_{row[1]}" for row in rows}
    logger.info("Loaded %d notified slot key(s) from DB", len(keys))
    return keys


def mark_slots_notified(slot_keys: list[tuple[str, str]]) -> None:
    """
    Insert rows for newly notified slots.

    *slot_keys* is a list of (date_str, time_slot) tuples,
    e.g. [("2026-03-15", "19:00-20:00"), ...]

    Uses INSERT ... ON CONFLICT DO NOTHING to be idempotent.
    """
    if not slot_keys:
        return

    now = datetime.utcnow()
    rows = [(date_str, time_slot, now) for date_str, time_slot in slot_keys]

    with _get_connection() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO notified_slots (date, time_slot, notified_at)
                VALUES %s
                ON CONFLICT (date, time_slot) DO NOTHING
                """,
                rows,
            )
        conn.commit()

    logger.info("Marked %d slot(s) as notified in DB", len(rows))
