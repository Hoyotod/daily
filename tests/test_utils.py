from calendar import monthrange
from datetime import datetime

import genshin

from utils import (
    CookieInfo,
    DailyInfo,
    censor_uid,
    check_lang,
    format_name,
    get_days_of_month,
    is_invalid_cookie,
)


class TestCheckLang:
    def test_valid_languages(self) -> None:
        valid_langs = [
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
        ]
        for lang in valid_langs:
            assert check_lang(lang) == lang
            assert check_lang(lang.upper()) == lang

    def test_invalid_language_fallback(self) -> None:
        assert check_lang("invalid-lang") == "en-us"
        assert check_lang("xx-xx") == "en-us"
        assert check_lang("") == "en-us"


class TestCensorUid:
    def test_censor_long_uid(self) -> None:
        assert censor_uid("1234567890") == "1234■■■■■0"
        assert censor_uid(1234567890) == "1234■■■■■0"

    def test_censor_short_uid(self) -> None:
        assert censor_uid("12345") == "12345"
        assert censor_uid("") == ""
        assert censor_uid("1") == "1"

    def test_censor_exact_six_chars(self) -> None:
        assert censor_uid("123456") == "■■■■■6"

    def test_censor_seven_chars(self) -> None:
        assert censor_uid("1234567") == "1■■■■■7"


class TestFormatName:
    def test_basic_formatting(self) -> None:
        assert format_name("test user") == "TEST_USER"
        assert format_name("test-user") == "TEST_USER"
        assert format_name("test.user") == "TEST_USER"

    def test_special_characters(self) -> None:
        assert format_name("test@user#123") == "TEST_USER_123"
        assert format_name("user!name$here") == "USER_NAME_HERE"

    def test_multiple_spaces(self) -> None:
        assert format_name("test   user") == "TEST_USER"

    def test_edge_cases(self) -> None:
        assert format_name("a") == "A"
        assert format_name("ABC123") == "ABC123"
        assert format_name("_test_") == "_TEST_"


class TestGetDaysOfMonth:
    def test_current_month_days(self) -> None:
        now = datetime.now()
        expected_days = monthrange(now.year, now.month)[1]
        assert get_days_of_month() == expected_days


class TestIsInvalidCookie:
    def test_invalid_cookies_exception(self) -> None:
        exc = genshin.errors.InvalidCookies()
        assert is_invalid_cookie(exc) is True

    def test_cookie_exception(self) -> None:
        exc = genshin.errors.CookieException()
        assert is_invalid_cookie(exc) is True

    def test_genshin_exception_with_invalid_retcodes(self) -> None:
        invalid_retcodes = [-100, 10001, 10103, -1071, -3203, -707]
        for retcode in invalid_retcodes:
            exc = genshin.errors.GenshinException()
            exc.retcode = retcode
            assert is_invalid_cookie(exc) is True, (
                f"retcode {retcode} should be invalid"
            )

    def test_genshin_exception_with_valid_retcode(self) -> None:
        exc = genshin.errors.GenshinException()
        exc.retcode = 0
        assert is_invalid_cookie(exc) is False

        exc.retcode = -10002
        assert is_invalid_cookie(exc) is False

    def test_non_cookie_exception(self) -> None:
        exc = ValueError("Some other error")
        assert is_invalid_cookie(exc) is False

        exc_runtime = RuntimeError("Runtime error")
        assert is_invalid_cookie(exc_runtime) is False


class TestCookieInfo:
    def test_cookie_info_creation(self) -> None:
        cookie = CookieInfo(
            env_name="TEST_USER",
            cookies="account_id_v2=123; cookie_token_v2=abc",
            user_webhook="https://discord.com/webhook",
        )
        assert cookie.env_name == "TEST_USER"
        assert cookie.cookies == "account_id_v2=123; cookie_token_v2=abc"
        assert cookie.user_webhook == "https://discord.com/webhook"

    def test_cookie_info_defaults(self) -> None:
        cookie = CookieInfo()
        assert cookie.env_name == ""
        assert cookie.cookies == ""
        assert cookie.user_webhook is None


class TestDailyInfo:
    def test_daily_info_creation(self) -> None:
        info = DailyInfo(
            uid="123456■■■■■0",
            status="✅",
            check_in_count="15 / 31",
            reward="Primogem x50",
            success=True,
            env_name="TEST_USER",
        )
        assert info.uid == "123456■■■■■0"
        assert info.status == "✅"
        assert info.check_in_count == "15 / 31"
        assert info.reward == "Primogem x50"
        assert info.success is True
        assert info.env_name == "TEST_USER"

    def test_daily_info_defaults(self) -> None:
        info = DailyInfo()
        assert info.uid == "❓"
        assert info.status == "❌"
        assert info.check_in_count == "❓"
        assert info.reward == "❓"
        assert info.success is False
        assert info.env_name == "❓"
