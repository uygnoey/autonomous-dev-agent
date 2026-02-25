"""토큰 한도 관리기.

토큰 한도에 도달하면 리셋될 때까지 대기한 후 이어서 진행한다.
절대로 중단하지 않는다.
"""

import asyncio
import time

import anthropic

from src.utils.logger import setup_logger

logger = setup_logger(__name__)

# 기본 대기 시간 (초)
DEFAULT_WAIT_SECONDS = 60
MAX_WAIT_SECONDS = 300  # 최대 5분


class TokenManager:
    """토큰 사용량을 추적하고 한도 초과 시 대기한다."""

    def __init__(
        self,
        wait_seconds: int = DEFAULT_WAIT_SECONDS,
        max_wait_seconds: int = MAX_WAIT_SECONDS,
    ):
        self._wait_seconds = wait_seconds
        self._max_wait_seconds = max_wait_seconds
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._last_rate_limit_at: float | None = None
        self._consecutive_limits = 0

    def record_usage(self, input_tokens: int, output_tokens: int) -> None:
        """토큰 사용량을 기록한다."""
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens

    async def wait_if_needed(self) -> None:
        """rate limit 직후라면 충분히 대기한다."""
        if self._last_rate_limit_at is None:
            return

        elapsed = time.time() - self._last_rate_limit_at
        if elapsed < self._wait_seconds:
            remaining = self._wait_seconds - elapsed
            logger.info(f"Rate limit 쿨다운 대기: {remaining:.0f}초")
            await asyncio.sleep(remaining)

    async def wait_for_reset(self) -> None:
        """토큰 한도 초과 시 리셋될 때까지 대기한다.

        지수 백오프로 대기 시간을 늘린다.
        절대로 포기하지 않고, 리셋될 때까지 계속 대기한다.
        """
        self._consecutive_limits += 1
        self._last_rate_limit_at = time.time()

        # 지수 백오프: 60초 → 120초 → 240초 → 최대 max_wait_seconds
        wait = min(
            self._wait_seconds * (2 ** (self._consecutive_limits - 1)),
            self._max_wait_seconds,
        )

        logger.warning(
            f"토큰 한도 초과 (연속 {self._consecutive_limits}회). "
            f"{wait}초 대기 후 재시도..."
        )
        await asyncio.sleep(wait)

        # 대기 후 API 호출 가능한지 테스트
        if await self._test_api_available():
            self._consecutive_limits = 0
            self._last_rate_limit_at = None
            logger.info("API 사용 가능. 작업 재개.")
        else:
            # 아직 안 되면 재귀적으로 다시 대기
            await self.wait_for_reset()

    async def _test_api_available(self) -> bool:
        """API가 사용 가능한지 간단히 테스트한다."""
        try:
            client = anthropic.Anthropic()
            client.messages.create(
                model="claude-haiku-4-5-20251001",  # 가장 저렴한 모델로 테스트
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except anthropic.RateLimitError:
            return False
        except Exception:
            # 다른 에러는 rate limit이 아니므로 사용 가능으로 간주
            return True

    @property
    def total_tokens(self) -> int:
        """총 사용 토큰 수."""
        return self._total_input_tokens + self._total_output_tokens

    def get_usage_summary(self) -> dict:
        """사용량 요약을 반환한다."""
        return {
            "input_tokens": self._total_input_tokens,
            "output_tokens": self._total_output_tokens,
            "total_tokens": self.total_tokens,
            "consecutive_limits": self._consecutive_limits,
        }
