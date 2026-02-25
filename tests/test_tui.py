"""TUI 앱 헤드리스 테스트.

Textual의 run_test() 컨텍스트 매니저로 실제 터미널 없이 UI 컴포넌트를 검증한다.
asyncio_mode="auto"이므로 @pytest.mark.asyncio 불필요.
"""

from __future__ import annotations

import asyncio
import runpy
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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

    async def test_on_log_writes_to_richlog(
        self, tmp_path: Path, patched_orchestrator: MagicMock
    ) -> None:
        """_on_log() 직접 호출 시 RichLog에 메시지를 출력한다. (lines 373-378)"""
        event_bus = EventBus()

        class _App(App[None]):
            def on_mount(self) -> None:
                self.push_screen(DevScreen(tmp_path, "spec", event_bus))

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen: DevScreen = app.screen  # type: ignore[assignment]

            # 예외 없이 실행되어야 함 (error, warning, info, unknown 레벨 모두)
            screen._on_log({"level": "error", "message": "에러 메시지"})
            screen._on_log({"level": "warning", "message": "경고 메시지"})
            screen._on_log({"level": "info", "message": "정보 메시지"})
            screen._on_log({"level": "unknown", "message": "미지 레벨"})
            await pilot.pause()

    async def test_handle_event_progress_branch(
        self, tmp_path: Path, patched_orchestrator: MagicMock
    ) -> None:
        """PROGRESS 이벤트 → _on_progress() 호출. (lines 365-366, 381-382)"""
        event_bus = EventBus()

        class _App(App[None]):
            def on_mount(self) -> None:
                self.push_screen(DevScreen(tmp_path, "spec", event_bus))

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen: DevScreen = app.screen  # type: ignore[assignment]

            screen._handle_event(
                Event(
                    type=EventType.PROGRESS,
                    data={
                        "iteration": 3,
                        "phase": "coding",
                        "completion_percent": 50.0,
                        "test_pass_rate": 70.0,
                        "lint_errors": 0,
                        "type_errors": 0,
                        "build_success": True,
                    },
                )
            )
            await pilot.pause()

            assert "50.0%" in str(screen.query_one("#label-completion", Label).content)

    async def test_handle_event_question_branch(
        self, tmp_path: Path, patched_orchestrator: MagicMock
    ) -> None:
        """QUESTION 이벤트 → _on_question() 호출. (lines 367-368)"""
        event_bus = EventBus()

        class _App(App[None]):
            def on_mount(self) -> None:
                self.push_screen(DevScreen(tmp_path, "spec", event_bus))

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen: DevScreen = app.screen  # type: ignore[assignment]

            screen._handle_event(
                Event(
                    type=EventType.QUESTION,
                    data={"issue": {"description": "handle_event QUESTION 분기"}},
                )
            )
            await pilot.pause()

            assert screen._waiting_for_answer

    async def test_handle_event_completed_branch(
        self, tmp_path: Path, patched_orchestrator: MagicMock
    ) -> None:
        """COMPLETED 이벤트 → _on_completed() 호출. (lines 369-370)"""
        event_bus = EventBus()

        class _App(App[None]):
            def on_mount(self) -> None:
                self.push_screen(DevScreen(tmp_path, "spec", event_bus))

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen: DevScreen = app.screen  # type: ignore[assignment]

            screen._handle_event(
                Event(
                    type=EventType.COMPLETED,
                    data={
                        "is_complete": True,
                        "iteration": 5,
                        "test_pass_rate": 100.0,
                        "lint_errors": 0,
                        "type_errors": 0,
                        "build_success": True,
                        "pending_questions": [],
                    },
                )
            )
            await pilot.pause()

            assert len(screen.query(".completed-box")) == 1

    async def test_listen_events_dispatches_event(
        self, tmp_path: Path, patched_orchestrator: MagicMock
    ) -> None:
        """_listen_events 워커가 이벤트 수신 시 _handle_event를 호출한다. (line 357)"""
        event_bus = EventBus()

        class _App(App[None]):
            def on_mount(self) -> None:
                self.push_screen(DevScreen(tmp_path, "spec", event_bus))

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen: DevScreen = app.screen  # type: ignore[assignment]

            with patch.object(screen, "_handle_event") as mock_handle:
                await event_bus.publish(
                    Event(
                        type=EventType.LOG,
                        data={"level": "info", "message": "이벤트 루프 테스트"},
                    )
                )
                await pilot.pause()

                mock_handle.assert_called_once()

    async def test_run_orchestrator_awaits_run(
        self, tmp_path: Path, patched_orchestrator: MagicMock
    ) -> None:
        """_run_orchestrator가 AutonomousOrchestrator.run()을 호출한다. (line 349)"""
        event_bus = EventBus()

        class _App(App[None]):
            def on_mount(self) -> None:
                self.push_screen(DevScreen(tmp_path, "spec", event_bus))

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen: DevScreen = app.screen  # type: ignore[assignment]

            mock_run = AsyncMock()
            patched_orchestrator.return_value.run = mock_run
            await screen._run_orchestrator()

        mock_run.assert_awaited_once()

    async def test_on_input_submitted_triggers_send_answer(
        self, tmp_path: Path, patched_orchestrator: MagicMock
    ) -> None:
        """question-input Enter → action_send_answer() 호출. (lines 443-444)"""
        event_bus = EventBus()

        class _App(App[None]):
            def on_mount(self) -> None:
                self.push_screen(DevScreen(tmp_path, "spec", event_bus))

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen: DevScreen = app.screen  # type: ignore[assignment]

            screen._on_question({"issue": {"description": "test"}})
            await pilot.pause()

            q_input = screen.query_one("#question-input", Input)
            q_input.value = "답변 내용"
            mock_event = MagicMock()
            mock_event.input.id = "question-input"
            screen.on_input_submitted(mock_event)
            await pilot.pause()

            assert q_input.value == ""
            assert not screen._waiting_for_answer

    async def test_on_button_pressed_triggers_send_answer(
        self, tmp_path: Path, patched_orchestrator: MagicMock
    ) -> None:
        """question-send-btn 클릭 → action_send_answer() 호출. (lines 447-448)"""
        event_bus = EventBus()

        class _App(App[None]):
            def on_mount(self) -> None:
                self.push_screen(DevScreen(tmp_path, "spec", event_bus))

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen: DevScreen = app.screen  # type: ignore[assignment]

            screen._on_question({"issue": {"description": "test"}})
            await pilot.pause()

            q_input = screen.query_one("#question-input", Input)
            q_input.value = "버튼 답변"
            mock_event = MagicMock()
            mock_event.button.id = "question-send-btn"
            screen.on_button_pressed(mock_event)
            await pilot.pause()

            assert q_input.value == ""

    async def test_dev_action_quit_app_calls_exit(
        self, tmp_path: Path, patched_orchestrator: MagicMock
    ) -> None:
        """DevScreen action_quit_app → app.exit() 호출. (line 463)"""
        event_bus = EventBus()

        class _App(App[None]):
            def on_mount(self) -> None:
                self.push_screen(DevScreen(tmp_path, "spec", event_bus))

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen: DevScreen = app.screen  # type: ignore[assignment]

            with patch.object(app, "exit") as mock_exit:
                screen.action_quit_app()
            mock_exit.assert_called_once()


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

    async def test_on_input_submitted_calls_action_send(
        self, tmp_path: Path, patched_spec_builder: MagicMock
    ) -> None:
        """on_input_submitted → action_send() 호출. (line 147)"""
        event_bus = EventBus()

        class _App(App[None]):
            def on_mount(self) -> None:
                self.push_screen(SpecScreen(tmp_path, event_bus))

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen: SpecScreen = app.screen  # type: ignore[assignment]

            user_input = screen.query_one("#user-input", Input)
            user_input.value = "테스트 입력"
            screen.on_input_submitted(MagicMock())
            await pilot.pause()

            assert len(screen.query(".msg-user")) == 1
            assert user_input.value == ""

    async def test_on_button_pressed_calls_action_send(
        self, tmp_path: Path, patched_spec_builder: MagicMock
    ) -> None:
        """on_button_pressed → send-btn이면 action_send() 호출. (lines 150-151)"""
        event_bus = EventBus()

        class _App(App[None]):
            def on_mount(self) -> None:
                self.push_screen(SpecScreen(tmp_path, event_bus))

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen: SpecScreen = app.screen  # type: ignore[assignment]

            user_input = screen.query_one("#user-input", Input)
            user_input.value = "버튼 클릭 테스트"
            mock_event = MagicMock()
            mock_event.button.id = "send-btn"
            screen.on_button_pressed(mock_event)
            await pilot.pause()

            assert len(screen.query(".msg-user")) == 1

    async def test_action_quit_app_calls_exit(
        self, tmp_path: Path, patched_spec_builder: MagicMock
    ) -> None:
        """action_quit_app → app.exit() 호출. (line 165)"""
        event_bus = EventBus()

        class _App(App[None]):
            def on_mount(self) -> None:
                self.push_screen(SpecScreen(tmp_path, event_bus))

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen: SpecScreen = app.screen  # type: ignore[assignment]

            with patch.object(app, "exit") as mock_exit:
                screen.action_quit_app()
            mock_exit.assert_called_once()

    async def test_run_spec_builder_pushes_dev_screen(
        self, tmp_path: Path, patched_spec_builder: MagicMock
    ) -> None:
        """SpecBuilder.build() 완료 시 DevScreen으로 전환한다. (line 122)"""
        event_bus = EventBus()

        async def fast_build(path: Path) -> str:
            return "스펙 내용"

        class _App(App[None]):
            def on_mount(self) -> None:
                self.push_screen(SpecScreen(tmp_path, event_bus))

        with patch("src.ui.tui.app.AutonomousOrchestrator") as mock_orch:
            mock_orch.return_value.run = _hang
            app = _App()
            async with app.run_test() as pilot:
                await pilot.pause()
                screen: SpecScreen = app.screen  # type: ignore[assignment]
                screen._spec_builder.build = fast_build  # type: ignore[assignment]

                await screen._run_spec_builder()
                await pilot.pause()

                assert isinstance(app.screen, DevScreen)

    async def test_run_spec_builder_handles_exception(
        self, tmp_path: Path, patched_spec_builder: MagicMock
    ) -> None:
        """SpecBuilder.build() 예외 발생 시 에러 메시지를 표시한다. (line 124)"""
        event_bus = EventBus()

        async def failing_build(path: Path) -> str:
            raise ValueError("빌드 실패")

        class _App(App[None]):
            def on_mount(self) -> None:
                self.push_screen(SpecScreen(tmp_path, event_bus))

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen: SpecScreen = app.screen  # type: ignore[assignment]
            screen._spec_builder.build = failing_build  # type: ignore[assignment]

            await screen._run_spec_builder()
            await pilot.pause()

            messages = screen.query(".msg-assistant")
            assert any("오류" in str(m.content) for m in messages)

    async def test_listen_spec_events_adds_spec_message(
        self, tmp_path: Path, patched_spec_builder: MagicMock
    ) -> None:
        """SPEC_MESSAGE 이벤트 수신 시 채팅 영역에 메시지를 추가한다. (lines 132-135)"""
        event_bus = EventBus()

        class _App(App[None]):
            def on_mount(self) -> None:
                self.push_screen(SpecScreen(tmp_path, event_bus))

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen: SpecScreen = app.screen  # type: ignore[assignment]

            await event_bus.publish(
                Event(
                    type=EventType.SPEC_MESSAGE,
                    data={"role": "assistant", "content": "스펙 메시지 테스트"},
                )
            )
            await pilot.pause()

            assert len(screen.query(".msg-assistant")) >= 1


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


# ─── TUI __main__ ────────────────────────────────────────────────────


class TestTuiMain:
    """src/ui/tui/__main__.py if __name__ == '__main__' 블록 테스트."""

    def test_main_block_calls_run_tui(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """if __name__ == '__main__' 블록이 run_tui를 호출한다. (__main__.py:13-16)"""
        monkeypatch.setattr(sys, "argv", ["src.ui.tui"])
        with patch("src.ui.tui.app.run_tui") as mock_run:
            runpy.run_module("src.ui.tui", run_name="__main__", alter_sys=False)
        mock_run.assert_called_once_with(project_path=None, spec_file=None)

    def test_main_block_passes_argv(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """sys.argv에 project_path가 있으면 run_tui에 그대로 전달된다."""
        monkeypatch.setattr(sys, "argv", ["src.ui.tui", str(tmp_path)])
        with patch("src.ui.tui.app.run_tui") as mock_run:
            runpy.run_module("src.ui.tui", run_name="__main__", alter_sys=False)
        mock_run.assert_called_once_with(project_path=str(tmp_path), spec_file=None)
