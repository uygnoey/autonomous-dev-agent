# Agents API

Claude Agent SDK 실행 계층 API 문서.

---

## AgentExecutor

**파일**: `src/agents/executor.py`

task_prompt를 분석하여 적합한 에이전트를 자동으로 선택하고 실행한다.

### 생성자

```python
AgentExecutor(
    project_path: str,
    max_turns: int = 100,
    use_rag: bool = True,
)
```

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `project_path` | `str` | — | 대상 프로젝트 경로 |
| `max_turns` | `int` | `100` | 에이전트 최대 실행 턴 수 |
| `use_rag` | `bool` | `True` | RAG MCP 서버 활성화 여부 |

### 에이전트 유형 (AgentType)

| 값 | 역할 | 모델 | 트리거 키워드 |
|----|------|------|--------------|
| `architect` | 설계·구조·아키텍처 결정 | claude-opus-4-6 | 설계, 구조, 아키텍처, 모듈, api 설계, 데이터 모델, 디렉토리, 인터페이스, 의존성 |
| `coder` | 기능 구현·버그 수정·리팩토링 | claude-sonnet-4-6 | 구현, 작성, 코딩, 버그 수정, 리팩토링, 기능 추가, 개발, 수정 |
| `tester` | 테스트 작성·실행·커버리지 | claude-sonnet-4-6 | 테스트, 커버리지, pytest, 검증, test, 단위 테스트, 통합 테스트 |
| `reviewer` | 코드 리뷰·품질 검증 (수정 불가) | claude-sonnet-4-6 | 리뷰, 검토, 품질 확인, 코드 검사, 점검, 감사 |
| `documenter` | README·API 문서·CHANGELOG 작성 | claude-sonnet-4-6 | 문서, readme, api 문서, changelog, 주석, 가이드, 설명서 |

**우선순위**: `architect > tester > reviewer > documenter > coder`

### 메서드

#### `execute(task_prompt, agent_type=None) -> list[Message | dict]`

작업을 실행하고 결과를 반환한다.

```python
executor = AgentExecutor(project_path="/path/to/project")

# 자동 분류 (task_prompt 키워드로 에이전트 선택)
results = await executor.execute("UserDTO 클래스를 구현하세요")
# → AgentType.CODER 선택됨

# 명시적 지정
results = await executor.execute("테스트 커버리지를 확인하세요", agent_type=AgentType.TESTER)
```

**반환값**: Agent SDK 메시지 리스트. 에러 발생 시 `{"error": "..."}` dict 포함.

#### `execute_with_retry(task_prompt, max_retries=3, agent_type=None) -> list[Message | dict]`

실패 시 최대 `max_retries`회 재시도하며 실행한다.

---

## Verifier

**파일**: `src/agents/verifier.py`

pytest, ruff, mypy, 빌드를 순차 실행하고 결과를 구조화하여 반환한다.

### 생성자

```python
Verifier(project_path: str)
```

### 메서드

#### `verify_all() -> dict`

모든 검증을 수행하고 결과를 반환한다.

```python
verifier = Verifier(project_path="/path/to/project")
result = await verifier.verify_all()
```

**반환값:**
```python
{
    "tests_total": int,      # 전체 테스트 수
    "tests_passed": int,     # 통과한 테스트 수
    "tests_failed": int,     # 실패한 테스트 수
    "lint_errors": int,      # ruff 에러 수
    "type_errors": int,      # mypy 에러 수
    "build_success": bool,   # 빌드 성공 여부
    "issues": list[str],     # 이슈 설명 목록
}
```

**실행 명령:**
1. `pytest tests/ -v --tb=short`
2. `ruff check src/`
3. `mypy src/ --ignore-missing-imports`
4. `python -c "import src"`
