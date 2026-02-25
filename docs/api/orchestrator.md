# Orchestrator API

자율 개발 에이전트의 핵심 실행 계층 API 문서.

---

## AutonomousOrchestrator

**파일**: `src/orchestrator/main.py`

Claude API로 판단하고 Claude Agent SDK로 실행하는 상위 오케스트레이터.

### 생성자

```python
AutonomousOrchestrator(
    project_path: str,
    spec: str,
    event_bus: EventBus | None = None,
)
```

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `project_path` | `str` | 대상 프로젝트 루트 경로 |
| `spec` | `str` | 확정된 프로젝트 스펙 문자열 |
| `event_bus` | `EventBus \| None` | UI 연동용 이벤트 버스. `None`이면 터미널 I/O 사용 |

### 메서드

#### `run() -> None`

메인 자율 루프를 실행한다. 완성 조건을 만족할 때까지 무한 반복.

**완성 조건:**
- 테스트 통과율 100%
- 린트 에러 0건
- 타입 에러 0건
- 빌드 성공

**실행 순서:**
1. Phase 1: 프로젝트 초기 구성 (Setup)
2. 루프 반복: 계획 → 실행 → 검증 → 이슈 처리 → 상태 업데이트
3. Phase 6: 문서화 (Document)
4. Phase 7: 완성 보고

```python
orchestrator = AutonomousOrchestrator(
    project_path="/path/to/project",
    spec="# 프로젝트 스펙\n...",
)
await orchestrator.run()
```

---

## Planner

**파일**: `src/orchestrator/planner.py`

현재 프로젝트 상태를 분석하여 다음 작업을 결정한다.

### 생성자

```python
Planner(model: str = "claude-sonnet-4-6")
```

### 메서드

#### `decide_next_task(state: ProjectState) -> str`

현재 상태를 기반으로 다음 작업 프롬프트를 반환한다.

**우선순위 (높음 → 낮음):**
1. 빌드 실패 → 빌드 수정
2. 테스트 실패 → 테스트/코드 수정
3. 린트/타입 에러 → 수정
4. 미구현 기능 → 구현
5. 모두 통과 → 코드 품질 개선

```python
planner = Planner()
task = await planner.decide_next_task(state)
# → "src/models/user.py에 UserDTO 클래스를 구현하세요. 타입 힌트와 docstring을 포함..."
```

---

## IssueClassifier

**파일**: `src/orchestrator/issue_classifier.py`

검증 결과의 이슈를 Critical / Non-critical로 분류한다.

### 생성자

```python
IssueClassifier(model: str = "claude-sonnet-4-6")
```

### 메서드

#### `classify(verification: dict) -> list[dict]`

검증 결과에서 이슈를 추출하고 분류한다.

**반환값:**
```python
[
    {
        "description": "이슈 설명",
        "level": "critical" | "non_critical",
        "suggestion": "제안사항 (선택)"
    }
]
```

**Critical 조건:**
- 스펙 모호 (구현 방향 결정 불가)
- 외부 서비스 연동 정보 필요
- 스펙 간 모순
- 보안 아키텍처 결정 필요

**Non-critical 조건:**
- UI 세부 조정
- 네이밍 선택
- 성능 최적화 방향

> 빌드/테스트/린트/타입 에러는 분류 대상 아님 — 에이전트가 직접 해결

---

## SpecBuilder

**파일**: `src/orchestrator/spec_builder.py`

Claude와 대화하며 프로젝트 스펙을 확정한다.

### 생성자

```python
SpecBuilder(
    event_bus: EventBus,
    model: str = "claude-sonnet-4-6",
)
```

### 메서드

#### `build(project_path: Path) -> str`

대화를 통해 스펙을 확정하고 `spec.md`로 저장한다.

- `spec.md`가 이미 존재하면 그대로 반환
- Claude가 `SPEC_CONFIRMED` 태그를 출력하면 스펙 확정
- 확정된 스펙은 `{project_path}/spec.md`에 저장

```python
builder = SpecBuilder(event_bus)
spec = await builder.build(Path("/path/to/project"))
```

---

## TokenManager

**파일**: `src/orchestrator/token_manager.py`

API rate limit 초과 시 지수 백오프로 대기한다.

### 생성자

```python
TokenManager(wait_seconds: int = 60)
```

### 메서드

#### `wait_if_needed() -> None`
rate limit 직후라면 쿨다운 대기.

#### `wait_for_reset() -> None`
토큰 한도 초과 시 리셋될 때까지 대기. 지수 백오프: 60s → 120s → 240s → 최대 300s.

#### `record_usage(input_tokens: int, output_tokens: int) -> None`
토큰 사용량 기록.

#### `get_usage_summary() -> dict`
```python
{
    "input_tokens": int,
    "output_tokens": int,
    "total_tokens": int,
    "consecutive_limits": int,
}
```
