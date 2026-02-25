# 개발 환경 설정 가이드

이 문서는 autonomous-dev-agent 프로젝트의 개발 환경을 설정하는 방법을 설명합니다.

## 목차

1. [사전 요구사항](#사전-요구사항)
2. [저장소 클론](#저장소-클론)
3. [의존성 설치](#의존성-설치)
4. [환경 변수 설정](#환경-변수-설정)
5. [개발 명령어](#개발-명령어)
6. [프로젝트 구조 이해](#프로젝트-구조-이해)

---

## 사전 요구사항

### Python 3.12 이상

`pyproject.toml`의 `requires-python = ">=3.12"` 조건을 만족해야 합니다.

Python 버전 확인:

```bash
python --version
# Python 3.12.x 이상이어야 합니다
```

Python 3.12가 없으면 [python.org](https://www.python.org/downloads/) 또는 [pyenv](https://github.com/pyenv/pyenv)로 설치합니다.

```bash
# pyenv 사용 시
pyenv install 3.12
pyenv local 3.12
```

### uv 패키지 매니저

이 프로젝트는 [uv](https://docs.astral.sh/uv/)를 사용합니다.

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# 설치 확인
uv --version
```

### Claude 인증

Claude API를 사용하는 두 가지 방법 중 하나를 선택합니다.

**방법 1: Anthropic API 키 사용**

[Anthropic Console](https://console.anthropic.com/)에서 API 키를 발급합니다.

**방법 2: Claude Code 세션 사용**

`ANTHROPIC_API_KEY` 없이 `claude` CLI로 인증된 세션을 사용합니다. Claude Code가 설치되어 있고 `claude` 명령으로 인증된 상태여야 합니다.

`src/utils/claude_client.py`의 `call_claude_for_text` 함수는 `ANTHROPIC_API_KEY` 환경변수 존재 여부로 자동으로 방법을 선택합니다.

---

## 저장소 클론

```bash
git clone <repo-url>
cd autonomous-dev-agent
```

---

## 빠른 설치 (권장)

**원클릭 설치 스크립트 사용:**

```bash
./scripts/install.sh
```

이 스크립트는 다음을 자동으로 수행합니다:
1. Python 3.12 이상 확인
2. uv 패키지 매니저 설치
3. 가상환경 생성
4. 의존성 설치
5. .env 파일 생성
6. Claude Code 확인 (선택)
7. 설치 검증 및 테스트 실행

**또는 수동 설치:**

```bash
uv sync
```

이 명령으로 `pyproject.toml`의 `dependencies`와 `dev` 그룹이 함께 설치됩니다.

```toml
# pyproject.toml 기준 주요 의존성
dependencies = [
    "anthropic>=0.40.0",
    "claude-agent-sdk>=0.1.0",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "pyyaml>=6.0",
    "textual>=0.80.0",
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "websockets>=13.0",
    "python-multipart>=0.0.12",
]
```

RAG 벡터 검색 기능(chromadb, sentence-transformers)을 함께 설치하려면:

```bash
uv sync --extra rag
```

`rag` 옵션 없이 설치하면 `CodebaseIndexer`는 텍스트 기반 검색만 사용합니다.

---

## 환경 변수 설정

`.env.example`을 복사하여 `.env`를 만듭니다.

```bash
cp .env.example .env
```

`.env` 파일 내용:

```dotenv
# Anthropic API Key (선택 - 없으면 Claude Code 세션 사용)
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Agent Teams 활성화 (.claude/settings.json에도 설정됨)
CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1

# 서브에이전트 모델 (기본값: claude-sonnet-4-6)
CLAUDE_CODE_SUBAGENT_MODEL=claude-sonnet-4-6
```

`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`와 `CLAUDE_CODE_SUBAGENT_MODEL`은 `.claude/settings.json`의 `env` 블록에도 이미 설정되어 있습니다. `.env` 파일 설정은 추가적인 오버라이드가 필요할 때 사용합니다.

---

## 개발 명령어

모든 명령어는 프로젝트 루트에서 실행합니다.

### 테스트 실행

```bash
# 전체 테스트 + 커버리지 요약
uv run pytest tests/ -v --cov

# 커버리지 상세 보고 (미커버 라인 표시)
uv run pytest tests/ -v --cov=src --cov-report=term-missing

# 특정 테스트 파일
uv run pytest tests/test_executor.py -v

# 특정 테스트 함수
uv run pytest tests/test_executor.py::test_classify_task_coder -v
```

TUI 코드(`src/ui/`)는 커버리지 측정에서 제외됩니다. `pyproject.toml`의 `tool.coverage.run.omit`에 `src/ui/*`가 명시되어 있습니다.

### 린트

```bash
uv run ruff check src/
```

린트 오류 자동 수정:

```bash
uv run ruff check --fix src/
```

ruff는 `pyproject.toml`의 아래 설정을 따릅니다.

```toml
[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "SIM", "RUF"]
```

### 타입 체크

```bash
uv run mypy src/
```

mypy는 `pyproject.toml`의 아래 설정을 따릅니다.

```toml
[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = true
```

### TUI 실행 (권장)

**간단한 명령어로 실행:**

```bash
# 기본 실행 (현재 디렉토리, 스펙 대화부터 시작)
adev

# 또는 전체 이름 사용
autonomous-dev

# 프로젝트 경로 지정
adev /path/to/project

# 스펙 파일 있으면 바로 개발 시작
adev /path/to/project spec.md
```

**또는 전체 경로로 실행:**

```bash
# uv run 사용
uv run python -m src.ui.tui

# 프로젝트 경로 지정
uv run python -m src.ui.tui /path/to/project

# 스펙 파일 지정
uv run python -m src.ui.tui /path/to/project spec.md
```

TUI는 두 개의 화면으로 구성됩니다.

- **SpecScreen**: Claude와 대화하며 스펙을 확정합니다. `SPEC_CONFIRMED` 태그가 포함된 응답이 나오면 `spec.md`에 저장하고 DevScreen으로 전환합니다.
- **DevScreen**: 진행 상황 패널(완성도, 테스트율, 린트/타입 에러, 빌드 상태)과 실시간 로그, 크리티컬 이슈 답변 입력란을 표시합니다.

### CLI 실행 (고급)

TUI 없이 Orchestrator만 직접 실행하려면:

```bash
uv run python -m src.orchestrator.main spec.md
```

또는 재시작 루프를 포함한 실행 스크립트 사용:

```bash
./scripts/run.sh spec.md
```

### 전체 품질 검사 (테스트 + 린트 + 타입 체크 순서)

```bash
uv run pytest tests/ -v --cov && uv run ruff check src/ && uv run mypy src/
```

---

## 프로젝트 구조 이해

### Orchestrator 흐름

`src/orchestrator/main.py`의 `AutonomousOrchestrator.run()`이 메인 루프입니다.

```
Phase 1: _phase_setup()       — 프로젝트 초기 구조 생성
Phase 2~5: 반복 루프          — 완성 조건을 만족할 때까지
    1. Planner.decide_next_task()     — 다음 작업 결정 (Claude API)
    2. AgentExecutor.execute()        — 코드 작성/수정 (Claude Agent SDK)
    3. Verifier.verify_all()          — pytest/ruff/mypy/빌드 검증
    4. IssueClassifier.classify()     — 이슈 분류
    5. _handle_issues()               — critical → 즉시 질문, non-critical → 모아두기
    6. _update_state()                — 상태 업데이트 + state.json 저장
Phase 6: _phase_document()    — documenter 에이전트로 문서 생성
Phase 7: _report_completion() — 완성 보고 + 비크리티컬 질문 전달
```

최대 반복 횟수는 `MAX_ITERATIONS = 500`입니다.

### 완성 판단 기준

`_is_complete()`가 아래 조건을 모두 만족하면 루프를 종료합니다.

```python
COMPLETION_CRITERIA = {
    "test_pass_rate": 100.0,
    "lint_errors": 0,
    "type_errors": 0,
    "build_success": True,
}
```

### 완성도 계산

`_update_state()`에서 가중 평균으로 완성도를 계산합니다.

| 항목 | 가중치 |
|------|--------|
| 테스트 통과율 | 40% |
| 린트 에러 없음 | 15% |
| 타입 에러 없음 | 15% |
| 빌드 성공 | 30% |

### AgentExecutor 키워드 분류

`src/agents/executor.py`의 `_classify_task()`는 아래 키워드 맵으로 에이전트를 선택합니다.

| AgentType | 분류 키워드 |
|-----------|------------|
| ARCHITECT | 설계, 구조, 아키텍처, 모듈, api 설계, 데이터 모델, 디렉토리, 인터페이스, 의존성 |
| TESTER | 테스트, 커버리지, pytest, 검증, test, 단위 테스트, 통합 테스트 |
| REVIEWER | 리뷰, 검토, 품질 확인, 코드 검사, 점검, 감사 |
| DOCUMENTER | 문서, readme, api 문서, changelog, 주석, 가이드, 설명서 |
| CODER | 구현, 작성, 코딩, 버그 수정, 리팩토링, 기능 추가, 개발, 수정 |

우선순위: `ARCHITECT > TESTER > REVIEWER > DOCUMENTER > CODER`. 매칭 없으면 CODER가 기본값입니다.

### RAG MCP 서버

`src/rag/mcp_server.py`의 `build_rag_mcp_server()`는 두 개의 MCP 도구를 제공합니다.

- `search_code(query, top_k=5)`: 코드베이스에서 쿼리와 관련된 코드 청크를 반환합니다.
- `reindex_codebase()`: 코드 변경 후 인덱스를 재구축합니다.

`CodebaseIndexer`는 텍스트 기반 토큰 매칭 검색을 기본으로 사용합니다. `.py`, `.ts`, `.js`, `.tsx`, `.jsx`, `.go`, `.java`, `.rs` 확장자를 인덱싱하며, `__pycache__`, `.git`, `node_modules`, `.venv` 디렉토리는 제외합니다.

### 상태 저장

`ProjectState`는 `.claude/state.json`에 저장됩니다. 토큰 한도로 중단되거나 재시작할 때 `load_or_create()`가 이전 상태를 불러옵니다. 스펙의 앞 100자가 일치하면 이전 상태를 이어받습니다.
