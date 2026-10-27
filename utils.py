import asyncio
import logging
import re
import sys
from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime
from re import sub
from urllib.parse import urlparse

import asyncpg
import genshin
import requests
from discord_webhook import DiscordEmbed, DiscordWebhook
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from rich.console import Console
from rich.logging import RichHandler

# --- Setup Logging & Console ---
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=Console(), rich_tracebacks=True)],
)
log = logging.getLogger("rich")
console = Console()


# --- Configuration Management (Pydantic) ---
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App Config
    LOCALE: str = "en-us"
    MAX_PARALLEL: int = 5

    # Database
    DATABASE_URL: str | None = None

    # Webhooks
    DISCORD_WEBHOOK_URL: str = ""

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # Feature Flags
    NO_GENSHIN: bool = False
    NO_STARRAIL: bool = False
    NO_ZZZ: bool = False
    NO_HONKAI: bool = False
    NO_TOT: bool = False

    @field_validator("MAX_PARALLEL")
    @classmethod
    def _validate_max_parallel(cls, value: int) -> int:
        if value < 1:
            return 1
        return value


settings = Settings()


# --- Data Structures ---
@dataclass
class CookieInfo:
    env_name: str = ""
    cookies: str | dict[str, str] = ""
    user_webhook: str | None = None
    telegram_chat_id: str | None = None


@dataclass
class DailyInfo:
    uid: str = "❓"
    status: str = "❌"
    check_in_count: str = "❓"
    reward: str = "❓"
    success: bool = False
    env_name: str = "❓"


# --- Helper Functions ---
def check_lang(lang: str) -> str:
    valid = {
        "zh-cn",
        "zh-tw",
        "de-de",
        "en-us",
        "es-es",
        "fr-fr",
        "id-id",
        "ja-jp",
        "ko-kr",
        "pt-pt",
        "ru-ru",
        "th-th",
        "vi-vn",
    }
    lang = lang.lower()
    if lang not in valid:
        log.warning(f"[LANGUAGE] '{lang}' not supported. Using 'en-us'.")
        return "en-us"
    return lang


def censor_uid(uid: int | str) -> str:
    s = str(uid)
    return s[:-6] + "■■■■■" + s[-1] if len(s) >= 6 else s


def format_name(name: str) -> str:
    # Ganti karakter non-alphanumeric (kecuali awal/akhir) dengan underscore
    name = sub(r"(?<!^)\W+(?!$)", "_", name)
    return name.upper()


def fix_asyncio_windows_error() -> None:
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def get_days_of_month() -> int:
    now = datetime.now()
    return monthrange(now.year, now.month)[1]


def is_invalid_cookie(exc: Exception) -> bool:
    """
    Deteksi apakah exception adalah error cookie yang tidak valid/expired.
    Retcode yang relevan: -100, 10001, 10103, -1071, -3203, dan lainnya.
    """
    if isinstance(exc, genshin.errors.InvalidCookies):
        return True
    if isinstance(exc, genshin.errors.CookieException):
        return True
    if isinstance(exc, genshin.errors.GenshinException):
        invalid_retcodes = {-100, 10001, 10103, -1071, -3203, -707}
        if exc.retcode in invalid_retcodes:
            return True
    return False


# --- Core Logic ---


