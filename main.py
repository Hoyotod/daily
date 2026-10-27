import asyncio
from datetime import datetime

import genshin
from rich.console import Group
from rich.panel import Panel
from rich.table import Table

from utils import (
    CookieInfo,
    DailyInfo,
    censor_uid,
    check_lang,
    console,
    create_genshin_client,
    fix_asyncio_windows_error,
    get_cookies_from_db,
    get_days_of_month,
    is_invalid_cookie,
    log,
    send_chunked_telegram,
    send_discord_embed,
    settings,
)


class DailyClaimer:
    def __init__(self, game: genshin.Game):
        self.game = game
        self._monthly_rewards: list[genshin.models.DailyReward] = []

    async def claim(self, cookie: CookieInfo, lang: str) -> DailyInfo:
        parts = cookie.env_name.split("_", 1)
        display_name = parts[1] if len(parts) > 1 else cookie.env_name

        info = DailyInfo(env_name=display_name)

        client, err = await create_genshin_client(cookie, lang, self.game)
        if err or client is None:
            info.status = "cookie_err"
            return info

        try:
            # 1. Proses Klaim
            try:
                await client.claim_daily_reward(reward=False)
                info.status = "✅"
            except genshin.AlreadyClaimed:
                info.status = "🟡"
            except genshin.GenshinException as e:
                if e.retcode == -10002:
                    info.status = "no_account"
                    return info
                if is_invalid_cookie(e):
                    info.status = "cookie_err"
                    return info
                log.warning(f"[{display_name}] Gagal klaim: {e}")
                info.status = "❌"
                return info

            # 2. Info Reward & Hari
            _, day = await client.get_reward_info()

            if not self._monthly_rewards:
                self._monthly_rewards = list(await client.get_monthly_rewards())

            if (
                not self._monthly_rewards
                or not isinstance(day, int)
                or day < 1
                or day > len(self._monthly_rewards)
            ):
                log.warning(f"[{display_name}] Data reward harian tidak valid.")
                info.status = "ERR"
                return info

            reward = self._monthly_rewards[day - 1]
            info.reward = f"{reward.name} x{reward.amount}"

            total_days = get_days_of_month()
            info.check_in_count = f"{day} / {total_days}"

            # 3. Info Akun
            accounts = await client.get_game_accounts()
            target = next((a for a in accounts if a.game == self.game), None)

            if target:
                info.uid = censor_uid(target.uid)
                info.success = True
            else:
                info.uid = "Unknown"
                info.success = True

        except Exception as e:
            if is_invalid_cookie(e):
                info.status = "cookie_err"
            else:
                log.warning(f"[{display_name}] Error Runtime: {e}")
                info.status = "ERR"

        return info


async def send_chunked_webhook(
    webhook_url: str, title: str, lines: list[str], color: str
) -> None:
    """Memecah pesan Discord agar tidak kena limit karakter."""
    MAX_LENGTH = 1900

    # Pecah baris yang terlalu panjang agar tidak melebihi limit Discord
    safe_lines: list[str] = []
    for line in lines:
        if len(line) <= MAX_LENGTH - 10:
            safe_lines.append(line)
        else:
            chunk_size = MAX_LENGTH - 10
            for i in range(0, len(line), chunk_size):
                safe_lines.append(line[i : i + chunk_size])

    current_msg = "```\n"

    for line in safe_lines:
        if len(current_msg) + len(line) > MAX_LENGTH:
            current_msg += "```"
            await send_discord_embed(webhook_url, title, current_msg, color)
            current_msg = "```\n" + line + "\n"
        else:
            current_msg += line + "\n"

    if current_msg != "```\n":
        current_msg += "```"
        await send_discord_embed(webhook_url, title, current_msg, color)


