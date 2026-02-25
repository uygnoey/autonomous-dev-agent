"""claude_client 모듈 테스트."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCallViaApi:
    def test_returns_text_from_text_block(self):
        from anthropic.types import TextBlock

        from src.utils.claude_client import _call_via_api

        mock_block = MagicMock(spec=TextBlock)
        mock_block.text = "task result"
        mock_response = MagicMock()
        mock_response.content = [mock_block]

        with patch("src.utils.claude_client.anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = _call_via_api("system", "user", "model", 1024)

        assert result == "task result"
        mock_client.messages.create.assert_called_once_with(
            model="model",
            max_tokens=1024,
            system="system",
            messages=[{"role": "user", "content": "user"}],
        )

    def test_raises_on_non_text_block(self):
        from src.utils.claude_client import _call_via_api

        mock_block = MagicMock()  # spec 없이 → isinstance 체크 실패
        mock_response = MagicMock()
        mock_response.content = [mock_block]

        with patch("src.utils.claude_client.anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            with pytest.raises(ValueError, match="예상치 못한 응답 블록 타입"):
                _call_via_api("system", "user", "model", 1024)


class TestCallViaSdk:
    @pytest.mark.asyncio
    async def test_returns_text_from_assistant_message(self):
        from claude_agent_sdk import AssistantMessage, TextBlock

        from src.utils.claude_client import _call_via_sdk

        mock_block = MagicMock(spec=TextBlock)
        mock_block.text = "sdk response"
        mock_msg = MagicMock(spec=AssistantMessage)
        mock_msg.content = [mock_block]

        async def mock_query(**kwargs):
            yield mock_msg

        with patch("src.utils.claude_client.query", new=mock_query):
            result = await _call_via_sdk("system", "user", "model")

        assert result == "sdk response"

    @pytest.mark.asyncio
    async def test_returns_empty_string_when_no_text(self):
        from src.utils.claude_client import _call_via_sdk

        async def mock_query(**kwargs):
            return
            yield  # make it an async generator

        with patch("src.utils.claude_client.query", new=mock_query):
            result = await _call_via_sdk("system", "user", "model")

        assert result == ""


class TestCallClaudeForText:
    @pytest.mark.asyncio
    async def test_uses_api_when_api_key_set(self):
        from src.utils.claude_client import call_claude_for_text

        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}),
            patch(
                "src.utils.claude_client._call_via_api",
                return_value="api result",
            ) as mock_api,
            patch("src.utils.claude_client._call_via_sdk") as mock_sdk,
        ):
            result = await call_claude_for_text("sys", "user")

        assert result == "api result"
        mock_api.assert_called_once()
        mock_sdk.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_sdk_when_no_api_key(self):
        from src.utils.claude_client import call_claude_for_text

        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch("src.utils.claude_client._call_via_api") as mock_api,
            patch(
                "src.utils.claude_client._call_via_sdk",
                new=AsyncMock(return_value="sdk result"),
            ) as mock_sdk,
        ):
            result = await call_claude_for_text("sys", "user")

        assert result == "sdk result"
        mock_api.assert_not_called()
        mock_sdk.assert_called_once()
