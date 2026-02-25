"""Planner 테스트."""

from unittest.mock import AsyncMock, patch

import pytest

from src.orchestrator.planner import Planner
from src.utils.state import PhaseType, ProjectState


class TestPlanner:
    def setup_method(self):
        self.planner = Planner(model="claude-test-model")
        self.state = ProjectState(spec="테스트 스펙 내용")

    @pytest.mark.asyncio
    async def test_decide_next_task_returns_task_prompt(self):
        expected = "다음 작업: 로그인 API 구현"
        with patch(
            "src.orchestrator.planner.call_claude_for_text",
            new=AsyncMock(return_value=expected),
        ):
            result = await self.planner.decide_next_task(self.state)

        assert result == expected

    @pytest.mark.asyncio
    async def test_decide_next_task_calls_with_correct_system_prompt(self):
        with patch(
            "src.orchestrator.planner.call_claude_for_text",
            new=AsyncMock(return_value="task"),
        ) as mock_call:
            await self.planner.decide_next_task(self.state)

        call_kwargs = mock_call.call_args
        assert "system" in call_kwargs.kwargs or call_kwargs.args
        # system prompt에 핵심 규칙 포함 확인
        called_system = call_kwargs.kwargs.get("system") or call_kwargs.args[0]
        assert "테크 리드" in called_system or "프로젝트 매니저" in called_system

    @pytest.mark.asyncio
    async def test_decide_next_task_uses_configured_model(self):
        with patch(
            "src.orchestrator.planner.call_claude_for_text",
            new=AsyncMock(return_value="task"),
        ) as mock_call:
            await self.planner.decide_next_task(self.state)

        call_kwargs = mock_call.call_args
        model_arg = call_kwargs.kwargs.get("model") or call_kwargs.args[2]
        assert model_arg == "claude-test-model"

    def test_build_context_includes_state_info(self):
        self.state.iteration = 5
        self.state.completion_percent = 75.0
        self.state.test_pass_rate = 90.0
        self.state.lint_errors = 2
        self.state.type_errors = 1
        self.state.phase = PhaseType.BUILD

        context = self.planner._build_context(self.state)

        assert "5" in context  # iteration
        assert "75.0" in context  # completion
        assert "90.0" in context  # test pass rate
        assert "2" in context  # lint errors
        assert "1" in context  # type errors
        assert "build" in context.lower()  # phase

    def test_build_context_includes_spec(self):
        self.state.spec = "A" * 600  # 500자 초과
        context = self.planner._build_context(self.state)
        # 500자만 포함
        assert "A" * 500 in context

    def test_build_context_includes_pending_questions_count(self):
        self.state.pending_questions = [{"desc": "q1"}, {"desc": "q2"}]
        context = self.planner._build_context(self.state)
        assert "2" in context  # pending_questions count
