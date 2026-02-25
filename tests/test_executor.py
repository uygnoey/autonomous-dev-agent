"""AgentExecutor 테스트."""

from unittest.mock import MagicMock, patch

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

from src.agents.executor import AgentExecutor


def make_mock_query(*messages):
    """테스트용 비동기 제너레이터 팩토리."""
    async def _mock(*args, **kwargs):
        for msg in messages:
            yield msg
    return _mock


def make_assistant_message(text: str) -> AssistantMessage:
    """AssistantMessage mock 생성."""
    mock_block = MagicMock(spec=TextBlock)
    mock_block.text = text
    mock_msg = MagicMock(spec=AssistantMessage)
    mock_msg.content = [mock_block]
    return mock_msg


class TestAgentExecutor:
    def setup_method(self):
        self.executor = AgentExecutor(
            project_path="/tmp/test",
            use_rag=False,
        )

    @pytest.mark.asyncio
    async def test_execute_returns_messages(self):
        mock_msg = make_assistant_message("작업 완료")
        with patch("src.agents.executor.query", new=make_mock_query(mock_msg)):
            result = await self.executor.execute("do task")

        assert len(result) == 1
        assert result[0] is mock_msg

    @pytest.mark.asyncio
    async def test_execute_returns_multiple_messages(self):
        msg1 = make_assistant_message("첫 번째")
        mock_result = MagicMock(spec=ResultMessage)
        with patch("src.agents.executor.query", new=make_mock_query(msg1, mock_result)):
            result = await self.executor.execute("task")

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_execute_handles_exception(self):
        async def error_query(*args, **kwargs):
            raise RuntimeError("API 연결 실패")
            yield  # make it async generator

        with patch("src.agents.executor.query", new=error_query):
            result = await self.executor.execute("task")

        # 에러도 결과에 포함
        assert len(result) == 1
        assert "error" in result[0]
        assert "API 연결 실패" in result[0]["error"]

    @pytest.mark.asyncio
    async def test_execute_with_retry_succeeds_on_first_try(self):
        mock_msg = make_assistant_message("완료")
        with patch("src.agents.executor.query", new=make_mock_query(mock_msg)):
            result = await self.executor.execute_with_retry("task", max_retries=3)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_execute_with_retry_retries_on_error(self):
        mock_msg = make_assistant_message("완료")
        call_count = 0

        async def failing_then_success(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                yield {"error": "일시적 오류"}
            else:
                yield mock_msg

        with patch("src.agents.executor.query", new=failing_then_success):
            result = await self.executor.execute_with_retry("task", max_retries=3)

        # 최종 결과에 에러 없음
        errors = [r for r in result if isinstance(r, dict) and "error" in r]
        assert not errors

    @pytest.mark.asyncio
    async def test_execute_with_retry_returns_after_max_retries(self):
        async def always_fail(*args, **kwargs):
            yield {"error": "계속 실패"}

        with patch("src.agents.executor.query", new=always_fail):
            result = await self.executor.execute_with_retry("task", max_retries=2)

        # 최대 재시도 후 에러 결과 반환
        errors = [r for r in result if isinstance(r, dict) and "error" in r]
        assert errors

    @pytest.mark.asyncio
    async def test_execute_includes_quality_context_in_prompt(self):
        captured_kwargs = {}

        async def capture_query(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return
            yield

        with patch("src.agents.executor.query", new=capture_query):
            await self.executor.execute("내 작업")

        # prompt에 품질 컨텍스트가 포함되어야 함
        prompt = captured_kwargs.get("prompt", "")
        assert "내 작업" in prompt
        assert "필수 준수사항" in prompt

    @pytest.mark.asyncio
    async def test_execute_uses_custom_model(self):
        executor = AgentExecutor(
            project_path="/tmp/test",
            model="claude-custom-model",
            use_rag=False,
        )
        captured_options = {}

        async def capture_query(prompt, options):
            captured_options["model"] = getattr(options, "model", None)
            return
            yield

        with patch("src.agents.executor.query", new=capture_query):
            await executor.execute("task")

        assert captured_options.get("model") == "claude-custom-model"
