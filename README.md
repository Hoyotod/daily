# daily

Auto-claims daily check-in rewards for HoYoverse games and sends results to Discord.

## Features

- Supports Genshin Impact, Honkai: Star Rail, Zenless Zone Zero, Honkai Impact 3rd, and Tears of Themis
- Batch claims across multiple accounts concurrently
- Configurable concurrency limit (`MAX_PARALLEL`) to avoid API rate limits
- Discord webhook notifications with chunked messages
- Rich terminal output with per-game tables

## Prerequisites

- Python 3.13
- PostgreSQL database with an `Account` table
- [uv](https://docs.astral.sh/uv/) package manager

## Setup

1. Install dependencies:
   ```bash
   uv sync
   ```

2. Copy `.env.example` to `.env` and configure:
   ```bash
   cp .env.example .env
   ```

3. Fill in required values:
   - `DATABASE_URL` — PostgreSQL connection string
   - `DISCORD_WEBHOOK_URL` — (optional) Discord webhook URL

4. Run:
   ```bash
   uv run python main.py
   ```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `DISCORD_WEBHOOK_URL` | No | — | Discord webhook URL for notifications |
| `LOCALE` | No | `en-us` | API response language |
| `MAX_PARALLEL` | No | `5` | Max concurrent API requests |
| `NO_GENSHIN` | No | `False` | Disable Genshin Impact |
| `NO_STARRAIL` | No | `False` | Disable Honkai: Star Rail |
| `NO_ZZZ` | No | `False` | Disable Zenless Zone Zero |
| `NO_HONKAI` | No | `False` | Disable Honkai Impact 3rd |
| `NO_TOT` | No | `True` | Disable Tears of Themis |

## Database Schema

Expects a PostgreSQL `Account` table:

| Column | Type | Description |
|---|---|---|
| `name` | TEXT | Account display name |
| `accountId` | TEXT | Game account ID (unique) |
| `cookieToken` | TEXT | Authentication cookie token |

## Troubleshooting

### Invalid/Expired Cookie Errors

The app stores `cookie_token_v2` (v2 format), which is HoYoLAB's long-lived authentication token (lasts several months). It expires when you:
- Sign out from HoYoLAB on any device
- Change your HoYoverse account password
- Don't visit HoYoLAB for 90+ days

**When the app reports "❌ Cookie" errors:**

1. The stored `cookie_token_v2` is no longer valid
2. You must **re-capture** the token from the HoYoLAB mobile app using a network monitoring tool (e.g., HTTP Toolkit, Fiddler)
3. Update the `cookieToken` column in the `Account` table for affected accounts
4. The app cannot auto-refresh v2 tokens without the root credential (`stoken_v2` + `mid`), which is not currently stored

**To capture fresh tokens:**
- Use a proxy/network monitor on your device
- Log into the HoYoLAB mobile app
- Find the `cookie_token_v2` value in request cookies
- Update the database with the new token

## License

MIT
