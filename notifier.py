"""
notifier.py — Sends Telegram notifications for available badminton slots.

Uses the Telegram Bot HTTP API to send formatted messages.
Credentials are read from environment variables.
"""

import logging
import os

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"

BOOKING_URL = "https://www.ucpa.com/sport-station/paris-19/badminton"

# ---------------------------------------------------------------------------
# Message formatting
# ---------------------------------------------------------------------------


# Abbreviated French day names to keep lines short on mobile
_DAY_ABBR: dict[str, str] = {
    "Lundi": "Lun", "Mardi": "Mar", "Mercredi": "Mer",
    "Jeudi": "Jeu", "Vendredi": "Ven", "Samedi": "Sam", "Dimanche": "Dim",
}


def _abbr_date_label(date_label: str) -> str:
    """'Dimanche 15 mars' → 'Dim 15 mars'"""
    parts = date_label.split(" ", 1)
    if len(parts) == 2:
        abbr = _DAY_ABBR.get(parts[0], parts[0])
        return f"{abbr} {parts[1]}"
    return date_label


def _group_by_date(slots: list[dict]) -> dict[str, list[dict]]:
    """Group slots by date (ISO), preserving insertion order."""
    groups: dict[str, list[dict]] = {}
    for slot in slots:
        key = slot.get("date", slot["date_label"])
        groups.setdefault(key, []).append(slot)
    return groups


def _render_groups(groups: dict[str, list[dict]]) -> list[str]:
    """
    Render grouped slots as lines, e.g.:

        📅 <b>Dim 15 mars</b>
          🕐 21:00–22:00  ·  🟢 2 courts
    """
    lines = []
    for _, day_slots in groups.items():
        label = _abbr_date_label(day_slots[0]["date_label"])
        lines.append(f"📅 <b>{label}</b>")
        for slot in day_slots:
            time_display = slot["time_slot"].replace("-", "–")
            n = slot["available_courts"]
            court_str = f"{n} court{'s' if n > 1 else ''}"
            lines.append(f"  🕐 {time_display}  ·  🟢 {court_str}")
        lines.append("")  # blank line between dates
    return lines


def _format_summary_message(slots: list[dict]) -> str:
    """Incremental alert: only new slots since last run."""
    groups = _group_by_date(slots)
    lines = ["🏸 <b>Nouveaux créneaux !</b>\n"]
    lines.extend(_render_groups(groups))
    lines.append(f'<a href="{BOOKING_URL}">🔗 Réserver</a>')
    return "\n".join(lines)


def _format_weekly_summary_message(slots: list[dict]) -> str:
    """Friday weekly recap: all currently available slots."""
    groups = _group_by_date(slots)
    n_total = sum(len(v) for v in groups.values())
    lines = [f"📊 <b>Récap hebdo — {n_total} créneau{'x' if n_total > 1 else ''} dispo</b>\n"]
    lines.extend(_render_groups(groups))
    lines.append(f'<a href="{BOOKING_URL}">🔗 Réserver</a>')
    return "\n".join(lines)



# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------

def _get_credentials() -> tuple[str, str]:
    """Read Telegram bot token and chat ID from environment variables."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token:
        raise EnvironmentError("TELEGRAM_BOT_TOKEN is not set")
    if not chat_id:
        raise EnvironmentError("TELEGRAM_CHAT_ID is not set")

    return token, chat_id


def send_message(text: str) -> bool:
    """
    Send a plain-text message via the Telegram Bot API.

    Returns True on success, False on failure.
    """
    try:
        token, chat_id = _get_credentials()
    except EnvironmentError as exc:
        logger.error("Telegram credentials missing: %s", exc)
        return False

    url = TELEGRAM_API_URL.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        logger.info("Telegram message sent successfully")
        return True
    except requests.RequestException as exc:
        logger.error("Failed to send Telegram message: %s", exc)
        return False


def notify_single_slot(
    date_label: str,
    time_slot: str,
    available_courts: int,
) -> bool:
    """Send a notification for a single available slot."""
    message = _format_message(date_label, time_slot, available_courts)
    return send_message(message)


def notify_multiple_slots(slots: list[dict]) -> bool:
    """
    Send a single summary notification for multiple available slots.

    Each dict in *slots* should have keys:
        - date_label (str): e.g. "Tuesday 12 May"
        - time_slot (str): e.g. "19:00-20:00"
        - available_courts (int): e.g. 2
    """
    if not slots:
        logger.info("No slots to notify about")
        return True

    message = _format_summary_message(slots)
    return send_message(message)


def notify_weekly_summary(slots: list[dict]) -> bool:
    """
    Send the Friday weekly summary of all available slots.

    Same dict shape as notify_multiple_slots but uses a distinct header.
    """
    if not slots:
        logger.info("No slots available for the weekly summary")
        return True

    message = _format_weekly_summary_message(slots)
    return send_message(message)

