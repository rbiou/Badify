# 🏸 Badminton Slot Monitor

Monitors badminton court availability at [UCPA Sport Station Paris 19](https://www.ucpa.com/sport-station/paris-19/badminton) and sends **Telegram notifications** when evening slots become available.

Designed to run automatically every **10 minutes** via GitHub Actions.

## Monitored Slots

| Days | Times |
|------|-------|
| Sunday – Friday | 18:00–19:00 |
| | 19:00–20:00 |
| | 20:00–21:00 |
| | 21:00–22:00 |

## How It Works

1. **Scrapes** 3 weeks of availability via the UCPA JSON API (no browser needed)
2. **Filters** for the target days and time slots
3. **Deduplicates** using a local JSON cache (`cache.json`) to avoid repeat notifications
4. **Notifies** via Telegram with date, time, and number of available courts

## Setup

### Prerequisites

- Python 3.11+
- A Telegram bot (create one via [@BotFather](https://t.me/BotFather))
- Your Telegram chat ID (get it via [@userinfobot](https://t.me/userinfobot))

### Local Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd badminton-slot-monitor

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your Telegram bot token and chat ID
```

### Running Locally

```bash
# Full run (sends Telegram notifications)
python monitor.py

# Dry run (logs what would be sent, no actual notifications)
python monitor.py --dry-run
```

### GitHub Actions Deployment

1. Push this repository to GitHub
2. Go to **Settings → Secrets and variables → Actions**
3. Add these repository secrets:
   - `TELEGRAM_BOT_TOKEN` — your bot token from BotFather
   - `TELEGRAM_CHAT_ID` — your chat ID
4. The workflow runs automatically every 10 minutes
5. You can also trigger it manually from the **Actions** tab

> **Note:** The `cache.json` file is **not persisted** between GitHub Actions runs.
> Each run is independent, so you may receive duplicate notifications across runs.
> For persistent caching, consider using [GitHub Actions cache](https://github.com/actions/cache)
> or an external store.

## Project Structure

```
├── monitor.py          # Main entry point (orchestrator)
├── scraper.py          # Fetches availability from UCPA API
├── notifier.py         # Sends Telegram notifications
├── requirements.txt    # Python dependencies
├── .env.example        # Environment variable template
├── .gitignore          # Git ignore rules
└── .github/
    └── workflows/
        └── monitor.yml # GitHub Actions workflow
```

## Telegram Message Example

```
🏸 Badminton slots available!

📅 Mardi 12 mars  ·  🕐 19:00–20:00  ·  🟢 2 court(s)
📅 Mercredi 13 mars  ·  🕐 20:00–21:00  ·  🟢 1 court(s)

Book here:
https://www.ucpa.com/sport-station/paris-19/badminton
```

## License

MIT
