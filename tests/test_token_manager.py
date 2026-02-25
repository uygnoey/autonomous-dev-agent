"""TokenManager 유닛 테스트."""

import asyncio
import time
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from src.orchestrator.token_manager import TokenManager


class TestTokenManager:
    def test_initial_state(self):
        manager = TokenManager()
        assert manager.total_tokens == 0
        assert manager._consecutive_limits == 0
        assert manager._last_rate_limit_at is None

    def test_record_usage(self):
        manager = TokenManager()
        manager.record_usage(100, 50)
        assert manager.total_tokens == 150

        manager.record_usage(200, 100)
        assert manager.total_tokens == 450

    def test_get_usage_summary(self):
        manager = TokenManager()
        manager.record_usage(100, 50)

        summary = manager.get_usage_summary()
        assert summary["input_tokens"] == 100
        assert summary["output_tokens"] == 50
        assert summary["total_tokens"] == 150
        assert summary["consecutive_limits"] == 0

    async def test_wait_if_needed_skips_when_no_rate_limit(self):
        """rate limit이 없으면 대기하지 않는다."""
        manager = TokenManager()
        await asyncio.wait_for(manager.wait_if_needed(), timeout=0.1)

    async def test_wait_if_needed_skips_when_cooldown_elapsed(self):
        """쿨다운이 지났으면 대기하지 않는다."""
        manager = TokenManager(wait_seconds=1)
        manager._last_rate_limit_at = time.time() - 2  # 2초 전에 rate limit
        await asyncio.wait_for(manager.wait_if_needed(), timeout=0.1)

    def test_total_tokens_property(self):
        manager = TokenManager()
        manager._total_input_tokens = 300
        manager._total_output_tokens = 200
        assert manager.total_tokens == 500

    @pytest.mark.asyncio
    async def test_wait_if_needed_sleeps_when_in_cooldown(self):
        """쿨다운 중이면 남은 시간만큼 대기한다."""
        manager = TokenManager(wait_seconds=10)
        manager._last_rate_limit_at = time.time() - 5  # 5초 전 → 5초 남음

        with patch("src.orchestrator.token_manager.asyncio.sleep") as mock_sleep:
            mock_sleep.return_value = None
            await manager.wait_if_needed()

        mock_sleep.assert_called_once()
        sleep_duration = mock_sleep.call_args[0][0]
        # 약 5초 남음 (±1초 허용)
        assert 4 <= sleep_duration <= 6

    @pytest.mark.asyncio
    async def test_wait_for_reset_increments_consecutive_limits(self):
        """wait_for_reset 호출 시 consecutive_limits가 증가한다."""
        manager = TokenManager(wait_seconds=1)

        with (
            patch("src.orchestrator.token_manager.asyncio.sleep"),
            patch.object(manager, "_test_api_available", return_value=True),
        ):
            await manager.wait_for_reset()

        assert manager._consecutive_limits == 0  # 리셋됨
        assert manager._last_rate_limit_at is None  # 클리어됨

    @pytest.mark.asyncio
    async def test_wait_for_reset_exponential_backoff(self):
        """지수 백오프로 대기 시간이 늘어난다."""
        manager = TokenManager(wait_seconds=10)
        manager._consecutive_limits = 1  # 이미 1회 했다고 가정

        sleep_calls = []
        with (
            patch(
                "src.orchestrator.token_manager.asyncio.sleep",
                side_effect=lambda t: sleep_calls.append(t),
            ),
            patch.object(manager, "_test_api_available", return_value=True),
        ):
            await manager.wait_for_reset()

        # consecutive_limits=1 → wait_seconds * 2^(2-1) = 10 * 2 = 20초
        assert sleep_calls[0] == 20

    @pytest.mark.asyncio
    async def test_test_api_available_returns_true_on_success(self):
        """API 호출 성공 시 True를 반환한다."""
        manager = TokenManager()
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock()

        with patch("src.orchestrator.token_manager.anthropic.Anthropic", return_value=mock_client):
            result = await manager._test_api_available()

        assert result is True

    @pytest.mark.asyncio
    async def test_test_api_available_returns_false_on_rate_limit(self):
        """RateLimitError 시 False를 반환한다."""
        manager = TokenManager()
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = anthropic.RateLimitError(
            message="rate limit",
            response=MagicMock(headers={}),
            body=None,
        )

        with patch("src.orchestrator.token_manager.anthropic.Anthropic", return_value=mock_client):
            result = await manager._test_api_available()

        assert result is False

    @pytest.mark.asyncio
    async def test_test_api_available_returns_true_on_other_error(self):
        """다른 에러는 rate limit이 아니므로 True를 반환한다."""
        manager = TokenManager()
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = ConnectionError("네트워크 오류")

        with patch("src.orchestrator.token_manager.anthropic.Anthropic", return_value=mock_client):
            result = await manager._test_api_available()

        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_reset_retries_when_api_unavailable(self):
        """API 아직 안 될 때 재귀적으로 다시 대기한다. (line 75)"""
        manager = TokenManager(wait_seconds=1)
        call_count = 0

        async def api_available():
            nonlocal call_count
            call_count += 1
            return call_count >= 2  # 첫번째 False, 두번째부터 True

        with (
            patch("src.orchestrator.token_manager.asyncio.sleep"),
            patch.object(manager, "_test_api_available", side_effect=api_available),
        ):
            await manager.wait_for_reset()

        assert call_count == 2
        assert manager._consecutive_limits == 0
