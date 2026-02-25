"""TUI 앱 헤드리스 테스트.

Textual의 run_test() 컨텍스트 매니저로 실제 터미널 없이 UI 컴포넌트를 검증한다.
asyncio_mode="auto"이므로 @pytest.mark.asyncio 불필요.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Button, Input, Label, ProgressBar

from src.ui.tui.app import (
    AgentApp,
    ChatMessage,
    DevScreen,
    SpecScreen,
    StatusPanel,
    run_tui,
)
from src.utils.events import Event, EventBus, EventType


async def _hang(*_: object, **__: object) -> None:
    """절대 완료되지 않는 코루틴 — 워커 백그라운드 실행 방지용."""
    await asyncio.sleep(9_999)


# ─── ChatMessage ──────────────────────────────────────────────────────


class TestChatMessage:
    """ChatMessage 위젯 CSS 클래스 테스트."""

    def test_assistant_adds_msg_assistant_class(self) -> None:
        """role='assistant' → msg-assistant 클래스 추가."""
        msg = ChatMessage("assistant", "안녕하세요")
        assert msg.has_class("msg-assistant")
        assert not msg.has_class("msg-user")

    def test_user_adds_msg_user_class(self) -> None:
        """role='user' → msg-user 클래스 추가."""
        msg = ChatMessage("user", "반갑습니다")
        assert msg.has_class("msg-user")
        assert not msg.has_class("msg-assistant")


# ─── StatusPanel ─────────────────────────────────────────────────────


class _StatusApp(App[None]):
    """StatusPanel 단독 테스트 전용 최소 앱."""

    def compose(self) -> ComposeResult:
        yield StatusPanel(id="panel")


class TestStatusPanel:
    """StatusPanel.update_progress() 테스트."""

    async def test_labels_updated_correctly(self) -> None:
        """update_progress() 호출 시 각 레이블이 올바른 값으로 업데이트됨."""
        app = _StatusApp()
        async with app.run_test() as pilot:
            panel = app.query_one("#panel", StatusPanel)
            panel.update_progress(
                {
                    "iteration": 5,
                    "phase": "coding",
                    "completion_percent": 75.0,
                    "test_pass_rate": 60.0,
                    "lint_errors": 2,
                    "type_errors": 1,
                    "build_success": True,
                }
            )
            await pilot.pause()

            assert "5회" in str(app.query_one("#stat-iteration", Label).content)
            assert "coding" in str(app.query_one("#stat-phase", Label).content)
            assert "75.0%" in str(app.query_one("#label-completion", Label).content)
            assert "60.0%" in str(app.query_one("#label-test", Label).content)
            assert "린트 에러: 2건" in str(app.query_one("#stat-lint", Label).content)
            assert "타입 에러: 1건" in str(app.query_one("#stat-type", Label).content)
            assert "빌드: 성공" in str(app.query_one("#stat-build", Label).content)

    async def test_build_failure_shows_fail_label(self) -> None:
        """build_success=False → '빌드: 실패' 레이블."""
        app = _StatusApp()
        async with app.run_test() as pilot:
            panel = app.query_one("#panel", StatusPanel)
            panel.update_progress(
                {
                    "iteration": 1,
                    "phase": "init",
                    "completion_percent": 0.0,
                    "test_pass_rate": 0.0,
                    "lint_errors": 0,
                    "type_errors": 0,
                    "build_success": False,
                }
            )
            await pilot.pause()
            assert "빌드: 실패" in str(app.query_one("#stat-build", Label).content)

    async def test_progress_bar_values(self) -> None:
        """ProgressBar.progress 값이 completion_percent / test_pass_rate와 일치."""
        app = _StatusApp()
        async with app.run_test() as pilot:
            panel = app.query_one("#panel", StatusPanel)
            panel.update_progress(
                {
                    "iteration": 1,
                    "phase": "test",
                    "completion_percent": 80.0,
                    "test_pass_rate": 50.0,
                    "lint_errors": 0,
                    "type_errors": 0,
                    "build_success": True,
                }
            )
            await pilot.pause()
            assert app.query_one("#bar-completion", ProgressBar).progress == 80.0
            assert app.query_one("#bar-test", ProgressBar).progress == 50.0


# ─── AgentApp ────────────────────────────────────────────────────────


class TestAgentApp:
    """AgentApp.on_mount() 화면 전환 테스트."""

    async def test_no_spec_path_shows_spec_screen(self, tmp_path: Path) -> None:
        """spec_path=None → SpecScreen이 활성 화면으로 표시됨."""
        with patch("src.ui.tui.app.SpecBuilder") as mock_cls:
            instance = MagicMock()
            instance.build = _hang
            mock_cls.return_value = instance

            app = AgentApp(project_path=tmp_path)
            async with app.run_test() as pilot:
                await pilot.pause()
                assert isinstance(app.screen, SpecScreen)

    async def test_with_spec_file_shows_dev_screen(self, tmp_path: Path) -> None:
        """spec_path가 실제 파일 → DevScreen이 활성 화면으로 표시됨."""
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# 테스트 스펙")

        with patch("src.ui.tui.app.AutonomousOrchestrator") as mock_cls:
            mock_cls.return_value.run = _hang

            app = AgentApp(project_path=tmp_path, spec_path=spec_file)
            async with app.run_test() as pilot:
                await pilot.pause()
                assert isinstance(app.screen, DevScreen)


# ─── DevScreen ───────────────────────────────────────────────────────


class TestDevScreen:
    """DevScreen 이벤트 처리 및 입력 제어 테스트."""

    @pytest.fixture
    def patched_orchestrator(self):
        """AutonomousOrchestrator.run을 영원히 대기하는 mock으로 교체."""
        with patch("src.ui.tui.app.AutonomousOrchestrator") as cls:
            cls.return_value.run = _hang
            yield cls

    async def test_on_question_enables_input(
        self, tmp_path: Path, patched_orchestrator: MagicMock
    ) -> None:
        """QUESTION 이벤트 → question-input/button 활성화 + _waiting_for_answer=True."""
        event_bus = EventBus()

        class _App(App[None]):
            def on_mount(self) -> None:
                self.push_screen(DevScreen(tmp_path, "spec", event_bus))

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen: DevScreen = app.screen  # type: ignore[assignment]

            screen._on_question(
                {"issue": {"description": "모호한 스펙", "suggestion": "명확화 필요"}}
            )
            await pilot.pause()

            assert not screen.query_one("#question-input", Input).disabled
            assert not screen.query_one("#question-send-btn", Button).disabled
            assert screen._waiting_for_answer

    async def test_on_completed_no_pending_keeps_input_disabled(
        self, tmp_path: Path, patched_orchestrator: MagicMock
    ) -> None:
        """pending_questions=[] → completed-box 마운트, 입력 비활성 유지."""
        event_bus = EventBus()

        class _App(App[None]):
            def on_mount(self) -> None:
                self.push_screen(DevScreen(tmp_path, "spec", event_bus))

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen: DevScreen = app.screen  # type: ignore[assignment]

            screen._on_completed(
                {
                    "is_complete": True,
                    "iteration": 10,
                    "test_pass_rate": 100.0,
                    "lint_errors": 0,
                    "type_errors": 0,
                    "build_success": True,
                    "pending_questions": [],
                }
            )
            await pilot.pause()

            assert len(screen.query(".completed-box")) == 1
            assert screen.query_one("#question-input", Input).disabled

    async def test_on_completed_with_pending_enables_input(
        self, tmp_path: Path, patched_orchestrator: MagicMock
    ) -> None:
        """pending_questions가 있으면 입력 활성화."""
        event_bus = EventBus()

        class _App(App[None]):
            def on_mount(self) -> None:
                self.push_screen(DevScreen(tmp_path, "spec", event_bus))

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen: DevScreen = app.screen  # type: ignore[assignment]

            screen._on_completed(
                {
                    "is_complete": False,
                    "iteration": 5,
                    "test_pass_rate": 80.0,
                    "lint_errors": 1,
                    "type_errors": 0,
                    "build_success": True,
                    "pending_questions": [{"description": "색상 선택?"}],
                }
            )
            await pilot.pause()

            assert not screen.query_one("#question-input", Input).disabled
            assert not screen.query_one("#question-send-btn", Button).disabled
            assert screen._waiting_for_answer

    async def test_action_send_answer_when_waiting(
        self, tmp_path: Path, patched_orchestrator: MagicMock
    ) -> None:
        """_waiting_for_answer=True → 답변 전송, 입력 초기화 및 비활성화."""
        event_bus = EventBus()

        class _App(App[None]):
            def on_mount(self) -> None:
                self.push_screen(DevScreen(tmp_path, "spec", event_bus))

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen: DevScreen = app.screen  # type: ignore[assignment]

            # 질문 이벤트로 waiting 상태 진입
            screen._on_question({"issue": {"description": "이슈"}})
            await pilot.pause()

            q_input = screen.query_one("#question-input", Input)
            q_input.value = "사용자 답변"
            screen.action_send_answer()
            await pilot.pause()

            assert q_input.value == ""
            assert q_input.disabled
            assert not screen._waiting_for_answer

    async def test_action_send_answer_when_not_waiting_does_nothing(
        self, tmp_path: Path, patched_orchestrator: MagicMock
    ) -> None:
        """_waiting_for_answer=False → 아무것도 하지 않음, 입력값 유지."""
        event_bus = EventBus()

        class _App(App[None]):
            def on_mount(self) -> None:
                self.push_screen(DevScreen(tmp_path, "spec", event_bus))

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen: DevScreen = app.screen  # type: ignore[assignment]
            assert not screen._waiting_for_answer

            q_input = screen.query_one("#question-input", Input)
            q_input.value = "무시되어야 할 텍스트"
            screen.action_send_answer()
            await pilot.pause()

            assert q_input.value == "무시되어야 할 텍스트"

    async def test_handle_event_dispatches_log(
        self, tmp_path: Path, patched_orchestrator: MagicMock
    ) -> None:
        """LOG 이벤트 → _on_log() 호출, 예외 없이 처리됨."""
        event_bus = EventBus()

        class _App(App[None]):
            def on_mount(self) -> None:
                self.push_screen(DevScreen(tmp_path, "spec", event_bus))

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen: DevScreen = app.screen  # type: ignore[assignment]

            with patch.object(screen, "_on_log") as mock_on_log:
                event = Event(type=EventType.LOG, data={"level": "info", "message": "테스트 로그"})
                screen._handle_event(event)
                mock_on_log.assert_called_once_with({"level": "info", "message": "테스트 로그"})


# ─── SpecScreen ──────────────────────────────────────────────────────


class TestSpecScreen:
    """SpecScreen 입력 처리 테스트."""

    @pytest.fixture
    def patched_spec_builder(self):
        """SpecBuilder.build를 영원히 대기하는 mock으로 교체."""
        with patch("src.ui.tui.app.SpecBuilder") as cls:
            instance = MagicMock()
            instance.build = _hang
            cls.return_value = instance
            yield cls

    async def test_action_send_ignores_empty_input(
        self, tmp_path: Path, patched_spec_builder: MagicMock
    ) -> None:
        """빈 입력 → 채팅 메시지 추가 없음."""
        event_bus = EventBus()

        class _App(App[None]):
            def on_mount(self) -> None:
                self.push_screen(SpecScreen(tmp_path, event_bus))

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen: SpecScreen = app.screen  # type: ignore[assignment]

            user_input = screen.query_one("#user-input", Input)
            user_input.value = "   "
            screen.action_send()
            await pilot.pause()

            assert len(screen.query(".msg-user")) == 0

    async def test_action_send_adds_message_and_clears_input(
        self, tmp_path: Path, patched_spec_builder: MagicMock
    ) -> None:
        """유효한 입력 → msg-user 추가 + 입력창 초기화."""
        event_bus = EventBus()

        class _App(App[None]):
            def on_mount(self) -> None:
                self.push_screen(SpecScreen(tmp_path, event_bus))

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen: SpecScreen = app.screen  # type: ignore[assignment]

            user_input = screen.query_one("#user-input", Input)
            user_input.value = "로그인 기능 필요"
            screen.action_send()
            await pilot.pause()

            assert len(screen.query(".msg-user")) == 1
            assert user_input.value == ""


# ─── run_tui ─────────────────────────────────────────────────────────


class TestRunTui:
    """run_tui() 진입점 테스트."""

    def test_creates_agent_app_and_calls_run(self, tmp_path: Path) -> None:
        """run_tui() → AgentApp 생성 후 run() 호출."""
        with patch("src.ui.tui.app.AgentApp") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            run_tui(project_path=str(tmp_path))
            mock_instance.run.assert_called_once()

    def test_uses_cwd_when_no_path_given(self) -> None:
        """project_path=None → Path.cwd() 사용."""
        with patch("src.ui.tui.app.AgentApp") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            run_tui()
            assert mock_cls.call_args.kwargs["project_path"] == Path.cwd()
