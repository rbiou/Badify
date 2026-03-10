# 🏸 Badminton Slot Monitor

Monitors badminton court availability at [UCPA Sport Station Paris 19](https://www.ucpa.com/sport-station/paris-19/badminton) and sends **Telegram notifications** when evening slots become available.

Runs automatically via **GitHub Actions** with two modes:
- **Every 10 minutes** — alerts only when *new* slots appear (no duplicate notifications)
- **Every Friday at 5pm (Paris)** — weekly recap of all currently available slots

## Monitored Slots

| Days | Times |
|------|-------|
| Monday – Friday | 18:00–19:00 |
| + Sunday | 19:00–20:00 |
| | 20:00–21:00 |
| | 21:00–22:00 |

## How It Works

1. **Scrapes** 3 weeks of availability via the UCPA JSON API
2. **Filters** for target days and time slots
3. **Deduplicates** against a PostgreSQL database to avoid repeat notifications
4. **Notifies** via Telegram — one message per run, or nothing if no new slots

## Setup

### Prerequisites

- Python 3.11+
- A Telegram bot ([create one via @BotFather](https://t.me/BotFather)) and your Telegram chat/channel ID
- A remote PostgreSQL database (e.g. [Clever Cloud](https://www.clever-cloud.com/), Supabase, Neon…)

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
# Edit .env with your credentials
```

### Environment Variables

```dotenv
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_CHAT_ID=-100xxxxxxxxxx       # Channel ID (with -100 prefix) or @username
DATABASE_URL=postgresql://user:password@host:port/dbname
```

> **Note:** The database table (`notified_slots`) is created automatically on first run — no manual schema setup needed.

### Running Locally

```bash
# Incremental run (sends Telegram if new slots found)
python monitor.py

# Dry run (logs output, no Telegram, no DB writes)
python monitor.py --dry-run

# Force weekly summary mode
WEEKLY_SUMMARY=true python monitor.py --dry-run
```

### GitHub Actions Deployment

1. Push this repository to GitHub
2. Go to **Settings → Secrets and variables → Actions**
3. Add these repository secrets:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `DATABASE_URL`
4. The workflow runs automatically every 10 minutes + every Friday at 5pm Paris time
5. You can also trigger it manually from the **Actions** tab

## Project Structure

```
├── monitor.py          # Main entry point — orchestrates scraping, deduplication, notifications
├── scraper.py          # Fetches availability from UCPA API
├── notifier.py         # Sends Telegram notifications
├── db.py               # PostgreSQL persistence layer (deduplication state)
├── requirements.txt    # Python dependencies
├── .env.example        # Environment variable template
└── .github/
    └── workflows/
        └── monitor.yml # GitHub Actions workflow (10-min + Friday schedules)
```

## Telegram Message Examples

**Incremental alert (new slots only):**
```
🏸 Badminton slots available!

📅 Dimanche 15 mars  ·  🕐 21:00–22:00  ·  🟢 2 court(s)
📅 Vendredi 20 mars  ·  🕐 20:00–21:00  ·  🟢 1 court(s)

Book here:
https://www.ucpa.com/sport-station/paris-19/badminton
```

**Weekly recap (every Friday):**
```
📊 Récap hebdo — créneaux dispos !

📅 Dimanche 15 mars  ·  🕐 21:00–22:00  ·  🟢 2 court(s)
📅 Vendredi 20 mars  ·  🕐 20:00–21:00  ·  🟢 1 court(s)
...

Réserver :
https://www.ucpa.com/sport-station/paris-19/badminton
```

## License

MIT
