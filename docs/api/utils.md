# Utils API

유틸리티 모듈 API 문서.

---

## EventBus

**파일**: `src/utils/events.py`

Orchestrator와 UI 사이의 비동기 통신을 담당하는 이벤트 버스.

### 이벤트 타입 (EventType)

| 값 | 방향 | 설명 |
|----|------|------|
| `LOG` | Orchestrator → UI | 로그 메시지 |
| `PROGRESS` | Orchestrator → UI | 진행 상황 업데이트 |
| `QUESTION` | Orchestrator → UI | 크리티컬 이슈 질문 |
| `SPEC_MESSAGE` | SpecBuilder ↔ UI | 스펙 확정 대화 메시지 |
| `AGENT_OUTPUT` | Orchestrator → UI | 에이전트 실행 결과 |
| `COMPLETED` | Orchestrator → UI | 완성 보고 |

### Event 데이터 클래스

```python
@dataclass
class Event:
    type: EventType
    data: dict[str, Any] = field(default_factory=dict)
```

### 메서드

#### `subscribe() -> asyncio.Queue[Event]`
새 구독자 큐를 생성하고 반환한다. TUI의 각 화면이 이 큐로 이벤트를 받는다.

#### `publish(event: Event) -> None`
모든 구독자에게 이벤트를 발행한다.

```python
await event_bus.publish(Event(
    type=EventType.LOG,
    data={"message": "작업 시작", "level": "info"},
))
```

#### `wait_for_answer() -> str`
사용자 답변을 기다린다. Orchestrator/SpecBuilder가 호출.

#### `put_answer(answer: str) -> None`
사용자 답변을 큐에 넣는다. TUI가 호출.

#### `has_waiting_answer() -> bool`
대기 중인 답변이 있는지 확인.

---

## ProjectState

**파일**: `src/utils/state.py`

프로젝트 상태를 추적하고 JSON으로 영속화한다. 토큰 한도 재시작 시 이어받기 위함.

### PhaseType

| 값 | 설명 |
|----|------|
| `init` | 초기화 |
| `setup` | 프로젝트 초기 구성 |
| `build` | 개발 반복 루프 |
| `verify` | 검증 |
| `document` | 문서화 |
| `complete` | 완성 |

### 데이터 필드

```python
@dataclass
class ProjectState:
    spec: str                          # 확정된 프로젝트 스펙
    phase: PhaseType                   # 현재 단계
    iteration: int                     # 반복 횟수
    completion_percent: float          # 완성도 (0~100)
    test_pass_rate: float              # 테스트 통과율 (0~100)
    lint_errors: int                   # 린트 에러 수
    type_errors: int                   # 타입 에러 수
    build_success: bool                # 빌드 성공 여부
    pending_questions: list            # 비크리티컬 질문 목록
    started_at: str                    # 시작 시간 (ISO format)
    last_updated_at: str               # 마지막 업데이트 시간
```

### 메서드

#### `save(path: Path) -> None`
`.claude/state.json`에 상태를 저장한다.

#### `load(path: Path) -> ProjectState` (classmethod)
저장된 상태를 복원한다.

#### `load_or_create(path: Path, spec: str) -> ProjectState` (classmethod)
저장된 상태가 있으면 복원, 없으면 새로 생성한다.

```python
state = ProjectState.load_or_create(
    path=project_path / ".claude" / "state.json",
    spec=spec_content,
)
```

---

## call_claude_for_text

**파일**: `src/utils/claude_client.py`

ANTHROPIC_API_KEY 유무에 따라 API 직접 호출 또는 Claude Code 세션을 사용한다.

### 함수 시그니처

```python
async def call_claude_for_text(
    system: str,
    user: str,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 4096,
) -> str:
```

**동작 방식:**
- `ANTHROPIC_API_KEY` 환경변수 있음 → Anthropic API 직접 호출
- `ANTHROPIC_API_KEY` 없음 → Claude Code 세션 (subscription) 사용

```python
response = await call_claude_for_text(
    system="당신은 전문가입니다.",
    user="다음 작업을 계획해줘.",
)
```

---

## setup_logger

**파일**: `src/utils/logger.py`

구조화된 로거를 설정하여 반환한다.

```python
from src.utils.logger import setup_logger

logger = setup_logger(__name__)
logger.info("작업 시작")
logger.warning("주의 사항")
logger.error("에러 발생")
```
