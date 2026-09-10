from unittest.mock import AsyncMock, MagicMock, patch

import genshin
import pytest

from main import DailyClaimer, send_chunked_webhook
from utils import CookieInfo


class TestDailyClaimer:
    @pytest.mark.asyncio
    async def test_claim_success(
        self,
        mock_cookie: CookieInfo,
        mock_genshin_client: MagicMock,
        mock_game_account: MagicMock,
        mock_reward: MagicMock,
    ) -> None:
        from utils import get_days_of_month

        claimer = DailyClaimer(genshin.Game.GENSHIN)
        claimer._monthly_rewards = [mock_reward] * 31

        mock_genshin_client.get_reward_info.return_value = (None, 15)
        mock_genshin_client.get_game_accounts.return_value = [mock_game_account]

        with patch(
            "main.create_genshin_client", return_value=(mock_genshin_client, None)
        ):
            result = await claimer.claim(mock_cookie, "en-us")

        expected_days = get_days_of_month()
        assert result.status == "✅"
        assert result.success is True
        assert result.check_in_count == f"15 / {expected_days}"
        assert result.reward == "Primogem x50"
        assert "■■■■■" in result.uid

    @pytest.mark.asyncio
    async def test_claim_already_claimed(
        self,
        mock_cookie: CookieInfo,
        mock_genshin_client: MagicMock,
        mock_game_account: MagicMock,
        mock_reward: MagicMock,
    ) -> None:
        claimer = DailyClaimer(genshin.Game.GENSHIN)
        claimer._monthly_rewards = [mock_reward] * 31

        mock_genshin_client.claim_daily_reward.side_effect = genshin.AlreadyClaimed()
        mock_genshin_client.get_reward_info.return_value = (None, 15)
        mock_genshin_client.get_game_accounts.return_value = [mock_game_account]

        with patch(
            "main.create_genshin_client", return_value=(mock_genshin_client, None)
        ):
            result = await claimer.claim(mock_cookie, "en-us")

        assert result.status == "🟡"
        assert result.success is True

    @pytest.mark.asyncio
    async def test_claim_cookie_error(self, mock_cookie: CookieInfo) -> None:
        claimer = DailyClaimer(genshin.Game.GENSHIN)

        with patch("main.create_genshin_client", return_value=(None, "Invalid cookie")):
            result = await claimer.claim(mock_cookie, "en-us")

        assert result.status == "cookie_err"
        assert result.success is False

    @pytest.mark.asyncio
    async def test_claim_no_account(
        self, mock_cookie: CookieInfo, mock_genshin_client: MagicMock
    ) -> None:
        claimer = DailyClaimer(genshin.Game.GENSHIN)

        exc = genshin.GenshinException()
        exc.retcode = -10002
        mock_genshin_client.claim_daily_reward.side_effect = exc

        with patch(
            "main.create_genshin_client", return_value=(mock_genshin_client, None)
        ):
            result = await claimer.claim(mock_cookie, "en-us")

        assert result.status == "no_account"
        assert result.success is False

    @pytest.mark.asyncio
    async def test_claim_invalid_cookie_during_claim(
        self, mock_cookie: CookieInfo, mock_genshin_client: MagicMock
    ) -> None:
        claimer = DailyClaimer(genshin.Game.GENSHIN)

        exc = genshin.errors.InvalidCookies()
        mock_genshin_client.claim_daily_reward.side_effect = exc

        with patch(
            "main.create_genshin_client", return_value=(mock_genshin_client, None)
        ):
            result = await claimer.claim(mock_cookie, "en-us")

        assert result.status == "cookie_err"
        assert result.success is False

    @pytest.mark.asyncio
    async def test_claim_generic_error(
        self, mock_cookie: CookieInfo, mock_genshin_client: MagicMock
    ) -> None:
        claimer = DailyClaimer(genshin.Game.GENSHIN)

        exc = genshin.GenshinException()
        exc.retcode = 9999
        mock_genshin_client.claim_daily_reward.side_effect = exc

        with patch(
            "main.create_genshin_client", return_value=(mock_genshin_client, None)
        ):
            result = await claimer.claim(mock_cookie, "en-us")

        assert result.status == "❌"
        assert result.success is False

    @pytest.mark.asyncio
    async def test_claim_unknown_uid(
        self,
        mock_cookie: CookieInfo,
        mock_genshin_client: MagicMock,
        mock_reward: MagicMock,
    ) -> None:
        claimer = DailyClaimer(genshin.Game.GENSHIN)
        claimer._monthly_rewards = [mock_reward] * 31

        mock_genshin_client.get_reward_info.return_value = (None, 15)
        mock_genshin_client.get_game_accounts.return_value = []

        with patch(
            "main.create_genshin_client", return_value=(mock_genshin_client, None)
        ):
            result = await claimer.claim(mock_cookie, "en-us")

        assert result.uid == "Unknown"
        assert result.success is True


class TestSendChunkedWebhook:
    @pytest.mark.asyncio
    async def test_send_single_message(self) -> None:
        lines = ["Line 1", "Line 2", "Line 3"]

        with patch("main.send_discord_embed", new_callable=AsyncMock) as mock_send:
            await send_chunked_webhook(
                "https://webhook.url", "Test Title", lines, "00ff00"
            )

        mock_send.assert_called_once()
        call_args = mock_send.call_args[0]
        assert call_args[0] == "https://webhook.url"
        assert call_args[1] == "Test Title"
        assert "Line 1" in call_args[2]
        assert "Line 2" in call_args[2]
        assert "Line 3" in call_args[2]

    @pytest.mark.asyncio
    async def test_send_chunked_messages(self) -> None:
        lines = ["Line with some extra content " + str(i) * 50 for i in range(100)]

        with patch("main.send_discord_embed", new_callable=AsyncMock) as mock_send:
            await send_chunked_webhook(
                "https://webhook.url", "Test Title", lines, "00ff00"
            )

        assert mock_send.call_count > 1

    @pytest.mark.asyncio
    async def test_send_empty_lines(self) -> None:
        lines: list[str] = []

        with patch("main.send_discord_embed", new_callable=AsyncMock) as mock_send:
            await send_chunked_webhook(
                "https://webhook.url", "Test Title", lines, "00ff00"
            )

        mock_send.assert_not_called()
