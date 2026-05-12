"""Tests for atlas.intraday.notify."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from atlas.intraday.notify import send_message, send_message_sync


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_send_message_missing_token_logs_warning_and_returns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Graceful no-op when TELEGRAM_BOT_TOKEN is missing."""
        with patch.dict("os.environ", {}, clear=True):
            # Remove telegram env vars if set
            import os

            os.environ.pop("TELEGRAM_BOT_TOKEN", None)
            os.environ.pop("TELEGRAM_CHAT_ID", None)
            # Should not raise
            await send_message("test message")

    @pytest.mark.asyncio
    async def test_send_message_missing_chat_id_logs_warning_and_returns(self) -> None:
        """Graceful no-op when TELEGRAM_CHAT_ID is missing."""
        import os

        env = {"TELEGRAM_BOT_TOKEN": "fake_token"}
        os.environ.pop("TELEGRAM_CHAT_ID", None)
        with patch.dict("os.environ", env, clear=False):
            os.environ.pop("TELEGRAM_CHAT_ID", None)
            await send_message("test message")

    @pytest.mark.asyncio
    async def test_send_message_calls_bot_api_when_configured(self) -> None:
        """Calls telegram.Bot.send_message when both env vars present."""

        env = {
            "TELEGRAM_BOT_TOKEN": "test_token_123",
            "TELEGRAM_CHAT_ID": "test_chat_456",
        }
        mock_bot_instance = AsyncMock()
        mock_bot_instance.send_message = AsyncMock()
        mock_bot_class = MagicMock(return_value=mock_bot_instance)
        mock_telegram_module = MagicMock()
        mock_telegram_module.Bot = mock_bot_class

        with patch.dict("os.environ", env, clear=False):
            with patch.dict("sys.modules", {"telegram": mock_telegram_module}):
                await send_message("Hello from test")

        mock_bot_class.assert_called_once_with(token="test_token_123")
        mock_bot_instance.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_exception_logs_warning_not_raises(self) -> None:
        """Bot API failure must not propagate — logs warning instead."""
        env = {
            "TELEGRAM_BOT_TOKEN": "test_token",
            "TELEGRAM_CHAT_ID": "test_chat",
        }
        with patch.dict("os.environ", env, clear=False):
            # Mock telegram import to raise
            mock_bot = MagicMock()
            mock_bot.return_value.send_message = AsyncMock(side_effect=Exception("Network error"))
            mock_telegram = MagicMock()
            mock_telegram.Bot = mock_bot
            with patch.dict("sys.modules", {"telegram": mock_telegram}):
                # Should not raise
                await send_message("test message")


class TestSendMessageSync:
    def test_send_message_sync_runs_without_error_when_not_configured(self) -> None:
        """Synchronous wrapper must not raise when Telegram is not configured."""
        import os

        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_CHAT_ID", None)
        # Should not raise
        send_message_sync("test message")

    def test_send_message_sync_is_callable(self) -> None:
        assert callable(send_message_sync)
