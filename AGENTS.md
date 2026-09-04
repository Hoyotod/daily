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

## Cookie Handling & Expiry

- The app uses **v2 cookies** (`account_id_v2` + `cookie_token_v2`), which are long-lived (months). They expire only on sign-out, password change, or ~90 days of inactivity.
- `genshin.complete_cookies(refresh=False)` is called — the `refresh=False` is critical. The refresh API returns `-707` for v2 cookies because the library's refresh path is v1-only and requires `stoken_v2`+`mid` (not stored).
- Invalid/expired cookies are detected via `is_invalid_cookie()` helper (checks for `InvalidCookies`, `CookieException`, and retcodes `-100`, `10001`, `10103`, `-1071`, `-3203`, `-707`).
- When detected, status is set to `"cookie_err"` → displayed as `❌ Cookie` in terminal → aggregated in final Discord "⚠️ Account Alert".
- **No auto-refresh** — expired cookies must be manually re-captured from HoYoLAB app and updated in the database.
