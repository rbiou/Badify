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

def _format_message(
    date_label: str,
    time_slot: str,
    available_courts: int,
) -> str:
    """
    Build a human-friendly Telegram notification message.

    Example output:
        🏸 Badminton slot available!

        Date: Tuesday 12 May
        Time: 19:00–20:00
        Courts available: 2

        Book here:
        https://www.ucpa.com/sport-station/paris-19/badminton
    """
    # Replace the ASCII hyphen with an en-dash for aesthetics
    time_display = time_slot.replace("-", "–")

    return (
        f"🏸 Badminton slot available!\n"
        f"\n"
        f"📅 Date: {date_label}\n"
        f"🕐 Time: {time_display}\n"
        f"🟢 Courts available: {available_courts}\n"
        f"\n"
        f"Book here:\n"
        f"{BOOKING_URL}"
    )


def _format_summary_message(
    slots: list[dict],
) -> str:
    """
    Build a single summary message listing all available slots.

    This avoids sending one message per slot, which could be spammy.
    """
    lines = ["🏸 Badminton slots available!\n"]

    for slot in slots:
        time_display = slot["time_slot"].replace("-", "–")
        lines.append(
            f"📅 {slot['date_label']}  ·  🕐 {time_display}  ·  "
            f"🟢 {slot['available_courts']} court(s)"
        )

    lines.append(f"\nBook here:\n{BOOKING_URL}")
    return "\n".join(lines)


def _format_weekly_summary_message(slots: list[dict]) -> str:
    """Build a weekly recap message listing all currently available slots."""
    lines = ["📊 Récap hebdo — créneaux dispos !\n"]

    for slot in slots:
        time_display = slot["time_slot"].replace("-", "–")
        lines.append(
            f"📅 {slot['date_label']}  ·  🕐 {time_display}  ·  "
            f"🟢 {slot['available_courts']} court(s)"
        )

    lines.append(f"\nRéserver :\n{BOOKING_URL}")
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

