"""TokenManager 유닛 테스트."""

import asyncio
import pytest

from src.orchestrator.token_manager import TokenManager, DEFAULT_WAIT_SECONDS


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
        # 대기 없이 즉시 반환되어야 함
        await asyncio.wait_for(manager.wait_if_needed(), timeout=0.1)

    async def test_wait_if_needed_skips_when_cooldown_elapsed(self):
        """쿨다운이 지났으면 대기하지 않는다."""
        import time
        manager = TokenManager(wait_seconds=1)
        manager._last_rate_limit_at = time.time() - 2  # 2초 전에 rate limit
        # 쿨다운(1초)이 지났으므로 즉시 반환
        await asyncio.wait_for(manager.wait_if_needed(), timeout=0.1)

    def test_total_tokens_property(self):
        manager = TokenManager()
        manager._total_input_tokens = 300
        manager._total_output_tokens = 200
        assert manager.total_tokens == 500
