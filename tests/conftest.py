from unittest.mock import AsyncMock, MagicMock

import genshin
import pytest

from utils import CookieInfo, DailyInfo


@pytest.fixture
def mock_cookie() -> CookieInfo:
    return CookieInfo(
        env_name="ACC1_TEST_USER",
        cookies="account_id_v2=123456; cookie_token_v2=abcdef",
        user_webhook=None,
    )


@pytest.fixture
def mock_cookie_with_webhook() -> CookieInfo:
    return CookieInfo(
        env_name="ACC2_WEBHOOK_USER",
        cookies="account_id_v2=789012; cookie_token_v2=ghijkl",
        user_webhook="https://discord.com/api/webhooks/test",
    )


@pytest.fixture
def mock_daily_info() -> DailyInfo:
    return DailyInfo(
        uid="123456■■■■■7",
        status="✅",
        check_in_count="15 / 31",
        reward="Primogem x50",
        success=True,
        env_name="ACC1_TEST_USER",
    )


@pytest.fixture
def mock_genshin_client() -> MagicMock:
    client = MagicMock(spec=genshin.Client)
    client.claim_daily_reward = AsyncMock()
    client.get_reward_info = AsyncMock(return_value=(None, 15))
    client.get_monthly_rewards = AsyncMock()
    client.get_game_accounts = AsyncMock()
    return client


@pytest.fixture
def mock_game_account() -> MagicMock:
    account = MagicMock()
    account.game = genshin.Game.GENSHIN
    account.uid = 1234567890
    return account


@pytest.fixture
def mock_reward() -> MagicMock:
    reward = MagicMock()
    reward.name = "Primogem"
    reward.amount = 50
    return reward


@pytest.fixture
def mock_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "")
    monkeypatch.setenv("LOCALE", "en-us")
    monkeypatch.setenv("MAX_PARALLEL", "5")
    monkeypatch.setenv("NO_GENSHIN", "False")
    monkeypatch.setenv("NO_STARRAIL", "False")
    monkeypatch.setenv("NO_ZZZ", "False")
    monkeypatch.setenv("NO_HONKAI", "False")
    monkeypatch.setenv("NO_TOT", "True")