async def main() -> None:
    fix_asyncio_windows_error()
    cookies = await get_cookies_from_db()
    if not cookies:
        return log.warning("Tidak ada cookie yang ditemukan.")

    lang = check_lang(settings.LOCALE)
    games = {
        "GENSHIN": (genshin.Game.GENSHIN, settings.NO_GENSHIN),
        "STARRAIL": (genshin.Game.STARRAIL, settings.NO_STARRAIL),
        "ZZZ": (genshin.Game.ZZZ, settings.NO_ZZZ),
        "HONKAI": (genshin.Game.HONKAI, settings.NO_HONKAI),
        "TOT": (genshin.Game.TOT, settings.NO_TOT),
    }

    sem = asyncio.Semaphore(settings.MAX_PARALLEL)

    async def limited_claim(
        claimer: DailyClaimer, cookie: CookieInfo, lang: str
    ) -> DailyInfo:
        async with sem:
            return await claimer.claim(cookie, lang)

    results = {}
    async with asyncio.TaskGroup() as tg:
        for name, (game, disabled) in games.items():
            if disabled:
                continue
            claimer = DailyClaimer(game)
            results[name] = [
                tg.create_task(limited_claim(claimer, c, lang)) for c in cookies
            ]

    rich_output = []
    timestamp = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")

    # Global Set untuk menampung error cookie unik
    global_cookie_errors = set()

    # Per-User: webhook -> list[(game_name, DailyInfo)], webhook -> set cookie error
    user_results: dict[str, list[tuple[str, DailyInfo]]] = {}
    user_cookie_errors: dict[str, set[str]] = {}

    # Per-User Telegram: chat_id -> list[(game_name, DailyInfo)], chat_id -> set cookie error
    user_telegram_results: dict[str, list[tuple[str, DailyInfo]]] = {}
    user_telegram_cookie_errors: dict[str, set[str]] = {}

    # Status display mapping untuk tabel
    STATUS_DISPLAY = {
        "cookie_err": "❌ Cookie",
        "no_account": "⚪ No Account",
        "ERR": "❌ Runtime",
    }

    for name, tasks in results.items():
        infos = [t.result() for t in tasks]

        # Table Terminal: Tampilkan SEMUA status (termasuk no_account/cookie_err) agar user tahu di console
        table = Table(title=f"🎮 {name}", expand=True)
        table.add_column("Akun", style="cyan")
        table.add_column("UID", style="dim")
        table.add_column("Hari", justify="center", style="magenta")
        table.add_column("Status", justify="center")
        table.add_column("Reward", style="green", justify="right")

        # List Pesan Discord per Game
        success_lines = []
        error_lines = []

        has_valid_info = False

        for i, cookie in zip(infos, cookies, strict=True):
            # Tambahkan ke Terminal (Semua)
            display_status = STATUS_DISPLAY.get(i.status, i.status)
            table.add_row(i.env_name, i.uid, i.check_in_count, display_status, i.reward)

            # --- LOGIKA FILTER WEBHOOK ---

            # 1. Skip no_account sepenuhnya dari webhook
            if i.status == "no_account":
                continue

            has_valid_info = True

            # 2. Tangkap Cookie Error (Jangan kirim sekarang)
            if i.status == "cookie_err":
                global_cookie_errors.add(i.env_name)
                if cookie.user_webhook:
                    user_results.setdefault(cookie.user_webhook, []).append((name, i))
                    user_cookie_errors.setdefault(cookie.user_webhook, set()).add(
                        i.env_name
                    )
                if cookie.telegram_chat_id:
                    user_telegram_results.setdefault(
                        cookie.telegram_chat_id, []
                    ).append((name, i))
                    user_telegram_cookie_errors.setdefault(
                        cookie.telegram_chat_id, set()
                    ).add(i.env_name)
                continue

            # 3. Pisahkan Sukses dan Error Lainnya
            if i.status in ["✅", "🟡"]:
                success_lines.append(
                    f"{i.status} {i.env_name} ({i.uid}): Day {i.check_in_count}"
                )
                if cookie.user_webhook:
                    user_results.setdefault(cookie.user_webhook, []).append((name, i))
                if cookie.telegram_chat_id:
                    user_telegram_results.setdefault(
                        cookie.telegram_chat_id, []
                    ).append((name, i))
            else:
                # Error runtime lain (misal timeout, captcha, dll)
                error_lines.append(f"❌ {i.env_name}: {i.status}")
                if cookie.user_webhook:
                    user_results.setdefault(cookie.user_webhook, []).append((name, i))
                if cookie.telegram_chat_id:
                    user_telegram_results.setdefault(
                        cookie.telegram_chat_id, []
                    ).append((name, i))

        if has_valid_info:
            rich_output.append(table)

        if settings.DISCORD_WEBHOOK_URL:
            # Kirim Sukses Per Game
            if success_lines:
                await send_chunked_webhook(
                    settings.DISCORD_WEBHOOK_URL,
                    f"Daily Check-In - {name}",
                    success_lines,
                    "00ff00",
                )

            # Kirim Error Game Spesifik (Bukan Cookie)
            if error_lines:
                await send_chunked_webhook(
                    settings.DISCORD_WEBHOOK_URL,
                    f"⚠️ Daily Error - {name}",
                    error_lines,
                    "ff0000",
                )

        # Telegram (global)
        if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID:
            if success_lines:
                await send_chunked_telegram(
                    settings.TELEGRAM_BOT_TOKEN,
                    settings.TELEGRAM_CHAT_ID,
                    [f"Daily Check-In - {name}"] + success_lines,
                )
            if error_lines:
                await send_chunked_telegram(
                    settings.TELEGRAM_BOT_TOKEN,
                    settings.TELEGRAM_CHAT_ID,
                    [f"⚠️ Daily Error - {name}"] + error_lines,
                )

    # --- FINAL REPORT: COOKIE ERRORS ---
    # Dikirim sekali saja di akhir, mencakup semua game
    if global_cookie_errors and settings.DISCORD_WEBHOOK_URL:
        err_names = ", ".join(sorted(global_cookie_errors))
        error_msg = [f"❌ Invalid Cookies ({len(global_cookie_errors)}): {err_names}"]
        await send_chunked_webhook(
            settings.DISCORD_WEBHOOK_URL, "⚠️ Account Alert", error_msg, "ff0000"
        )

    if (
        global_cookie_errors
        and settings.TELEGRAM_BOT_TOKEN
        and settings.TELEGRAM_CHAT_ID
    ):
        err_names = ", ".join(sorted(global_cookie_errors))
        await send_chunked_telegram(
            settings.TELEGRAM_BOT_TOKEN,
            settings.TELEGRAM_CHAT_ID,
            [
                "⚠️ Account Alert",
                f"❌ Invalid Cookies ({len(global_cookie_errors)}): {err_names}",
            ],
        )

    # --- PER-USER REPORT ---
    # Kirim laporan ke webhook masing-masing user setelah webhook global
    for wh, items in user_results.items():
        user_success: dict[str, list[str]] = {}
        user_error: dict[str, list[str]] = {}

        for game_name, info in items:
            # Pisahkan Sukses dan Error (cookie_err sudah ditangkap di user_cookie_errors)
            if info.status in ["✅", "🟡"]:
                user_success.setdefault(game_name, []).append(
                    f"{info.status} {info.env_name} ({info.uid}): Day {info.check_in_count}"
                )
            elif info.status not in ("no_account", "cookie_err"):
                user_error.setdefault(game_name, []).append(
                    f"❌ {info.env_name}: {info.status}"
                )

        # Kirim Sukses Per Game
        for game_name, lines in user_success.items():
            await send_chunked_webhook(
                wh, f"Daily Check-In - {game_name}", lines, "00ff00"
            )

        # Kirim Error Game Spesifik (Bukan Cookie)
        for game_name, lines in user_error.items():
            await send_chunked_webhook(
                wh, f"⚠️ Daily Error - {game_name}", lines, "ff0000"
            )

        # Cookie Error Khusus User Ini
        err_names_set = user_cookie_errors.get(wh)
        if err_names_set:
            err_list = ", ".join(sorted(err_names_set))
            error_msg = [f"❌ Invalid Cookies ({len(err_names_set)}): {err_list}"]
            await send_chunked_webhook(wh, "⚠️ Account Alert", error_msg, "ff0000")

    # --- PER-USER TELEGRAM REPORT ---
    bot_token = settings.TELEGRAM_BOT_TOKEN
    for chat_id, items in user_telegram_results.items():
        if not bot_token:
            break
        tg_user_success: dict[str, list[str]] = {}
        tg_user_error: dict[str, list[str]] = {}

        for game_name, info in items:
            if info.status in ["✅", "🟡"]:
                tg_user_success.setdefault(game_name, []).append(
                    f"{info.status} {info.env_name} ({info.uid}): Day {info.check_in_count}"
                )
            elif info.status not in ("no_account", "cookie_err"):
                tg_user_error.setdefault(game_name, []).append(
                    f"❌ {info.env_name}: {info.status}"
                )

        for game_name, lines in tg_user_success.items():
            await send_chunked_telegram(
                bot_token, chat_id, [f"Daily Check-In - {game_name}"] + lines
            )
        for game_name, lines in tg_user_error.items():
            await send_chunked_telegram(
                bot_token, chat_id, [f"⚠️ Daily Error - {game_name}"] + lines
            )

        err_names_set = user_telegram_cookie_errors.get(chat_id)
        if err_names_set:
            err_list = ", ".join(sorted(err_names_set))
            await send_chunked_telegram(
                bot_token,
                chat_id,
                [
                    "⚠️ Account Alert",
                    f"❌ Invalid Cookies ({len(err_names_set)}): {err_list}",
                ],
            )

    if rich_output:
        console.print(Panel(Group(*rich_output), title=f"Daily Report - {timestamp}"))
    else:
        console.print("[yellow]Tidak ada aktivitas daily yang valid.[/yellow]")


if __name__ == "__main__":
    asyncio.run(main())
