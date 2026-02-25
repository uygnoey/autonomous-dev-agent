# Autonomous Development Agent

Claude API로 판단하고 Claude Agent SDK로 실행하는 자율 무한 루프 개발 시스템.

스펙을 입력하면 에이전트가 테스트 100% 통과와 전체 기능 완성까지 스스로 개발합니다. 빌드 실패, 테스트 실패, 린트 오류는 사람에게 묻지 않고 직접 해결합니다. 스펙이 모호하거나 외부 연동 정보가 필요한 경우에만 질문합니다.

**[English README](README_EN.md)**

## 목차

1. [주요 기능](#주요-기능)
2. [기술 스택](#기술-스택)
3. [빠른 시작](#빠른-시작)
4. [실행 방법](#실행-방법)
5. [디렉토리 구조](#디렉토리-구조)
6. [환경 변수](#환경-변수)
7. [테스트 실행](#테스트-실행)
8. [Agent Teams](#agent-teams)
9. [이슈 분류 규칙](#이슈-분류-규칙)

---

## 주요 기능

- **자율 개발 루프**: Planner가 다음 작업을 결정하고, Executor가 코드를 작성하고, Verifier가 pytest + ruff + mypy로 검증하는 사이클을 완성 조건을 만족할 때까지 반복합니다.
- **Textual TUI**: 스펙 확정 대화 화면(SpecScreen)과 실시간 개발 대시보드(DevScreen)로 구성된 터미널 인터페이스를 제공합니다.
- **SpecBuilder**: TUI에서 Claude와 대화하며 프로젝트 스펙을 확정합니다. 확정된 스펙은 `spec.md`로 저장됩니다.
- **AgentExecutor 라우팅**: task_prompt의 키워드를 분석하여 architect, coder, tester, reviewer, documenter 중 적합한 에이전트를 자동으로 선택합니다.
- **RAG MCP 서버**: `search_code` 도구로 코드베이스에서 유사 패턴을 검색하여 에이전트가 일관된 코드를 작성하도록 지원합니다.
- **토큰 한도 자동 대기**: API rate limit 초과 시 지수 백오프로 대기했다가 재시작합니다.
- **상태 영속성**: `.claude/state.json`에 진행 상태를 저장하여 중단 후 재개할 수 있습니다.
- **EventBus**: Orchestrator와 TUI 사이의 비동기 통신을 담당합니다. 이벤트 타입은 `LOG`, `PROGRESS`, `QUESTION`, `SPEC_MESSAGE`, `AGENT_OUTPUT`, `COMPLETED`입니다.

---

## 기술 스택

| 구성 요소 | 라이브러리 / 버전 |
|-----------|-----------------|
| 런타임 | Python 3.12+ |
| Claude 두뇌 | anthropic >= 0.40.0 |
| Claude 실행 계층 | claude-agent-sdk >= 0.1.0 |
| TUI 프레임워크 | textual >= 0.80.0 |
| 데이터 검증 | pydantic >= 2.0, pydantic-settings >= 2.0 |
| 설정 파일 | pyyaml >= 6.0 |
| API 서버 (선택) | fastapi >= 0.115.0, uvicorn >= 0.32.0 |
| 벡터 검색 (선택) | chromadb >= 0.5.0, sentence-transformers >= 3.0 |
| 테스트 | pytest >= 8.0, pytest-asyncio >= 0.24, pytest-cov >= 5.0 |
| 린트 | ruff >= 0.8.0 |
| 타입 체크 | mypy >= 1.13 |

---

## 빠른 시작

### 요구사항

**필수 요구사항 없음!** 🎉

설치 스크립트가 다음을 자동으로 설치합니다:
- Python 3.12 (없을 경우)
- Git (없을 경우)
- uv 패키지 매니저
- Node.js (Claude Code를 위해)
- Claude Code CLI (선택)

### 🚀 완전 자동 설치 (최고 권장)

**아무것도 설치되어 있지 않아도 됩니다!**

```bash
# macOS/Linux에서 원격 설치
curl -fsSL https://raw.githubusercontent.com/USER/REPO/main/scripts/install.sh | bash

# 또는 wget 사용
wget -qO- https://raw.githubusercontent.com/USER/REPO/main/scripts/install.sh | bash
```

**Git이 이미 있다면:**

```bash
git clone <repo-url>
cd autonomous-dev-agent
./scripts/install.sh
```

설치 스크립트가 자동으로:
- ✅ **Git 설치** (없을 경우)
- ✅ **Python 3.12 설치** (없거나 버전이 낮을 경우)
- ✅ **Node.js 설치** (없을 경우)
- ✅ **uv 패키지 매니저 설치**
- ✅ **Claude Code 설치** (선택)
- ✅ 가상환경 생성
- ✅ 의존성 설치
- ✅ .env 파일 생성
- ✅ 설치 검증 및 테스트 실행

### 수동 설치

**1단계: 의존성 설치**

```bash
git clone <repo-url>
cd autonomous-dev-agent
uv sync
```

RAG 벡터 검색 기능도 함께 설치하려면:

```bash
uv sync --extra rag
```

**2단계: 환경 변수 설정**

```bash
cp .env.example .env
```

`.env` 파일을 열어 `ANTHROPIC_API_KEY`를 입력합니다.

```dotenv
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

`ANTHROPIC_API_KEY`가 없으면 Claude Code 세션(claude CLI subscription)을 자동으로 사용합니다.

**3단계: CLI 명령어 설치**

```bash
uv pip install -e .
```

이제 `adev` 또는 `autonomous-dev` 명령어를 사용할 수 있습니다!

### 실행

**간단한 방법 (권장):**

```bash
# TUI 모드 실행 (스펙 대화부터 시작)
adev

# 프로젝트 경로 지정
adev /path/to/project

# 스펙 파일로 바로 시작
adev /path/to/project spec.md
```

**또는 전체 경로:**

```bash
# TUI 모드
uv run python -m src.ui.tui

# CLI 모드 (TUI 없이)
uv run python -m src.orchestrator.main spec.md
```

에이전트가 완성 조건(테스트 100%, 린트 0, 타입 에러 0, 빌드 성공)을 달성할 때까지 자율 반복합니다.

---

## 실행 방법

### TUI 실행 옵션

**간단한 명령어 (권장):**

| 명령어 | 동작 |
|--------|------|
| `adev` | 현재 디렉토리, 스펙 대화부터 |
| `adev /path/to/project` | 지정 경로, 스펙 대화부터 |
| `adev /path/to/project spec.md` | 스펙 파일 있으면 바로 개발 시작 |
| `autonomous-dev` | `adev`와 동일 (전체 이름) |

**전체 경로:**

| 명령어 | 동작 |
|--------|------|
| `uv run python -m src.ui.tui` | 현재 디렉토리, 스펙 대화부터 |
| `uv run python -m src.ui.tui /path/to/project` | 지정 경로, 스펙 대화부터 |
| `uv run python -m src.ui.tui /path/to/project spec.md` | 스펙 파일 있으면 바로 개발 시작 |

### CLI 실행 옵션 (고급)

**TUI 없이 Orchestrator만 직접 실행:**

```bash
uv run python -m src.orchestrator.main <spec_file>
```

**재시작 루프 포함 (토큰 한도 대기 자동):**

```bash
./scripts/run.sh spec.md
```

`spec_file`: 확정된 스펙이 담긴 텍스트 파일 경로.

### 완성 판단 기준

Orchestrator는 아래 조건을 모두 만족할 때 완성으로 판단합니다.

| 항목 | 기준 |
|------|------|
| 테스트 통과율 | 100% |
| 린트 에러 | 0건 |
| 타입 에러 | 0건 |
| 빌드 | 성공 |

---

## 디렉토리 구조

```
autonomous-dev-agent/
├── src/
│   ├── orchestrator/              # 자율 루프 두뇌 (Claude API 사용)
│   │   ├── main.py                # AutonomousOrchestrator, 메인 루프 (최대 500회)
│   │   ├── planner.py             # Planner: 다음 작업 결정
│   │   ├── spec_builder.py        # SpecBuilder: 스펙 확정 대화
│   │   ├── issue_classifier.py    # IssueClassifier: critical/non_critical 분류
│   │   └── token_manager.py       # TokenManager: rate limit 대기 (지수 백오프)
│   ├── agents/                    # Claude Agent SDK 실행 계층
│   │   ├── executor.py            # AgentExecutor: 에이전트 라우팅 + 실행
│   │   └── verifier.py            # Verifier: pytest/ruff/mypy/빌드 검증
│   ├── rag/                       # RAG 코드 검색 시스템
│   │   ├── indexer.py             # CodebaseIndexer: 텍스트 기반 코드 인덱싱
│   │   └── mcp_server.py          # RAG MCP 서버: search_code, reindex_codebase 도구
│   ├── ui/
│   │   └── tui/                   # Textual TUI
│   │       ├── app.py             # AgentApp, SpecScreen, DevScreen
│   │       └── __main__.py        # TUI 진입점
│   └── utils/
│       ├── events.py              # EventBus: Orchestrator-UI 비동기 통신
│       ├── state.py               # ProjectState: 상태 저장/복원 (state.json)
│       ├── claude_client.py       # call_claude_for_text: API/SDK 공통 헬퍼
│       └── logger.py              # setup_logger: 구조화된 로깅
├── tests/                         # 유닛 및 통합 테스트
│   ├── test_executor.py
│   ├── test_verifier.py
│   ├── test_events.py
│   ├── test_state.py
│   ├── test_planner.py
│   ├── test_issue_classifier.py
│   ├── test_token_manager.py
│   ├── test_indexer.py
│   ├── test_mcp_server.py
│   ├── test_main.py
│   ├── test_spec_builder.py
│   └── test_claude_client.py
├── docs/
│   ├── architecture/              # 아키텍처 설계 문서
│   └── setup/                     # 개발 환경 설정 가이드
├── .claude/
│   ├── settings.json              # Agent Teams 활성화, 권한 설정
│   ├── skills/                    # RAG 검색용 코딩 가이드라인 (6종)
│   │   ├── design-patterns/
│   │   ├── code-standards/
│   │   ├── error-handling/
│   │   ├── testing-strategy/
│   │   ├── project-architecture/
│   │   └── rag-search/
│   └── agents/                    # 서브에이전트 역할 정의 (5종)
├── pyproject.toml
├── .env.example
└── spec.md                        # 개발할 프로젝트 스펙 (사용자 작성)
```

---

## 환경 변수

| 변수명 | 필수 여부 | 설명 |
|--------|-----------|------|
| `ANTHROPIC_API_KEY` | 선택 | Anthropic API 키. 없으면 Claude Code 세션을 사용합니다. |
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | 선택 | `1`로 설정하면 Agent Teams 기능을 활성화합니다. `settings.json`에 이미 설정되어 있습니다. |
| `CLAUDE_CODE_SUBAGENT_MODEL` | 선택 | 서브에이전트 모델 ID. 기본값은 `claude-sonnet-4-6`입니다. |

`.env.example`을 복사하여 `.env`를 만들고 값을 채웁니다.

```bash
cp .env.example .env
```

---

## 테스트 실행

```bash
# 전체 테스트 + 커버리지
uv run pytest tests/ -v --cov

# 커버리지 상세 보고
uv run pytest tests/ -v --cov=src --cov-report=term-missing

# 특정 모듈 테스트
uv run pytest tests/test_executor.py -v
```

TUI 코드(`src/ui/`)는 Textual 앱 구동이 필요하므로 자동화 테스트 대상에서 제외됩니다(`pyproject.toml`의 `tool.coverage.run.omit` 참조).

---

## Agent Teams

### 활성화 방법

Agent Teams는 **자동으로 활성화**됩니다:

1. **설치 시 자동 설정**: `install.sh`가 `.env` 파일에 필수 환경 변수를 자동으로 추가합니다
2. **자동 로딩**: CLI 실행 시 `.env` 파일이 자동으로 로드됩니다 (python-dotenv 사용)
3. **다중 설정**: `.env` 파일과 `.claude/settings.json` 모두에 Agent Teams 설정이 포함됩니다

**확인 방법:**

```bash
# CLI 실행 시 로그 확인
adev

# 출력 예시:
# ✅ Agent Teams 활성화됨
#    서브에이전트 모델: claude-sonnet-4-6
```

### 환경 변수

`.env` 파일에 다음 환경 변수가 설정됩니다:

```dotenv
# Agent Teams 활성화
CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1

# 서브에이전트 모델 (비용 절감)
CLAUDE_CODE_SUBAGENT_MODEL=claude-sonnet-4-6
```

### 에이전트 라우팅

`AgentExecutor`는 task_prompt의 키워드를 분석하여 아래 다섯 개 에이전트 중 하나를 자동으로 선택합니다.

| 에이전트 | 역할 | 모델 | 허용 도구 |
|----------|------|------|-----------|
| **architect** | 디렉토리 구조, 모듈 분리, API 인터페이스, 데이터 모델 설계 | claude-opus-4-6 | Read, Glob, Grep, Write, Bash(find/ls) |
| **coder** | 기능 구현, 버그 수정, 리팩토링 | claude-sonnet-4-6 | Read, Write, Edit, Bash, Glob, Grep |
| **tester** | 테스트 작성, pytest 실행, 커버리지 확인 | claude-sonnet-4-6 | Read, Write, Edit, Bash, Glob, Grep |
| **reviewer** | 코드 품질 검토, 디자인 패턴 준수 확인 (수정 불가) | claude-sonnet-4-6 | Read, Glob, Grep, Bash(ruff/mypy/pytest) |
| **documenter** | README, API 문서, 아키텍처 문서, CHANGELOG 작성 | claude-sonnet-4-6 | Read, Write, Edit, Glob, Grep |

분류 우선순위: `architect > tester > reviewer > documenter > coder`. 어떤 키워드도 매칭되지 않으면 `coder`가 기본값입니다.

---

## 이슈 분류 규칙

`IssueClassifier`는 검증 결과의 이슈를 두 가지로 분류합니다.

| 분류 | 해당 항목 | 처리 방식 |
|------|-----------|-----------|
| **Critical** | 스펙 모호, 외부 API 키 필요, 스펙 간 모순, 보안 아키텍처 결정 | TUI/터미널로 즉시 사람에게 질문 |
| **Non-Critical** | UI 세부 조정, 네이밍, 성능 최적화 방향, 부가 기능 구현 방식 | 완성 후 모아서 전달 |

빌드 실패, 테스트 실패, 린트 오류, 타입 오류는 모두 에이전트가 직접 해결합니다. 사람에게 묻지 않습니다.

---

## 라이선스

MIT
