"""AutonomousOrchestrator 테스트."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.orchestrator.issue_classifier import IssueLevel
from src.orchestrator.main import AutonomousOrchestrator, TokenLimitError


class TestAutonomousOrchestrator:
    def setup_method(self):
        # 외부 의존성 패치 후 생성
        with (
            patch("src.orchestrator.main.AgentExecutor"),
            patch("src.orchestrator.main.Verifier"),
        ):
            self.orch = AutonomousOrchestrator("/tmp/test_project", "테스트 스펙")

        # 모든 컴포넌트를 AsyncMock으로 교체
        self.orch.executor = AsyncMock()
        self.orch.verifier = AsyncMock()
        self.orch.planner = AsyncMock()
        self.orch.classifier = AsyncMock()
        self.orch.token_manager = AsyncMock()
        self.orch.state.save = MagicMock()

    # ─── _is_complete() ───────────────────────────────────────────────

    def test_is_complete_returns_true_when_all_criteria_met(self):
        self.orch.state.test_pass_rate = 100.0
        self.orch.state.lint_errors = 0
        self.orch.state.type_errors = 0
        self.orch.state.build_success = True

        assert self.orch._is_complete() is True

    def test_is_complete_returns_false_when_test_rate_below_100(self):
        self.orch.state.test_pass_rate = 99.9
        self.orch.state.lint_errors = 0
        self.orch.state.type_errors = 0
        self.orch.state.build_success = True

        assert self.orch._is_complete() is False

    def test_is_complete_returns_false_when_lint_errors(self):
        self.orch.state.test_pass_rate = 100.0
        self.orch.state.lint_errors = 1
        self.orch.state.type_errors = 0
        self.orch.state.build_success = True

        assert self.orch._is_complete() is False

    def test_is_complete_returns_false_when_build_failed(self):
        self.orch.state.test_pass_rate = 100.0
        self.orch.state.lint_errors = 0
        self.orch.state.type_errors = 0
        self.orch.state.build_success = False

        assert self.orch._is_complete() is False

    # ─── _update_state() ──────────────────────────────────────────────

    def test_update_state_perfect_score(self):
        verification = {
            "tests_total": 10,
            "tests_passed": 10,
            "lint_errors": 0,
            "type_errors": 0,
            "build_success": True,
        }
        self.orch._update_state(verification)

        assert self.orch.state.test_pass_rate == 100.0
        assert self.orch.state.lint_errors == 0
        assert self.orch.state.build_success is True
        assert self.orch.state.completion_percent == 100.0

    def test_update_state_partial_score(self):
        verification = {
            "tests_total": 10,
            "tests_passed": 5,
            "lint_errors": 3,
            "type_errors": 1,
            "build_success": True,
        }
        self.orch._update_state(verification)

        assert self.orch.state.test_pass_rate == 50.0
        assert self.orch.state.lint_errors == 3
        assert self.orch.state.type_errors == 1
        # 완성도: 테스트 40*0.5 + 린트 0 + 타입 0 + 빌드 30 = 50
        assert self.orch.state.completion_percent == pytest.approx(50.0)

    def test_update_state_with_zero_tests(self):
        verification = {
            "tests_total": 0,
            "tests_passed": 0,
            "lint_errors": 0,
            "type_errors": 0,
            "build_success": True,
        }
        self.orch._update_state(verification)

        assert self.orch.state.test_pass_rate == 0
        # 빌드 성공 + 린트 0 + 타입 0 = 30+15+15 = 60
        assert self.orch.state.completion_percent == pytest.approx(60.0)

    def test_update_state_saves_to_file(self):
        self.orch._update_state({"tests_total": 0, "tests_passed": 0})
        self.orch.state.save.assert_called_once()

    # ─── _handle_issues() ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_handle_issues_non_critical_adds_to_pending(self):
        issue = {"description": "버튼 색상", "level": IssueLevel.NON_CRITICAL}
        await self.orch._handle_issues([issue])

        assert len(self.orch.state.pending_questions) == 1
        assert self.orch.state.pending_questions[0] == issue

    @pytest.mark.asyncio
    async def test_handle_issues_critical_asks_human(self):
        issue = {"description": "스펙 모호", "level": IssueLevel.CRITICAL}
        with patch.object(self.orch, "_ask_human", new=AsyncMock(return_value=None)):
            await self.orch._handle_issues([issue])

        # 비크리티컬 목록에 들어가지 않음
        assert len(self.orch.state.pending_questions) == 0

    @pytest.mark.asyncio
    async def test_handle_issues_critical_with_answer_executes(self):
        issue = {"description": "스펙 모호", "level": IssueLevel.CRITICAL}
        with patch.object(self.orch, "_ask_human", new=AsyncMock(return_value="소셜 로그인만")):
            await self.orch._handle_issues([issue])

        self.orch.executor.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_multiple_issues(self):
        issues = [
            {"description": "lint error", "level": IssueLevel.NON_CRITICAL},
            {"description": "ui color", "level": IssueLevel.NON_CRITICAL},
        ]
        await self.orch._handle_issues(issues)

        assert len(self.orch.state.pending_questions) == 2

    # ─── _ask_human() ─────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_ask_human_returns_answer(self):
        issue = {"description": "질문", "suggestion": "제안"}
        with patch("builtins.input", return_value="답변"):
            result = await self.orch._ask_human(issue)

        assert result == "답변"

    @pytest.mark.asyncio
    async def test_ask_human_returns_none_on_empty_input(self):
        issue = {"description": "질문"}
        with patch("builtins.input", return_value=""):
            result = await self.orch._ask_human(issue)

        assert result is None

    @pytest.mark.asyncio
    async def test_ask_human_handles_eof_error(self):
        issue = {"description": "질문", "level": IssueLevel.CRITICAL}
        with patch("builtins.input", side_effect=EOFError):
            result = await self.orch._ask_human(issue)

        assert result is None
        # EOFError 시 pending_questions에 추가
        assert len(self.orch.state.pending_questions) == 1

    # ─── _save_questions() ────────────────────────────────────────────

    def test_save_questions_writes_json_file(self, tmp_path):
        self.orch.project_path = tmp_path
        self.orch.state.pending_questions = [
            {"description": "색상 선택", "level": "non_critical"},
        ]
        self.orch._save_questions()

        output_file = tmp_path / "pending_questions.json"
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert len(data) == 1
        assert data[0]["description"] == "색상 선택"

    # ─── _self_heal() ─────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_self_heal_calls_executor(self):
        await self.orch._self_heal("RuntimeError: 뭔가 잘못됨")
        self.orch.executor.execute.assert_called_once()
        prompt = self.orch.executor.execute.call_args[0][0]
        assert "RuntimeError" in prompt

    # ─── _phase_setup() ───────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_phase_setup_calls_executor(self):
        from src.utils.state import PhaseType
        await self.orch._phase_setup()
        self.orch.executor.execute.assert_called_once()
        assert self.orch.state.phase == PhaseType.BUILD

    # ─── _phase_document() ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_phase_document_calls_executor(self):
        from src.utils.state import PhaseType
        await self.orch._phase_document()
        self.orch.executor.execute.assert_called_once()
        assert self.orch.state.phase == PhaseType.DOCUMENT

    # ─── _report_completion() ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_report_completion_prints_summary(self, capsys):
        self.orch.state.test_pass_rate = 100.0
        self.orch.state.lint_errors = 0
        self.orch.state.build_success = True
        with patch("builtins.input", side_effect=EOFError):
            await self.orch._report_completion()

        captured = capsys.readouterr()
        assert "100.0" in captured.out

    @pytest.mark.asyncio
    async def test_report_completion_pending_questions_eof(self, capsys):
        self.orch.state.pending_questions = [
            {"description": "색상 선택", "level": "non_critical"},
        ]
        self.orch.project_path = self.orch.project_path.__class__("/tmp")
        with (
            patch("builtins.input", side_effect=EOFError),
            patch.object(self.orch, "_save_questions"),
        ):
            await self.orch._report_completion()

        captured = capsys.readouterr()
        assert "색상 선택" in captured.out

    # ─── run() ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_run_completes_when_already_done(self):
        """처음부터 완성 조건을 충족하면 루프 없이 문서화 후 종료."""
        self.orch.state.test_pass_rate = 100.0
        self.orch.state.lint_errors = 0
        self.orch.state.type_errors = 0
        self.orch.state.build_success = True

        with (
            patch.object(self.orch, "_phase_setup", new=AsyncMock()),
            patch.object(self.orch, "_phase_document", new=AsyncMock()),
            patch("builtins.input", side_effect=EOFError),
        ):
            await self.orch.run()

        # 루프 없이 바로 완료 → planner.decide_next_task 호출 안 됨
        self.orch.planner.decide_next_task.assert_not_called()

    # ─── TokenLimitError ──────────────────────────────────────────────

    def test_token_limit_error_is_exception(self):
        with pytest.raises(TokenLimitError):
            raise TokenLimitError("한도 초과")
