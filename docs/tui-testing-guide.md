# TUI 테스팅 가이드

Autonomous Dev Agent의 TUI(Text User Interface)를 직접 실행하고 테스트하는 방법을 다룬다.

---

## 목차

1. [환경 설정](#1-환경-설정)
2. [TUI 실행 방법](#2-tui-실행-방법)
3. [화면 구성과 조작법](#3-화면-구성과-조작법)
4. [수동 테스트 시나리오](#4-수동-테스트-시나리오)
5. [자동화 테스트 실행](#5-자동화-테스트-실행)
6. [헤드리스 테스트 직접 작성하기](#6-헤드리스-테스트-직접-작성하기)
7. [디버깅 팁](#7-디버깅-팁)
8. [문제 해결](#8-문제-해결)

---

## 1. 환경 설정

### 1.1 사전 요구사항

- Python 3.12 이상
- uv 패키지 매니저
- 터미널 에뮬레이터 (최소 80x24 크기 권장, 120x40 이상 권장)

### 1.2 초기 설정

```bash
# 프로젝트 루트에서 실행
cd autonomous-dev-agent

# 자동 설정 (uv, 가상환경, 의존성 모두 설치)
./scripts/setup.sh

# 또는 수동 설정
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### 1.3 환경변수 설정

```bash
# .env 파일 생성
cp .env.example .env

# .env 파일 편집 — API 키 설정 (API 키 방식 사용 시)
# ANTHROPIC_API_KEY=sk-ant-your-key-here

# Claude Code subscription 방식은 API 키 없이 사용 가능
# claude init 으로 로그인하면 됨
```

### 1.4 Textual 설치 확인

```bash
# textual이 정상 설치되었는지 확인
python -c "import textual; print(f'Textual {textual.__version__} OK')"
```

---

## 2. TUI 실행 방법

TUI를 실행하는 방법은 3가지이다.

### 방법 A: `adev` CLI 명령어 (권장)

```bash
# 현재 디렉토리를 프로젝트로, 스펙 대화부터 시작
adev

# 특정 프로젝트 경로 지정
adev /path/to/my-project

# 스펙 파일을 지정하여 바로 개발 대시보드로 진입
adev /path/to/my-project spec.md
```

> `adev`는 `pyproject.toml`의 `[project.scripts]`에 등록된 CLI 명령어이다.
> `uv pip install -e ".[dev]"` 후 사용 가능하다.

### 방법 B: Python 모듈로 실행

```bash
# 스펙 대화부터 시작
python -m src.ui.tui

# 프로젝트 경로 지정
python -m src.ui.tui /path/to/my-project

# 스펙 파일 지정 → 바로 DevScreen
python -m src.ui.tui /path/to/my-project spec.md
```

### 방법 C: Python 코드에서 직접 호출

```python
from src.ui.tui.app import run_tui

# 스펙 대화부터
run_tui()

# 프로젝트 경로 + 스펙 파일 지정
run_tui(project_path="/path/to/project", spec_file="spec.md")
```

### 실행 모드 정리

| 인자 | 시작 화면 | 설명 |
|------|-----------|------|
| 없음 | SpecScreen | 스펙 대화를 통해 프로젝트 정의 |
| `<project_path>` | SpecScreen | 지정 경로에서 스펙 대화 시작 |
| `<project_path> <spec.md>` | DevScreen | 스펙 파일을 읽고 바로 개발 시작 |

---

## 3. 화면 구성과 조작법

TUI는 두 개의 화면으로 구성된다.

### 3.1 SpecScreen (스펙 확정 대화)

스펙 파일 없이 실행하면 이 화면이 표시된다.

```
┌─────────────────────────────────────────────────────────┐
│ 🤖 Autonomous Dev Agent                        [Clock] │
├─────────────────────────────────────────────────────────┤
│ 💬 스펙 확정 대화 — Claude와 대화하여 프로젝트를 정의하세요    │
│ ┌─────────────────────────────────────────────────────┐ │
│ │                                                     │ │
│ │ 🤖 Claude                                           │ │
│ │ 어떤 프로젝트를 만들고 싶으신가요?                        │ │
│ │                                                     │ │
│ │                              👤 나                   │ │
│ │              TODO 앱을 만들고 싶어요                   │ │
│ │                                                     │ │
│ │ 🤖 Claude                                           │ │
│ │ TODO 앱이군요! 몇 가지 질문이 있습니다...                │ │
│ │                                                     │ │
│ └─────────────────────────────────────────────────────┘ │
│ ┌──────────────────────────────────────────┐ ┌────────┐ │
│ │ 메시지 입력... (Ctrl+S 또는 Enter로 전송)   │ │ 전송   │ │
│ └──────────────────────────────────────────┘ └────────┘ │
│ Ctrl+S 전송 │ Escape 종료                                │
└─────────────────────────────────────────────────────────┘
```

**키 바인딩:**

| 키 | 동작 |
|----|------|
| `Enter` | 메시지 전송 |
| `Ctrl+S` | 메시지 전송 (대체) |
| `Escape` | 앱 종료 |
| `Ctrl+C` | 앱 종료 |
| `Ctrl+Q` | 앱 종료 |

**동작 흐름:**
1. Claude가 자동으로 스펙 관련 질문을 시작한다
2. 사용자가 입력창에 답변을 입력하고 Enter 또는 전송 버튼을 누른다
3. 대화가 진행되며 스펙이 구체화된다
4. 스펙이 확정되면 자동으로 DevScreen으로 전환된다

### 3.2 DevScreen (개발 대시보드)

스펙 파일과 함께 실행하거나 SpecScreen에서 스펙이 확정되면 이 화면이 표시된다.

```
┌──────────────────────────────────────────────────────────────────┐
│ 🤖 Autonomous Dev Agent                                 [Clock] │
├────────────────────────────────────┬─────────────────────────────┤
│ 📊 진행 상황                        │ 💬 크리티컬 이슈 / 완성 보고    │
│ ┌────────────────────────────────┐ │ ┌───────────────────────────┐│
│ │ 반복: 5회                       │ │ │                           ││
│ │ Phase: coding                  │ │ │ 🚨 CRITICAL ISSUE          ││
│ │ 완성도: 75.0%                   │ │ │ 로그인은 소셜만 지원?        ││
│ │ ████████████░░░░░  75%         │ │ │ 아니면 이메일도?             ││
│ │ 테스트: 60.0%                   │ │ │                           ││
│ │ ██████████░░░░░░░  60%         │ │ │ 💡 제안: 명확화 필요         ││
│ │ 린트 에러: 0건                   │ │ │                           ││
│ │ 타입 에러: 0건                   │ │ │ ✅ 프로젝트 완성!            ││
│ │ 빌드: 성공                      │ │ │ 반복: 10회                  ││
│ └────────────────────────────────┘ │ │ 테스트: 100.0%              ││
│ ┌────────────────────────────────┐ │ │ 린트: 0건                   ││
│ │ 🚀 자율 개발 에이전트 시작         │ │ │ 빌드: 성공                  ││
│ │ 프로젝트: /path/to/project     │ │ └───────────────────────────┘│
│ │ 스펙이 확정되었습니다...          │ │ ┌──────────────────┐ ┌─────┐│
│ │ [INFO] 코드 작성 시작...         │ │ │ 답변 입력...       │ │전송 ││
│ │ [INFO] 테스트 실행 중...          │ │ └──────────────────┘ └─────┘│
│ └────────────────────────────────┘ │                              │
├──────────────────────────────────────────────────────────────────┤
│ Ctrl+S 답변 전송 │ Escape 종료                                     │
└──────────────────────────────────────────────────────────────────┘
```

**레이아웃:**
- **좌측 (2/3)**: 상태 패널 + 실시간 로그
- **우측 (1/3)**: 크리티컬 이슈 Q&A + 완성 보고

**키 바인딩:**

| 키 | 동작 |
|----|------|
| `Ctrl+S` | 크리티컬 이슈 답변 전송 |
| `Escape` | 앱 종료 |
| `Ctrl+C` | 앱 종료 |
| `Ctrl+Q` | 앱 종료 |

**우측 패널 동작:**
- 평상시: 입력창과 전송 버튼이 **비활성화** 상태
- 크리티컬 이슈 발생 시: 입력창이 **활성화**되고 포커스가 이동
- 답변 전송 후: 다시 **비활성화**
- 프로젝트 완성 시: 완성 보고 + 비크리티컬 질문 모아서 표시

### 3.3 상태 패널 (StatusPanel) 항목 설명

| 항목 | 설명 | 색상 |
|------|------|------|
| 반복 | 자율 루프 반복 횟수 | - |
| Phase | 현재 진행 단계 (init, planning, coding, testing 등) | - |
| 완성도 | 전체 완성 비율 (프로그레스 바) | - |
| 테스트 | 테스트 통과율 (프로그레스 바) | - |
| 린트 에러 | ruff 린트 에러 수 | 0건=초록, 1건 이상=빨강 |
| 타입 에러 | mypy 타입 에러 수 | 0건=초록, 1건 이상=빨강 |
| 빌드 | 빌드 성공 여부 | 성공=초록, 실패=빨강 |

---

## 4. 수동 테스트 시나리오

직접 TUI를 실행하여 확인할 수 있는 테스트 시나리오들이다.

### 4.1 SpecScreen 테스트

#### 시나리오 1: 기본 실행 및 화면 확인

```bash
# 스펙 파일 없이 실행
adev
# 또는
python -m src.ui.tui
```

**확인 사항:**
- [ ] SpecScreen이 표시되는가
- [ ] Header에 "Autonomous Dev Agent" 제목이 보이는가
- [ ] "💬 스펙 확정 대화" 타이틀이 보이는가
- [ ] 입력창에 포커스가 잡혀 있는가
- [ ] Footer에 키 바인딩이 표시되는가

#### 시나리오 2: 메시지 전송

```bash
adev
```

**테스트 순서:**
1. 입력창에 "TODO 앱을 만들고 싶습니다" 입력
2. Enter 키 누르기
3. 확인: 채팅 영역에 "👤 나" 메시지가 추가되는가
4. 확인: 입력창이 비워졌는가
5. 확인: Claude 응답이 "🤖 Claude" 메시지로 나타나는가

#### 시나리오 3: 빈 입력 방지

1. 입력창을 비운 상태에서 Enter 누르기
2. 확인: 아무 메시지도 추가되지 않는가
3. 공백만 입력 후 Enter 누르기
4. 확인: 역시 메시지가 추가되지 않는가

#### 시나리오 4: 전송 버튼 사용

1. 입력창에 텍스트 입력
2. "전송" 버튼 클릭 (마우스 또는 Tab→Enter)
3. 확인: Enter와 동일하게 동작하는가

#### 시나리오 5: 종료

1. `Escape` 키 누르기
2. 확인: 앱이 종료되는가
3. 재실행 후 `Ctrl+C` 누르기
4. 확인: 앱이 종료되는가

### 4.2 DevScreen 테스트

#### 시나리오 1: 스펙 파일로 바로 진입

```bash
# 테스트용 스펙 파일 생성
cat > /tmp/test-spec.md << 'EOF'
# 테스트 프로젝트 스펙

## 개요
간단한 Hello World 프로젝트

## 기능
- 콘솔에 "Hello, World!" 출력
EOF

# DevScreen으로 바로 진입
adev /tmp/test-project /tmp/test-spec.md
# 또는
python -m src.ui.tui /tmp/test-project /tmp/test-spec.md
```

**확인 사항:**
- [ ] DevScreen이 바로 표시되는가 (SpecScreen 건너뜀)
- [ ] 좌측에 상태 패널이 보이는가
- [ ] 좌측 하단에 로그 영역이 보이는가
- [ ] 우측에 "💬 크리티컬 이슈 / 완성 보고" 패널이 보이는가
- [ ] 초기 로그에 "🚀 자율 개발 에이전트 시작" 메시지가 보이는가
- [ ] 우측 입력창이 비활성화 상태인가

#### 시나리오 2: 상태 패널 업데이트 관찰

개발이 진행되면서 상태 패널이 자동 업데이트되는지 확인한다.

**확인 사항:**
- [ ] 반복 횟수가 증가하는가
- [ ] Phase가 변경되는가
- [ ] 프로그레스 바가 움직이는가
- [ ] 린트/타입 에러 수가 변하는가
- [ ] 빌드 상태가 업데이트되는가

#### 시나리오 3: 크리티컬 이슈 응답

크리티컬 이슈가 발생하면:

**확인 사항:**
- [ ] 우측 패널에 "🚨 CRITICAL ISSUE" 박스가 나타나는가
- [ ] 입력창이 활성화되는가
- [ ] 입력창에 포커스가 이동하는가
- [ ] 답변 입력 후 전송하면 입력창이 다시 비활성화되는가

### 4.3 화면 전환 테스트

1. `adev`로 실행 (SpecScreen 시작)
2. Claude와 스펙 대화 진행
3. 스펙이 확정되면 자동으로 DevScreen으로 전환되는지 확인

---

## 5. 자동화 테스트 실행

### 5.1 전체 TUI 테스트 실행

```bash
# TUI 테스트만 실행
pytest tests/test_tui.py -v

# 특정 테스트 클래스만 실행
pytest tests/test_tui.py::TestStatusPanel -v
pytest tests/test_tui.py::TestSpecScreen -v
pytest tests/test_tui.py::TestDevScreen -v
pytest tests/test_tui.py::TestAgentApp -v
pytest tests/test_tui.py::TestChatMessage -v
pytest tests/test_tui.py::TestRunTui -v
pytest tests/test_tui.py::TestTuiMain -v

# 특정 테스트만 실행
pytest tests/test_tui.py::TestSpecScreen::test_action_send_adds_message_and_clears_input -v
```

### 5.2 커버리지 포함 실행

```bash
# 커버리지 리포트와 함께 실행
pytest tests/test_tui.py -v --cov=src/ui/tui --cov-report=term-missing

# HTML 리포트 생성
pytest tests/test_tui.py -v --cov=src/ui/tui --cov-report=html
# 결과: htmlcov/index.html
```

### 5.3 전체 테스트 스위트 실행

```bash
# 프로젝트 전체 테스트
pytest tests/ -v --cov

# 린트 + 타입체크도 함께
ruff check src/ui/tui/
mypy src/ui/tui/
```

### 5.4 테스트 클래스별 설명

| 테스트 클래스 | 대상 | 테스트 내용 |
|--------------|------|-------------|
| `TestChatMessage` | `ChatMessage` | CSS 클래스 할당 (msg-assistant / msg-user) |
| `TestStatusPanel` | `StatusPanel` | 레이블 업데이트, 프로그레스 바 값, 빌드 실패 표시 |
| `TestAgentApp` | `AgentApp` | on_mount 시 화면 전환 (SpecScreen vs DevScreen) |
| `TestDevScreen` | `DevScreen` | 이벤트 처리 (LOG/PROGRESS/QUESTION/COMPLETED), 입력 활성화/비활성화 |
| `TestSpecScreen` | `SpecScreen` | 빈 입력 무시, 메시지 추가, 버튼 클릭, 화면 전환 |
| `TestRunTui` | `run_tui()` | AgentApp 생성 및 run() 호출 |
| `TestTuiMain` | `__main__.py` | 모듈 직접 실행 시 run_tui 호출 |

---

## 6. 헤드리스 테스트 직접 작성하기

Textual의 `run_test()` 컨텍스트 매니저를 사용하면 실제 터미널 없이 TUI를 테스트할 수 있다.

### 6.1 기본 구조

```python
"""tests/test_my_tui.py"""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Input, Label

from src.ui.tui.app import AgentApp, DevScreen, SpecScreen, StatusPanel
from src.utils.events import Event, EventBus, EventType


# Orchestrator/SpecBuilder 등의 백그라운드 실행을 차단하는 헬퍼
async def _hang(*_args, **_kwargs):
    """절대 완료되지 않는 코루틴 — 워커가 실제로 돌지 않도록 방지."""
    import asyncio
    await asyncio.sleep(9_999)
```

### 6.2 StatusPanel 단독 테스트

```python
class _StatusApp(App[None]):
    """StatusPanel만 테스트하기 위한 최소 앱."""
    def compose(self) -> ComposeResult:
        yield StatusPanel(id="panel")


class TestMyStatusPanel:
    async def test_초기값_확인(self):
        app = _StatusApp()
        async with app.run_test() as pilot:
            panel = app.query_one("#panel", StatusPanel)

            # update_progress 호출 전에는 빈 상태
            panel.update_progress({
                "iteration": 0,
                "phase": "init",
                "completion_percent": 0.0,
                "test_pass_rate": 0.0,
                "lint_errors": 0,
                "type_errors": 0,
                "build_success": False,
            })
            await pilot.pause()

            assert "0회" in str(app.query_one("#stat-iteration", Label).content)
            assert "init" in str(app.query_one("#stat-phase", Label).content)
```

### 6.3 SpecScreen 테스트

```python
class TestMySpecScreen:
    async def test_사용자_메시지_전송(self, tmp_path: Path):
        # SpecBuilder.build를 무한 대기로 교체 (실제 Claude API 호출 방지)
        with patch("src.ui.tui.app.SpecBuilder") as mock_cls:
            instance = MagicMock()
            instance.build = _hang
            mock_cls.return_value = instance

            event_bus = EventBus()

            class _App(App[None]):
                def on_mount(self):
                    self.push_screen(SpecScreen(tmp_path, event_bus))

            app = _App()
            async with app.run_test() as pilot:
                await pilot.pause()
                screen = app.screen

                # 입력 필드에 텍스트 설정
                user_input = screen.query_one("#user-input", Input)
                user_input.value = "테스트 메시지"

                # 전송 액션 실행
                screen.action_send()
                await pilot.pause()

                # 검증
                assert len(screen.query(".msg-user")) == 1
                assert user_input.value == ""  # 입력창이 비워졌는지
```

### 6.4 DevScreen 이벤트 테스트

```python
class TestMyDevScreen:
    async def test_로그_이벤트_처리(self, tmp_path: Path):
        with patch("src.ui.tui.app.AutonomousOrchestrator") as mock_cls:
            mock_cls.return_value.run = _hang
            event_bus = EventBus()

            class _App(App[None]):
                def on_mount(self):
                    self.push_screen(DevScreen(tmp_path, "스펙 내용", event_bus))

            app = _App()
            async with app.run_test() as pilot:
                await pilot.pause()
                screen = app.screen

                # 이벤트 발행
                await event_bus.publish(Event(
                    type=EventType.LOG,
                    data={"level": "info", "message": "테스트 로그"},
                ))
                await pilot.pause()

                # RichLog에 메시지가 기록되었는지 확인
                # (RichLog 내부 content는 직접 검증이 어려우므로 예외 없이 실행되면 성공)

    async def test_크리티컬_이슈_입력_활성화(self, tmp_path: Path):
        with patch("src.ui.tui.app.AutonomousOrchestrator") as mock_cls:
            mock_cls.return_value.run = _hang
            event_bus = EventBus()

            class _App(App[None]):
                def on_mount(self):
                    self.push_screen(DevScreen(tmp_path, "스펙", event_bus))

            app = _App()
            async with app.run_test() as pilot:
                await pilot.pause()
                screen = app.screen

                # QUESTION 이벤트 직접 호출
                screen._on_question({
                    "issue": {
                        "description": "인증 방식이 불명확합니다",
                        "suggestion": "OAuth 또는 JWT 중 선택 필요",
                    }
                })
                await pilot.pause()

                # 입력 활성화 확인
                q_input = screen.query_one("#question-input", Input)
                assert not q_input.disabled
                assert screen._waiting_for_answer
```

### 6.5 이벤트 발행을 통한 통합 테스트

```python
class TestEventIntegration:
    async def test_이벤트_버스를_통한_상태_업데이트(self, tmp_path: Path):
        with patch("src.ui.tui.app.AutonomousOrchestrator") as mock_cls:
            mock_cls.return_value.run = _hang
            event_bus = EventBus()

            class _App(App[None]):
                def on_mount(self):
                    self.push_screen(DevScreen(tmp_path, "스펙", event_bus))

            app = _App()
            async with app.run_test() as pilot:
                await pilot.pause()

                # PROGRESS 이벤트를 EventBus를 통해 발행
                await event_bus.publish(Event(
                    type=EventType.PROGRESS,
                    data={
                        "iteration": 10,
                        "phase": "testing",
                        "completion_percent": 85.0,
                        "test_pass_rate": 92.0,
                        "lint_errors": 0,
                        "type_errors": 0,
                        "build_success": True,
                    },
                ))
                await pilot.pause()

                # StatusPanel이 업데이트되었는지 확인
                screen = app.screen
                assert "85.0%" in str(
                    screen.query_one("#label-completion", Label).content
                )
                assert "92.0%" in str(
                    screen.query_one("#label-test", Label).content
                )
```

### 6.6 주의사항

1. **mock 필수**: `SpecBuilder`와 `AutonomousOrchestrator`는 반드시 mock 처리한다. 실제 Claude API를 호출하면 테스트가 느려지고 비용이 발생한다.

2. **`await pilot.pause()`**: UI 업데이트는 비동기이므로, 상태 변경 후 반드시 `await pilot.pause()`를 호출하여 렌더링이 완료될 때까지 기다린다.

3. **`asyncio_mode = "auto"`**: `pyproject.toml`에 설정되어 있으므로 `@pytest.mark.asyncio`를 매번 붙일 필요 없다. `async def test_*`만으로 충분하다.

4. **Screen 테스트 패턴**: Textual Screen은 직접 인스턴스화할 수 없다. 항상 최소 App을 만들고 `on_mount`에서 `push_screen()`으로 마운트한다.

---

## 7. 디버깅 팁

### 7.1 Textual 개발자 도구

```bash
# Textual 개발자 콘솔 활성화
textual run --dev src/ui/tui/app.py

# 또는 환경변수로 디버그 모드
TEXTUAL=devtools python -m src.ui.tui
```

개발자 콘솔에서 확인할 수 있는 것:
- 실시간 DOM 트리
- CSS 스타일
- 이벤트 로그
- 위젯 상태

### 7.2 Textual 콘솔 연결

터미널 두 개를 열어야 한다:

```bash
# 터미널 1: 개발자 콘솔 실행
textual console

# 터미널 2: 앱을 디버그 모드로 실행
textual run --dev -c python -m src.ui.tui
```

### 7.3 스크린샷 캡처 (자동 테스트에서)

```python
async def test_with_screenshot(self, tmp_path: Path):
    app = _StatusApp()
    async with app.run_test() as pilot:
        # ... 테스트 코드 ...
        await pilot.pause()

        # SVG 스크린샷 저장
        screenshot = app.export_screenshot()
        Path("/tmp/tui-screenshot.svg").write_text(screenshot)
```

### 7.4 로그 출력으로 디버깅

```python
# 테스트 중 print 대신 Textual의 log 사용
from textual import log

class TestDebug:
    async def test_디버그_예시(self, tmp_path: Path):
        app = _StatusApp()
        async with app.run_test() as pilot:
            panel = app.query_one("#panel", StatusPanel)
            log(f"Panel children: {panel.children}")
            log(f"Panel CSS: {panel.styles}")
```

---

## 8. 문제 해결

### 8.1 "ModuleNotFoundError: No module named 'src'"

```bash
# 프로젝트를 editable 모드로 설치
uv pip install -e ".[dev]"

# 또는 PYTHONPATH 설정
export PYTHONPATH=/path/to/autonomous-dev-agent:$PYTHONPATH
```

### 8.2 "ModuleNotFoundError: No module named 'textual'"

```bash
# textual 설치 확인
uv pip install textual>=0.80.0

# 가상환경 활성화 확인
source .venv/bin/activate
which python  # .venv 안의 python이어야 함
```

### 8.3 터미널이 너무 작아서 깨짐

- 최소 80x24, 권장 120x40 이상으로 터미널 크기를 조절한다
- 또는 터미널 폰트 크기를 줄인다

### 8.4 API 키 없이 테스트하기

TUI 화면 자체는 API 키 없이도 테스트 가능하다. 자동화 테스트(`pytest`)는 `SpecBuilder`와 `AutonomousOrchestrator`를 mock 처리하므로 API 키가 필요 없다.

단, 수동으로 실제 대화를 테스트하려면 다음 중 하나가 필요하다:
- `.env`에 `ANTHROPIC_API_KEY` 설정
- `claude init`으로 Claude Code subscription 로그인

### 8.5 테스트가 hang 걸릴 때

`_hang()` mock이 제대로 적용되지 않으면 테스트가 멈출 수 있다. `patch` 경로가 정확한지 확인한다:

```python
# 올바른 patch 경로 (import 경로가 아닌, 사용 위치 기준)
with patch("src.ui.tui.app.SpecBuilder"):      # SpecScreen용
with patch("src.ui.tui.app.AutonomousOrchestrator"):  # DevScreen용
```

### 8.6 pytest-asyncio 경고

`pyproject.toml`에 이미 `asyncio_mode = "auto"`가 설정되어 있다. 경고가 나오면 pytest-asyncio 버전을 확인한다:

```bash
uv pip install "pytest-asyncio>=0.24"
```

---

## 부록: EventType 참조

TUI에서 사용하는 이벤트 타입 목록:

| EventType | 방향 | 설명 |
|-----------|------|------|
| `LOG` | Orchestrator → TUI | 로그 메시지 (level + message) |
| `PROGRESS` | Orchestrator → TUI | 진행 상황 업데이트 (iteration, phase, 각종 지표) |
| `QUESTION` | Orchestrator → TUI | 크리티컬 이슈 질문 (issue.description + suggestion) |
| `COMPLETED` | Orchestrator → TUI | 완성/중간 보고 (is_complete, 지표, pending_questions) |
| `SPEC_MESSAGE` | SpecBuilder → TUI | 스펙 대화 메시지 (role + content) |
| `AGENT_OUTPUT` | Orchestrator → TUI | 에이전트 실행 결과 |

### PROGRESS 이벤트 data 구조

```python
{
    "iteration": 5,           # 반복 횟수
    "phase": "coding",        # 현재 단계
    "completion_percent": 75.0,  # 완성도 (0~100)
    "test_pass_rate": 60.0,   # 테스트 통과율 (0~100)
    "lint_errors": 2,         # 린트 에러 수
    "type_errors": 1,         # 타입 에러 수
    "build_success": True,    # 빌드 성공 여부
}
```

### QUESTION 이벤트 data 구조

```python
{
    "issue": {
        "description": "로그인은 소셜만? 이메일도?",
        "suggestion": "명확화 필요",
    }
}
```

### COMPLETED 이벤트 data 구조

```python
{
    "is_complete": True,       # 완전 완성 여부
    "iteration": 10,
    "test_pass_rate": 100.0,
    "lint_errors": 0,
    "type_errors": 0,
    "build_success": True,
    "pending_questions": [     # 비크리티컬 질문 목록
        {"description": "색상 테마 선호는?"},
    ],
}
```
