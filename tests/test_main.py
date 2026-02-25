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

    @pytest.mark.asyncio
    async def test_run_one_iteration_then_complete(self):
        """루프가 1회 실행된 뒤 완성되면 종료한다. (lines 64-108)"""
        verification = {
            "tests_total": 10, "tests_passed": 10,
            "tests_failed": 0, "lint_errors": 0,
            "type_errors": 0, "build_success": True, "issues": [],
        }
        self.orch.planner.decide_next_task.return_value = "구현 작업"
        self.orch.verifier.verify_all.return_value = verification
        self.orch.classifier.classify.return_value = []

        # 첫 번째 while 체크: False(루프 진입), 두 번째: True(루프 탈출)
        # _report_completion도 mock → _is_complete 추가 호출 방지
        with (
            patch.object(self.orch, "_phase_setup", new=AsyncMock()),
            patch.object(self.orch, "_phase_document", new=AsyncMock()),
            patch.object(self.orch, "_report_completion", new=AsyncMock()),
            patch.object(self.orch, "_is_complete", side_effect=[False, True]),
        ):
            await self.orch.run()

        self.orch.planner.decide_next_task.assert_called_once()
        self.orch.executor.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_handles_token_limit_error(self):
        """TokenLimitError 발생 시 대기 후 루프를 계속한다."""
        self.orch.planner.decide_next_task.side_effect = [
            TokenLimitError("한도 초과"),
            "두 번째 작업",
        ]
        self.orch.verifier.verify_all.return_value = {
            "tests_total": 0, "tests_passed": 0, "tests_failed": 0,
            "lint_errors": 0, "type_errors": 0, "build_success": True, "issues": [],
        }
        self.orch.classifier.classify.return_value = []

        with (
            patch.object(self.orch, "_phase_setup", new=AsyncMock()),
            patch.object(self.orch, "_phase_document", new=AsyncMock()),
            patch.object(self.orch, "_report_completion", new=AsyncMock()),
            patch.object(self.orch, "_is_complete", side_effect=[False, False, True]),
        ):
            await self.orch.run()

        self.orch.token_manager.wait_for_reset.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_handles_unexpected_error(self):
        """예상치 못한 에러 발생 시 자가 복구를 시도한다."""
        self.orch.planner.decide_next_task.side_effect = [
            RuntimeError("예상치 못한 에러"),
            "두 번째 작업",
        ]
        self.orch.verifier.verify_all.return_value = {
            "tests_total": 0, "tests_passed": 0, "tests_failed": 0,
            "lint_errors": 0, "type_errors": 0, "build_success": True, "issues": [],
        }
        self.orch.classifier.classify.return_value = []

        mock_self_heal = AsyncMock()
        with (
            patch.object(self.orch, "_phase_setup", new=AsyncMock()),
            patch.object(self.orch, "_phase_document", new=AsyncMock()),
            patch.object(self.orch, "_report_completion", new=AsyncMock()),
            patch.object(self.orch, "_is_complete", side_effect=[False, False, True]),
            patch.object(self.orch, "_self_heal", new=mock_self_heal),
        ):
            await self.orch.run()

        mock_self_heal.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_breaks_on_max_iterations(self):
        """_max_iterations 초과 시 루프를 탈출하고 보고한다."""
        self.orch._max_iterations = 0
        with (
            patch.object(self.orch, "_phase_setup", new=AsyncMock()),
            patch.object(self.orch, "_phase_document", new=AsyncMock()),
            patch.object(self.orch, "_report_completion", new=AsyncMock()),
            patch.object(self.orch, "_is_complete", return_value=False),
        ):
            await self.orch.run()

        # 최대 반복 도달 시 바로 보고로 넘어감 (planner 호출 없음)
        self.orch.planner.decide_next_task.assert_not_called()

    # ─── _report_completion with user feedback ─────────────────────────

    @pytest.mark.asyncio
    async def test_report_completion_with_user_answer_reruns(self, capsys):
        """사용자가 피드백 답변을 주면 executor 실행 후 재시작한다. (lines 272-280)"""
        self.orch.state.pending_questions = [{"description": "색상 선택"}]
        # 재귀 run() 방지를 위해 _is_complete를 True로
        self.orch.state.test_pass_rate = 100.0
        self.orch.state.lint_errors = 0
        self.orch.state.type_errors = 0
        self.orch.state.build_success = True
        self.orch.project_path = self.orch.project_path.__class__("/tmp")

        mock_run = AsyncMock()
        with (
            patch("builtins.input", side_effect=["사용자 피드백", EOFError]),
            patch.object(self.orch, "run", new=mock_run),
        ):
            await self.orch._report_completion()

        self.orch.executor.execute.assert_called_once()
        mock_run.assert_called_once()

    # ─── main() 엔트리포인트 ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_main_no_args_exits(self):
        """인수 없이 실행하면 sys.exit(1). (lines 302-305)"""
        from src.orchestrator.main import main
        with (
            patch("sys.argv", ["main"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            await main()
        assert exc_info.value.code == 1

    @pytest.mark.asyncio
    async def test_main_file_not_found_exits(self, tmp_path):
        """존재하지 않는 파일이면 sys.exit(1). (lines 307-310)"""
        from src.orchestrator.main import main
        with (
            patch("sys.argv", ["main", str(tmp_path / "nonexistent.md")]),
            pytest.raises(SystemExit) as exc_info,
        ):
            await main()
        assert exc_info.value.code == 1

    @pytest.mark.asyncio
    async def test_main_runs_orchestrator(self, tmp_path):
        """유효한 파일이면 Orchestrator를 생성하고 실행한다. (lines 312-319)"""
        from src.orchestrator.main import main
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("테스트 스펙")

        with (
            patch("sys.argv", ["main", str(spec_file)]),
            patch("src.orchestrator.main.AgentExecutor"),
            patch("src.orchestrator.main.Verifier"),
            patch.object(
                AutonomousOrchestrator, "run", new=AsyncMock()
            ) as mock_run,
        ):
            await main()

        mock_run.assert_called_once()

    # ─── TokenLimitError ──────────────────────────────────────────────

    def test_token_limit_error_is_exception(self):
        with pytest.raises(TokenLimitError):
            raise TokenLimitError("한도 초과")

    # ─── EventBus 연동 ────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_emit_publishes_event_when_bus_set(self):
        """_emit은 event_bus가 있을 때 이벤트를 발행한다."""
        from src.utils.events import Event, EventBus, EventType

        bus = EventBus()
        q = bus.subscribe()
        with (
            patch("src.orchestrator.main.AgentExecutor"),
            patch("src.orchestrator.main.Verifier"),
        ):
            orch = AutonomousOrchestrator("/tmp", "spec", event_bus=bus)

        await orch._emit(EventType.LOG, {"message": "test"})
        event: Event = await q.get()
        assert event.type == EventType.LOG
        assert event.data["message"] == "test"

    @pytest.mark.asyncio
    async def test_emit_noop_when_bus_is_none(self):
        """_emit은 event_bus가 None이면 아무것도 하지 않는다."""
        from src.utils.events import EventType

        # 에러 없이 완료되어야 함
        await self.orch._emit(EventType.LOG, {"message": "noop"})

    @pytest.mark.asyncio
    async def test_ask_human_uses_event_bus(self):
        """event_bus가 있으면 QUESTION 이벤트를 발행하고 답변을 기다린다."""
        from src.utils.events import EventBus, EventType

        bus = EventBus()
        q = bus.subscribe()
        with (
            patch("src.orchestrator.main.AgentExecutor"),
            patch("src.orchestrator.main.Verifier"),
        ):
            orch = AutonomousOrchestrator("/tmp", "spec", event_bus=bus)
        orch.executor = AsyncMock()

        issue = {"description": "스펙 모호", "level": "critical"}
        # 사용자 답변을 미리 큐에 넣기
        await bus.put_answer("이메일 로그인 사용")
        answer = await orch._ask_human(issue)

        # QUESTION 이벤트 발행 확인
        event = await q.get()
        assert event.type == EventType.QUESTION
        assert event.data["issue"] == issue
        assert answer == "이메일 로그인 사용"

    @pytest.mark.asyncio
    async def test_ask_human_returns_none_for_empty_answer(self):
        """빈 답변이면 None을 반환한다."""
        from src.utils.events import EventBus

        bus = EventBus()
        bus.subscribe()
        with (
            patch("src.orchestrator.main.AgentExecutor"),
            patch("src.orchestrator.main.Verifier"),
        ):
            orch = AutonomousOrchestrator("/tmp", "spec", event_bus=bus)

        issue = {"description": "모호한 요구사항"}
        await bus.put_answer("")  # 빈 답변
        answer = await orch._ask_human(issue)
        assert answer is None

    @pytest.mark.asyncio
    async def test_report_completion_emits_completed_event(self):
        """_report_completion은 COMPLETED 이벤트를 발행한다."""
        from src.utils.events import EventBus, EventType

        bus = EventBus()
        q = bus.subscribe()
        with (
            patch("src.orchestrator.main.AgentExecutor"),
            patch("src.orchestrator.main.Verifier"),
        ):
            orch = AutonomousOrchestrator("/tmp", "spec", event_bus=bus)
        orch.executor = AsyncMock()
        orch.state.test_pass_rate = 100.0
        orch.state.lint_errors = 0
        orch.state.type_errors = 0
        orch.state.build_success = True

        # 비크리티컬 질문 없으면 wait_for_answer 호출 안 함
        await orch._report_completion()
        event = await q.get()
        assert event.type == EventType.COMPLETED
        assert event.data["is_complete"] is True

    @pytest.mark.asyncio
    async def test_report_completion_waits_for_answer_via_event_bus(self):
        """pending_questions가 있고 event_bus 있으면 bus로 답변을 기다린다. (line 335)"""
        from src.utils.events import EventBus

        bus = EventBus()
        bus.subscribe()
        with (
            patch("src.orchestrator.main.AgentExecutor"),
            patch("src.orchestrator.main.Verifier"),
        ):
            orch = AutonomousOrchestrator("/tmp", "spec", event_bus=bus)
        orch.executor = AsyncMock()
        orch.state.pending_questions = [{"description": "색상 선택", "level": "non_critical"}]

        # "done" 답변 → 수정 루프 없이 종료
        await bus.put_answer("done")
        await orch._report_completion()  # 에러 없이 완료되어야 함
