# Agents

## Project

Auto-claims daily check-in rewards for HoYoverse games (Genshin, Star Rail, ZZZ, Honkai, ToT) and sends results to Discord and/or Telegram. Two files: `main.py` (entrypoint) and `utils.py` (everything else).

## Setup & Run

- **Package manager**: `uv` (not pip). Lockfile `uv.lock` is committed.
- **Python**: 3.13 (see `.python-version`)
- **Account source**: hoyo-api (required) — reads every game account via `GET /api/internal/accounts`
- Install: `uv sync` (or `uv sync --extra dev` for development tools)
- Run: `uv run python main.py`
- Configure: copy `.env.example` to `.env` and fill in `HOYO_API_URL` + `HOYO_API_KEY` (required) and optionally `DISCORD_WEBHOOK_URL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

## Account Source

The app calls `GET {HOYO_API_URL}/api/internal/accounts` with the `X-API-Key: HOYO_API_KEY` header. The response contains every user's game accounts:

```json
{
  "accounts": [
    {
      "id": "uuid",
      "name": "Alice",
      "accountId": "123456789",
      "cookieToken": "plaintext-token",
      "webhook": "https://discord.com/api/webhooks/...",
      "telegramChatId": "123456789"
    }
  ]
}
```

Cookie strings are built as `account_id_v2={accountId}; cookie_token_v2={cookieToken}`. Per-user Discord webhooks and Telegram chat IDs come from the same response (`webhook` / `telegramChatId`).

## Conventions

- Comments, log messages, and variable names use **Bahasa Indonesia** — this is intentional, do not translate.
- Line endings are CRLF (`.editorconfig`).
- **Linter**: Ruff (configured in `pyproject.toml`) — run `uv run ruff check .` or `uv run ruff format .`
- **Type checker**: Mypy (strict mode) — run `uv run mypy main.py utils.py`
- **Tests**: Pytest with asyncio support - run `uv run pytest` or `uv run pytest --cov` for coverage (56 tests, ~52% coverage)
- **CI**: GitHub Actions runs all checks on push/PR to main (see `.github/workflows/ci.yml`)
- **Pre-commit**: configured in `.pre-commit-config.yaml` (ruff, mypy, pytest) — run `uv run pre-commit install` then `uv run pre-commit run --all-files`
- Config is loaded via `pydantic-settings` from `.env` at module import time (see `utils.py:51`).

## Gotchas

- The app fetches accounts from hoyo-api at runtime — it won't work without a valid `HOYO_API_URL`, `HOYO_API_KEY`, and hoyo-api's `SERVICE_API_KEY` secret.
- Discord webhook sends use `discord-webhook` library, wrapped in `asyncio.to_thread` to avoid blocking the event loop.
- Telegram sends use the Bot API via `requests` in `asyncio.to_thread`; configured via `TELEGRAM_BOT_TOKEN` (global) and per-user `telegramChatId` (hoyo-api user record) or `TELEGRAM_CHAT_ID` (global fallback).
- Cookie values from hoyo-api are validated against RFC 6265 cookie-value rules (printable ASCII except `;`, `,`, whitespace, `"` and `\`) to prevent cookie injection; invalid rows are skipped.
- Concurrency is controlled via `MAX_PARALLEL` (default 5). Uses `asyncio.Semaphore` to limit simultaneous API calls across all games.
- `fix_asyncio_windows_error()` is a Windows-only workaround — safe to ignore on Linux.
- Game toggles are **opt-out** (`NO_GENSHIN=False` means Genshin is enabled). All games except ToT are enabled by default per `.env.example`.

## Cookie Handling & Expiry

- The app uses **v2 cookies** (`account_id_v2` + `cookie_token_v2`), which are long-lived (months). They expire only on sign-out, password change, or ~90 days of inactivity.
- `genshin.complete_cookies(refresh=False)` is called — the `refresh=False` is critical. The refresh API returns `-707` for v2 cookies because the library's refresh path is v1-only and requires `stoken_v2`+`mid` (not stored).
- Invalid/expired cookies are detected via `is_invalid_cookie()` helper (checks for `InvalidCookies`, `CookieException`, and retcodes `-100`, `10001`, `10103`, `-1071`, `-3203`, `-707`).
- When detected, status is set to `"cookie_err"` → displayed as `❌ Cookie` in terminal → aggregated in final Discord "⚠️ Account Alert" and Telegram "⚠️ Account Alert".
- **No auto-refresh** — expired cookies must be manually re-captured from HoYoLAB app and updated in hoyo-api.
