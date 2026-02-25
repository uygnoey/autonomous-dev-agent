# 데이터 모델

Autonomous Dev Agent에서 사용하는 핵심 데이터 구조.

---

## ProjectState

**파일**: `src/utils/state.py`  
**저장 위치**: `{project_path}/.claude/state.json`

자율 루프 중 진행 상태를 추적하며, 토큰 한도 재시작 시 이어받기 위해 JSON으로 영속화된다.

```python
@dataclass
class ProjectState:
    spec: str                          # 확정된 프로젝트 스펙 (전체 텍스트)
    phase: PhaseType                   # 현재 개발 단계
    iteration: int = 0                 # 루프 반복 횟수 (최대 500)
    completion_percent: float = 0.0   # 완성도 점수 (0~100, 가중 평균)
    test_pass_rate: float = 0.0       # 테스트 통과율 (0~100)
    lint_errors: int = 0               # ruff 에러 수
    type_errors: int = 0               # mypy 에러 수
    build_success: bool = False        # 빌드 성공 여부
    pending_questions: list = []       # 비크리티컬 질문 누적 목록
    started_at: str = ""               # 시작 시간 (ISO 8601)
    last_updated_at: str = ""          # 마지막 저장 시간 (ISO 8601)
```

**완성도 계산 (가중 평균):**
```
completion_percent =
    test_pass_rate/100 × 40   (테스트 40%)
  + lint_ok × 15              (린트 15%)
  + type_ok × 15              (타입 15%)
  + build_ok × 30             (빌드 30%)
```

**PhaseType 값:**

| 값 | 설명 |
|----|------|
| `init` | 초기화 (상태 로드 전) |
| `setup` | Phase 1: 프로젝트 초기 구성 |
| `build` | Phase 2~5: 개발 반복 루프 |
| `verify` | 검증 진행 중 |
| `document` | Phase 6: 문서화 |
| `complete` | Phase 7: 완성 |

**JSON 직렬화 예시:**
```json
{
  "spec": "# 프로젝트 스펙\n...",
  "phase": "build",
  "iteration": 12,
  "completion_percent": 75.0,
  "test_pass_rate": 83.3,
  "lint_errors": 0,
  "type_errors": 2,
  "build_success": true,
  "pending_questions": [
    {
      "description": "대시보드 색상 테마를 다크로 할까요 라이트로 할까요?",
      "level": "non_critical"
    }
  ],
  "started_at": "2025-02-25T10:00:00.000000",
  "last_updated_at": "2025-02-25T10:42:31.123456"
}
```

---

## Event

**파일**: `src/utils/events.py`

Orchestrator와 TUI 사이의 비동기 메시지.

```python
@dataclass
class Event:
    type: EventType
    data: dict[str, Any]
```

**이벤트 타입별 data 스키마:**

### `LOG`
```python
{
    "message": str,
    "level": "info" | "warning" | "error"  # 기본값: "info"
}
```

### `PROGRESS`
```python
{
    "iteration": int,
    "completion_percent": float,
    "test_pass_rate": float,
    "lint_errors": int,
    "type_errors": int,
    "build_success": bool,
    "phase": str,
}
```

### `QUESTION`
```python
{
    "issue": {
        "description": str,
        "level": "critical",
        "suggestion": str | None,
    }
}
```

### `SPEC_MESSAGE`
```python
{
    "role": "assistant" | "user",
    "content": str,
}
```

### `COMPLETED`
```python
{
    "is_complete": bool,
    "iteration": int,
    "test_pass_rate": float,
    "lint_errors": int,
    "type_errors": int,
    "build_success": bool,
    "pending_questions": list[dict],
}
```

---

## CodeChunk

**파일**: `src/rag/indexer.py`

RAG 검색의 기본 단위. 코드 파일을 50줄 단위로 분할한 청크.

```python
@dataclass
class CodeChunk:
    file_path: str    # 프로젝트 루트 기준 상대 경로 (예: "src/agents/executor.py")
    content: str      # 청크 코드 내용
    start_line: int   # 시작 줄 (1-based)
    end_line: int     # 끝 줄 (1-based, 포함)
```

---

## AgentProfile

**파일**: `src/agents/executor.py`

에이전트 실행에 필요한 불변 설정 프로필.

```python
@dataclass(frozen=True)
class AgentProfile:
    agent_type: AgentType
    model: str                    # 사용할 Claude 모델 ID
    system_prompt: str            # 에이전트 역할 지시문
    allowed_tools: tuple[str, ...]  # 허용된 Claude Code 도구 목록
```

**모델 할당:**

| AgentType | Model |
|-----------|-------|
| `architect` | `claude-opus-4-6` (복잡한 설계 결정) |
| `coder` | `claude-sonnet-4-6` |
| `tester` | `claude-sonnet-4-6` |
| `reviewer` | `claude-sonnet-4-6` |
| `documenter` | `claude-sonnet-4-6` |

---

## IssueLevel

**파일**: `src/orchestrator/issue_classifier.py`

이슈 심각도 분류.

```python
class IssueLevel(StrEnum):
    CRITICAL = "critical"          # 즉시 사람에게 질문
    NON_CRITICAL = "non_critical"  # 완성 후 모아서 전달
```

**IssueClassifier 반환 스키마:**
```python
[
    {
        "description": str,        # 이슈 설명
        "level": IssueLevel,       # "critical" | "non_critical"
        "suggestion": str | None,  # 해결 제안 (선택)
    }
]
```