async def get_cookies_from_db() -> list[CookieInfo]:
    """
    Mengambil cookie dari PostgreSQL database.
    Schema: Account { name: string, accountId: string, cookieToken: string, ... }
    """
    if not settings.DATABASE_URL:
        log.error("[COOKIE] DATABASE_URL belum diset di .env")
        return []

    try:
        conn = await asyncpg.connect(settings.DATABASE_URL)
        try:
            rows = await conn.fetch(
                """SELECT a.name, a."accountId", a."cookieToken", u.webhook, u."telegramChatId"
                FROM "Account" a
                LEFT JOIN "User" u ON a."userId" = u.id"""
            )
        finally:
            await conn.close()
    except Exception as e:
        log.error(f"[COOKIE] Gagal mengambil cookie dari database: {type(e).__name__}")
        return []

    cookies = []
    for idx, row in enumerate(rows, 1):
        try:
            raw_name = row["name"]
            safe_name = format_name(raw_name)
            env_name = f"ACC{idx}_{safe_name}"

            account_id = row["accountId"]
            cookie_token = row["cookieToken"]

            if not account_id or not cookie_token:
                log.warning(f"[COOKIE] Data tidak lengkap untuk akun {env_name}, skip.")
                continue

            # Validasi untuk mencegah cookie injection (karakter berbahaya)
            account_id = str(account_id)
            cookie_token = str(cookie_token)
            if not re.fullmatch(r"[A-Za-z0-9_-]+", account_id) or not re.fullmatch(
                r"[A-Za-z0-9_-]+", cookie_token
            ):
                log.warning(
                    f"[COOKIE] Format cookie tidak valid untuk akun {env_name}, skip."
                )
                continue

            cookie_str = f"account_id_v2={account_id}; cookie_token_v2={cookie_token}"
            cookies.append(
                CookieInfo(
                    env_name=env_name,
                    cookies=cookie_str,
                    user_webhook=row["webhook"],
                    telegram_chat_id=row.get("telegramChatId")
                    if hasattr(row, "get")
                    else row["telegramChatId"],
                )
            )
        except Exception as e:
            log.warning(f"[COOKIE] Gagal memproses row {idx}: {e}")
            continue

    return sorted(cookies, key=lambda x: x.env_name)


async def create_genshin_client(
    cookie: CookieInfo, lang: str, game: genshin.Game
) -> tuple[genshin.Client | None, str | None]:
    """Factory function untuk membuat client Genshin yang aman."""
    try:
        cookies = await genshin.complete_cookies(cookies=cookie.cookies, refresh=False)
        client = genshin.Client(cookies=cookies, lang=lang, game=game)  # type: ignore
        return client, None
    except Exception as e:
        log.error(f"[CLIENT] Gagal membuat client: {type(e).__name__}")
        return None, str(e)


async def send_discord_embed(
    webhook_url: str, title: str, msg: str, color: str = "00ff00"
) -> None:
    """Mengirim notifikasi ke Discord (Unified)."""
    if not webhook_url:
        return
    parsed = urlparse(webhook_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        log.warning("[DISCORD] URL webhook tidak valid, pesan tidak dikirim.")
        return
    try:
        webhook = DiscordWebhook(url=webhook_url)
        embed = DiscordEmbed(title=title, description=msg, color=color)
        embed.set_timestamp()
        embed.set_footer(text="Hoyo Tools")
        webhook.add_embed(embed)
        await asyncio.to_thread(webhook.execute)
    except Exception as e:
        log.error(f"[DISCORD] Gagal mengirim webhook: {e}")


async def send_telegram_message(bot_token: str, chat_id: str, text: str) -> bool:
    """Mengirim satu pesan ke Telegram (Unified)."""
    if not bot_token or not chat_id or not text:
        return False

    def _sync() -> bool:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {"chat_id": chat_id, "text": text}
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return True
        except Exception as e:
            log.error(f"[TELEGRAM] Gagal mengirim pesan: {type(e).__name__}")
            return False

    return await asyncio.to_thread(_sync)


async def send_chunked_telegram(bot_token: str, chat_id: str, lines: list[str]) -> None:
    """Memecah pesan Telegram agar tidak kena limit karakter (4096)."""
    MAX_LENGTH = 4000
    safe_lines: list[str] = []
    for line in lines:
        if len(line) <= MAX_LENGTH:
            safe_lines.append(line)
        else:
            for i in range(0, len(line), MAX_LENGTH):
                safe_lines.append(line[i : i + MAX_LENGTH])

    current_msg = ""
    for line in safe_lines:
        if len(current_msg) + len(line) + 1 > MAX_LENGTH:
            if current_msg:
                await send_telegram_message(bot_token, chat_id, current_msg)
            current_msg = line + "\n"
        else:
            current_msg += line + "\n"

    if current_msg:
        await send_telegram_message(bot_token, chat_id, current_msg)
