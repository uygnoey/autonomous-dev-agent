"""Textual 기반 TUI 앱.

두 개의 화면으로 구성된다:
1. SpecScreen  - 스펙 확정 대화 (개발 시작 전)
2. DevScreen   - 개발 진행 대시보드 + 크리티컬 이슈 채팅

실행:
    python -m src.ui.tui <project_path>
    python -m src.ui.tui  (현재 디렉토리)
"""

import asyncio
from pathlib import Path
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    RichLog,
    Static,
)

from src.orchestrator.main import AutonomousOrchestrator
from src.orchestrator.spec_builder import SpecBuilder
from src.utils.events import Event, EventBus, EventType

# ─── 스펙 대화 화면 ──────────────────────────────────────────────────

class ChatMessage(Static):
    """채팅 메시지 위젯."""

    def __init__(self, role: str, content: str) -> None:
        prefix = "🤖 Claude" if role == "assistant" else "👤 나"
        super().__init__(f"[bold]{prefix}[/bold]\n{content}\n")
        if role == "assistant":
            self.add_class("msg-assistant")
        else:
            self.add_class("msg-user")


class SpecScreen(Screen):
    """스펙 확정 대화 화면.

    Claude와 대화하며 프로젝트 스펙을 확정한다.
    스펙이 확정되면 DevScreen으로 전환된다.
    """

    CSS = """
    SpecScreen {
        background: $surface;
    }
    #chat-area {
        height: 1fr;
        border: solid $primary;
        margin: 1 2;
        padding: 1;
    }
    .msg-assistant {
        background: $panel;
        margin: 0 0 1 0;
        padding: 1;
        border-left: thick $primary;
    }
    .msg-user {
        background: $boost;
        margin: 0 0 1 0;
        padding: 1;
        border-left: thick $accent;
        text-align: right;
    }
    #input-row {
        height: 5;
        margin: 0 2 1 2;
    }
    #user-input {
        width: 1fr;
    }
    #send-btn {
        width: 12;
        margin-left: 1;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [  # type: ignore[assignment]
        Binding("ctrl+s", "send", "전송", show=True),
        Binding("escape", "quit_app", "종료"),
    ]

    def __init__(self, project_path: Path, event_bus: EventBus) -> None:
        super().__init__()
        self._project_path = project_path
        self._event_bus = event_bus
        self._spec_builder = SpecBuilder(event_bus)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Label(" 💬 스펙 확정 대화 — Claude와 대화하여 프로젝트를 정의하세요", id="title")
        yield ScrollableContainer(id="chat-area")
        with Horizontal(id="input-row"):
            yield Input(placeholder="메시지 입력... (Ctrl+S 또는 Enter로 전송)", id="user-input")
            yield Button("전송", id="send-btn", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._listen_spec_events(), exclusive=False)
        self.run_worker(self._run_spec_builder(), exclusive=False)
        self.query_one("#user-input", Input).focus()

    async def _run_spec_builder(self) -> None:
        """백그라운드에서 스펙 빌더를 실행한다."""
        try:
            spec = await self._spec_builder.build(self._project_path)
            # 스펙 확정 → DevScreen으로 전환
            self.app.push_screen(DevScreen(self._project_path, spec, self._event_bus))
        except Exception as e:
            self._add_message("assistant", f"⚠️ 오류가 발생했습니다: {e}")

    async def _listen_spec_events(self) -> None:
        """이벤트 버스에서 스펙 메시지를 받아 화면에 표시한다."""
        q = self._event_bus.subscribe()
        try:
            while True:
                event: Event = await q.get()
                if event.type == EventType.SPEC_MESSAGE:
                    role = event.data.get("role", "assistant")
                    content = event.data.get("content", "")
                    self._add_message(role, content)
        except asyncio.CancelledError:
            pass

    def _add_message(self, role: str, content: str) -> None:
        """채팅 영역에 메시지를 추가한다."""
        chat = self.query_one("#chat-area", ScrollableContainer)
        msg = ChatMessage(role, content)
        chat.mount(msg)
        chat.scroll_end(animate=False)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_send()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send-btn":
            self.action_send()

    def action_send(self) -> None:
        """사용자 입력을 이벤트 버스로 전달한다."""
        user_input = self.query_one("#user-input", Input)
        text = user_input.value.strip()
        if not text:
            return

        self._add_message("user", text)
        user_input.value = ""
        self.run_worker(self._event_bus.put_answer(text), exclusive=False)

    def action_quit_app(self) -> None:
        self.app.exit()


# ─── 개발 대시보드 화면 ─────────────────────────────────────────────

class StatusPanel(Static):
    """개발 진행 상황 패널."""

    DEFAULT_CSS = """
    StatusPanel {
        height: 14;
        border: solid $primary;
        margin: 1;
        padding: 1 2;
    }
    .stat-row {
        height: 1;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("📊 진행 상황", id="panel-title")
        yield Label("", id="stat-iteration")
        yield Label("", id="stat-phase")
        with Container(classes="stat-row"):
            yield Label("완성도", id="label-completion")
        yield ProgressBar(total=100, id="bar-completion", show_eta=False)
        with Container(classes="stat-row"):
            yield Label("테스트", id="label-test")
        yield ProgressBar(total=100, id="bar-test", show_eta=False)
        yield Label("", id="stat-lint")
        yield Label("", id="stat-type")
        yield Label("", id="stat-build")

    def update_progress(self, data: dict) -> None:
        """진행 상황을 업데이트한다."""
        it = data.get("iteration", 0)
        phase = data.get("phase", "-")
        completion = data.get("completion_percent", 0.0)
        test_rate = data.get("test_pass_rate", 0.0)
        lint = data.get("lint_errors", 0)
        type_err = data.get("type_errors", 0)
        build = data.get("build_success", False)

        self.query_one("#stat-iteration", Label).update(f"반복: {it}회")
        self.query_one("#stat-phase", Label).update(f"Phase: {phase}")
        self.query_one("#label-completion", Label).update(
            f"완성도: {completion:.1f}%"
        )
        self.query_one("#bar-completion", ProgressBar).update(progress=completion)
        self.query_one("#label-test", Label).update(f"테스트: {test_rate:.1f}%")
        self.query_one("#bar-test", ProgressBar).update(progress=test_rate)
        lint_color = "green" if lint == 0 else "red"
        self.query_one("#stat-lint", Label).update(
            f"[{lint_color}]린트 에러: {lint}건[/{lint_color}]"
        )
        type_color = "green" if type_err == 0 else "red"
        self.query_one("#stat-type", Label).update(
            f"[{type_color}]타입 에러: {type_err}건[/{type_color}]"
        )
        build_color = "green" if build else "red"
        build_text = "성공" if build else "실패"
        self.query_one("#stat-build", Label).update(
            f"[{build_color}]빌드: {build_text}[/{build_color}]"
        )


class DevScreen(Screen):
    """개발 진행 대시보드.

    좌측: 진행 상황 + 실시간 로그
    우측: 크리티컬 이슈 채팅 (질문이 올 때만 활성화)
    """

    CSS = """
    DevScreen {
        background: $surface;
    }
    #main-layout {
        height: 1fr;
    }
    #left-panel {
        width: 2fr;
        height: 100%;
    }
    #log-area {
        height: 1fr;
        border: solid $primary;
        margin: 0 1 1 1;
    }
    #right-panel {
        width: 1fr;
        height: 100%;
        border: solid $accent;
        margin: 1 1 1 0;
    }
    #question-area {
        height: 1fr;
        overflow-y: auto;
        padding: 1;
    }
    #question-input-row {
        height: 5;
        margin: 0 1 1 1;
    }
    #question-input {
        width: 1fr;
    }
    #question-send-btn {
        width: 10;
        margin-left: 1;
    }
    #right-title {
        text-align: center;
        background: $accent;
        color: $text;
        padding: 1;
    }
    .question-box {
        background: $warning 20%;
        border: solid $warning;
        padding: 1;
        margin-bottom: 1;
    }
    .completed-box {
        background: $success 20%;
        border: solid $success;
        padding: 1;
        margin-bottom: 1;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [  # type: ignore[assignment]
        Binding("ctrl+s", "send_answer", "답변 전송", show=True),
        Binding("escape", "quit_app", "종료"),
    ]

    def __init__(
        self,
        project_path: Path,
        spec: str,
        event_bus: EventBus,
    ) -> None:
        super().__init__()
        self._project_path = project_path
        self._spec = spec
        self._event_bus = event_bus
        self._waiting_for_answer = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-layout"):
            with Vertical(id="left-panel"):
                yield StatusPanel(id="status-panel")
                yield RichLog(id="log-area", highlight=True, markup=True)
            with Vertical(id="right-panel"):
                yield Label("💬 크리티컬 이슈 / 완성 보고", id="right-title")
                yield ScrollableContainer(id="question-area")
                with Horizontal(id="question-input-row"):
                    yield Input(
                        placeholder="답변 입력...",
                        id="question-input",
                        disabled=True,
                    )
                    yield Button("전송", id="question-send-btn", variant="warning", disabled=True)
        yield Footer()

    def on_mount(self) -> None:
        log = self.query_one("#log-area", RichLog)
        log.write("[bold green]🚀 자율 개발 에이전트 시작[/bold green]")
        log.write(f"프로젝트: {self._project_path}")
        log.write("스펙이 확정되었습니다. 개발을 시작합니다...\n")

        self.run_worker(self._listen_events(), exclusive=False)
        self.run_worker(self._run_orchestrator(), exclusive=False)

    async def _run_orchestrator(self) -> None:
        """백그라운드에서 Orchestrator를 실행한다."""
        orchestrator = AutonomousOrchestrator(
            project_path=str(self._project_path),
            spec=self._spec,
            event_bus=self._event_bus,
        )
        await orchestrator.run()

    async def _listen_events(self) -> None:
        """이벤트 버스를 구독하여 UI를 업데이트한다."""
        q = self._event_bus.subscribe()
        try:
            while True:
                event: Event = await q.get()
                self._handle_event(event)
        except asyncio.CancelledError:
            pass

    def _handle_event(self, event: Event) -> None:
        """이벤트 타입에 따라 UI를 업데이트한다."""
        if event.type == EventType.LOG:
            self._on_log(event.data)
        elif event.type == EventType.PROGRESS:
            self._on_progress(event.data)
        elif event.type == EventType.QUESTION:
            self._on_question(event.data)
        elif event.type == EventType.COMPLETED:
            self._on_completed(event.data)

    def _on_log(self, data: dict) -> None:
        log = self.query_one("#log-area", RichLog)
        level = data.get("level", "info")
        msg = data.get("message", "")
        color_map = {"error": "red", "warning": "yellow", "info": "white"}
        color = color_map.get(level, "white")
        log.write(f"[{color}]{msg}[/{color}]")

    def _on_progress(self, data: dict) -> None:
        panel = self.query_one("#status-panel", StatusPanel)
        panel.update_progress(data)

    def _on_question(self, data: dict) -> None:
        """크리티컬 이슈 질문을 표시하고 입력을 활성화한다."""
        issue = data.get("issue", {})
        desc = issue.get("description", "")
        suggestion = issue.get("suggestion", "")

        area = self.query_one("#question-area", ScrollableContainer)
        content = f"🚨 [bold]CRITICAL ISSUE[/bold]\n\n{desc}"
        if suggestion:
            content += f"\n\n💡 제안: {suggestion}"
        box = Static(content, classes="question-box")
        area.mount(box)
        area.scroll_end(animate=False)

        # 입력 활성화
        self._waiting_for_answer = True
        q_input = self.query_one("#question-input", Input)
        q_input.disabled = False
        q_input.placeholder = "크리티컬 이슈 답변 (Enter 스킵)..."
        q_input.focus()
        self.query_one("#question-send-btn", Button).disabled = False

    def _on_completed(self, data: dict) -> None:
        """완성 보고를 표시하고 비크리티컬 질문이 있으면 입력 활성화."""
        is_done = data.get("is_complete", False)
        area = self.query_one("#question-area", ScrollableContainer)

        summary = (
            f"{'✅ 프로젝트 완성!' if is_done else '⏸ 중간 보고'}\n\n"
            f"반복: {data.get('iteration', 0)}회\n"
            f"테스트: {data.get('test_pass_rate', 0):.1f}%\n"
            f"린트: {data.get('lint_errors', 0)}건\n"
            f"타입: {data.get('type_errors', 0)}건\n"
            f"빌드: {'성공' if data.get('build_success') else '실패'}"
        )

        box = Static(summary, classes="completed-box")
        area.mount(box)

        pending = data.get("pending_questions", [])
        if pending:
            qs_text = "\n".join(
                f"{i+1}. {q.get('description', '')}" for i, q in enumerate(pending)
            )
            q_box = Static(
                f"📋 비크리티컬 질문 {len(pending)}건:\n{qs_text}",
                classes="question-box",
            )
            area.mount(q_box)
            area.scroll_end(animate=False)

            self._waiting_for_answer = True
            q_input = self.query_one("#question-input", Input)
            q_input.disabled = False
            q_input.placeholder = "피드백 입력 (없으면 'done')..."
            q_input.focus()
            self.query_one("#question-send-btn", Button).disabled = False

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "question-input":
            self.action_send_answer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "question-send-btn":
            self.action_send_answer()

    def action_send_answer(self) -> None:
        """사용자 답변을 이벤트 버스로 전달한다."""
        if not self._waiting_for_answer:
            return
        q_input = self.query_one("#question-input", Input)
        answer = q_input.value.strip()
        q_input.value = ""
        q_input.disabled = True
        self.query_one("#question-send-btn", Button).disabled = True
        self._waiting_for_answer = False
        self.run_worker(self._event_bus.put_answer(answer or "done"), exclusive=False)

    def action_quit_app(self) -> None:
        self.app.exit()


# ─── 메인 앱 ─────────────────────────────────────────────────────────

class AgentApp(App):
    """자율 개발 에이전트 TUI 앱."""

    TITLE = "🤖 Autonomous Dev Agent"
    CSS = """
    AgentApp {
        background: $surface;
    }
    #title {
        text-align: center;
        background: $primary;
        color: $text;
        padding: 1;
        margin-bottom: 1;
    }
    """
    BINDINGS: ClassVar[list[Binding]] = [  # type: ignore[assignment]
        Binding("ctrl+c", "quit", "종료"),
        Binding("ctrl+q", "quit", "종료"),
    ]

    def __init__(self, project_path: Path, spec_path: Path | None = None) -> None:
        super().__init__()
        self._project_path = project_path
        self._spec_path = spec_path
        self._event_bus = EventBus()

    def on_mount(self) -> None:
        """앱 시작 시 spec_path가 있으면 DevScreen, 없으면 SpecScreen."""
        if self._spec_path and self._spec_path.exists():
            spec = self._spec_path.read_text()
            self.push_screen(DevScreen(self._project_path, spec, self._event_bus))
        else:
            self.push_screen(SpecScreen(self._project_path, self._event_bus))


def run_tui(project_path: str | None = None, spec_file: str | None = None) -> None:
    """TUI를 실행한다.

    Args:
        project_path: 프로젝트 루트 경로 (없으면 현재 디렉토리)
        spec_file: 스펙 파일 경로 (없으면 스펙 대화 화면부터 시작)
    """
    path = Path(project_path) if project_path else Path.cwd()
    spec = Path(spec_file) if spec_file else None
    app = AgentApp(project_path=path, spec_path=spec)
    app.run()
