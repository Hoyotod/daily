# Agents

## Project

Auto-claims daily check-in rewards for HoYoverse games (Genshin, Star Rail, ZZZ, Honkai, ToT) and sends results to Discord. Two files: `main.py` (entrypoint) and `utils.py` (everything else).

## Setup & Run

- **Package manager**: `uv` (not pip). Lockfile `uv.lock` is committed.
- **Python**: 3.13 (see `.python-version`)
- **Database**: PostgreSQL (required) — reads account cookies from `Account` table
- Install: `uv sync`
- Run: `uv run python main.py`
- Configure: copy `.env.example` to `.env` and fill in `DATABASE_URL` (required) and optionally `DISCORD_WEBHOOK_URL`

## Database Schema

Expects a PostgreSQL table with:
```sql
"Account" (
  name TEXT,
  "accountId" TEXT,
  "cookieToken" TEXT
)
```
The app queries all rows and builds cookie strings as `account_id_v2={accountId}; cookie_token_v2={cookieToken}`.

## Conventions

- Comments, log messages, and variable names use **Bahasa Indonesia** — this is intentional, do not translate.
- Line endings are CRLF (`.editorconfig`).
- No linter, type checker, or formatter is configured. No tests exist.
- Config is loaded via `pydantic-settings` from `.env` at module import time (see `utils.py:51`).

## Gotchas

- The app fetches cookies from PostgreSQL at runtime — it won't work without a valid `DATABASE_URL` and the `Account` table.
- Discord webhook sends use `discord-webhook` library, wrapped in `asyncio.to_thread` to avoid blocking the event loop.
- Concurrency is controlled via `MAX_PARALLEL` (default 5). Uses `asyncio.Semaphore` to limit simultaneous API calls across all games.
- `fix_asyncio_windows_error()` is a Windows-only workaround — safe to ignore on Linux.
- Game toggles are **opt-out** (`NO_GENSHIN=False` means Genshin is enabled). All games except ToT are enabled by default per `.env.example`.
