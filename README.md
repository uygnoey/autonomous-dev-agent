# Autonomous Development Agent

Claude API로 판단하고 Claude Agent SDK로 실행하는 자율 무한 루프 개발 시스템.

스펙을 입력하면 에이전트가 테스트 100% 통과와 전체 기능 완성까지 스스로 개발합니다. 빌드 실패, 테스트 실패, 린트 오류는 사람에게 묻지 않고 직접 해결합니다. 스펙이 모호하거나 외부 연동 정보가 필요한 경우에만 질문합니다.

**[English README](README_EN.md)**

## 목차

1. [Phase 1 완성 사항](#phase-1-완성-사항)
2. [주요 기능](#주요-기능)
3. [기술 스택](#기술-스택)
4. [빠른 시작](#빠른-시작)
5. [실행 방법](#실행-방법)
6. [디렉토리 구조](#디렉토리-구조)
7. [환경 변수](#환경-변수)
8. [테스트 실행](#테스트-실행)
9. [Agent Teams](#agent-teams)
10. [이슈 분류 규칙](#이슈-분류-규칙)

---

## Phase 1 완성 사항

**RAG 시스템 전면 재설계** - 2026-02-26 완료

| 항목 | 이전 | Phase 1 이후 |
|------|------|-------------|
| 청킹 방식 | 50줄 고정 슬라이싱 | AST 경계 기반 (함수·클래스·메서드·모듈 단위) |
| 검색 알고리즘 | Boolean BoW (0/1) | BM25 TF-IDF + 벡터 코사인 유사도 하이브리드 |
| 인덱싱 전략 | 매번 전체 재인덱싱 O(n) | mtime 기반 증분 인덱싱 O(변경분) |
| MCP 도구 수 | 2개 | 5개 |
| 벡터 검색 | 없음 | Voyage AI 임베딩 + NumpyStore/LanceDBStore |

### 7개 모듈 구현 완료

| 모듈 | 파일 | 상태 |
|------|------|------|
| ASTChunker | `src/rag/chunker.py` | 완료 |
| BM25Scorer | `src/rag/scorer.py` | 완료 |
| AnthropicEmbedder | `src/rag/embedder.py` | 완료 |
| VectorStore | `src/rag/vector_store.py` | 완료 |
| HybridSearcher | `src/rag/hybrid_search.py` | 완료 |
| IncrementalIndexer | `src/rag/incremental_indexer.py` | 완료 |
| MCP Server | `src/rag/mcp_server.py` | 완료 |

### 테스트 결과

| 구분 | 테스트 수 | 결과 |
|------|-----------|------|
| 단위 테스트 | 306개 | 100% 통과 |
| 모듈 QC 테스트 | 70,000개 | 100% 통과 |
| E2E 통합 테스트 | 35개 | 100% 통과 |
| **합계** | **70,341개** | **100% 통과** |

---

## 주요 기능

- **자율 개발 루프**: Planner가 다음 작업을 결정하고, Executor가 코드를 작성하고, Verifier가 pytest + ruff + mypy로 검증하는 사이클을 완성 조건을 만족할 때까지 반복합니다.
- **AST 기반 청킹**: Python 파일을 함수·클래스·메서드 경계로 분할하여 의미 단위 컨텍스트를 보존합니다. 비Python 파일은 50줄 오버랩 폴백을 사용합니다.
- **BM25 렉시컬 검색**: rank-bm25 라이브러리 기반 IDF 가중치 스코어링. camelCase, snake_case 코드 특화 토큰화를 포함합니다.
- **벡터 시맨틱 검색**: Voyage AI (voyage-3 모델) 임베딩과 코사인 유사도 검색. SHA256 캐시로 중복 API 호출을 방지합니다.
- **하이브리드 검색**: BM25(0.6)와 벡터(0.4) 결과를 min-max 정규화 후 가중 합산합니다. 벡터 검색 불가 시 BM25-only 모드로 자동 전환합니다.
- **증분 인덱싱**: mtime 기반으로 변경 파일만 재인덱싱하여 대형 프로젝트의 인덱싱 지연을 최소화합니다.
- **5종 MCP 도구**: search_code, reindex_codebase, search_by_symbol, get_file_structure, get_similar_patterns를 에이전트에 제공합니다.
- **Textual TUI**: 스펙 확정 대화 화면(SpecScreen)과 실시간 개발 대시보드(DevScreen)로 구성된 터미널 인터페이스를 제공합니다.
- **토큰 한도 자동 대기**: API rate limit 초과 시 지수 백오프로 대기했다가 재시작합니다.
- **상태 영속성**: `.claude/state.json`에 진행 상태를 저장하여 중단 후 재개할 수 있습니다.

---

## 기술 스택

| 구성 요소 | 라이브러리 / 버전 |
|-----------|-----------------|
| 런타임 | Python 3.12+ |
| Claude 두뇌 | anthropic >= 0.40.0 |
| Claude 실행 계층 | claude-agent-sdk >= 0.1.0 |
| TUI 프레임워크 | textual >= 0.80.0 |
| BM25 검색 | rank-bm25 >= 0.2.2 |
| 벡터 연산 | numpy >= 1.26.0 |
| 벡터 DB (선택) | lancedb >= 0.6.0 |
| 임베딩 API | Voyage AI (voyage-3) via httpx |
| 데이터 검증 | pydantic >= 2.0, pydantic-settings >= 2.0 |
| 설정 파일 | pyyaml >= 6.0 |
| 테스트 | pytest >= 8.0, pytest-asyncio >= 0.24, pytest-cov >= 5.0 |
| 린트 | ruff >= 0.8.0 |
| 타입 체크 | mypy >= 1.13 |

---

## 빠른 시작

### 요구사항

**필수 요구사항 없음!**

설치 스크립트가 다음을 자동으로 설치합니다:
- Python 3.12 (없을 경우)
- Git (없을 경우)
- uv 패키지 매니저
- Node.js (Claude Code를 위해)
- Claude Code CLI (선택)

### 완전 자동 설치 (권장)

```bash
# macOS/Linux 원클릭 설치
curl -fsSL https://raw.githubusercontent.com/uygnoey/autonomous-dev-agent/main/scripts/install.sh | bash
```

**Git이 이미 있다면:**

```bash
git clone https://github.com/uygnoey/autonomous-dev-agent.git
cd autonomous-dev-agent
./scripts/install.sh
```

설치 스크립트가 자동으로:
- Git, Python 3.12, Node.js, uv 설치 (없을 경우)
- Claude Code 설치 (선택)
- 가상환경 생성 + 의존성 설치
- **adev CLI 전역 등록** (어디서든 `adev` 실행 가능)
- .env 파일 생성
- **인증 설정** (아래 3가지 옵션 중 선택)
- 설치 검증 및 테스트 실행

**인증 설정 옵션 (설치 중 자동 안내):**

| 옵션 | 설명 |
|------|------|
| **1. API 키 직접 입력** | 설치 중 프롬프트가 표시되면 Anthropic API 키를 입력합니다. 입력한 키는 `.env` 파일에 자동으로 저장됩니다. |
| **2. Claude 구독 로그인** | 브라우저가 열리면 Claude 계정으로 로그인합니다. API 키 없이 Claude 구독으로 인증합니다. |
| **3. 나중에 설정** | 인증을 건너뜁니다. 실행 전 `.env` 파일에 `ANTHROPIC_API_KEY`를 직접 입력해야 합니다. |

### 수동 설치

**1단계: 의존성 설치**

```bash
git clone https://github.com/uygnoey/autonomous-dev-agent.git
cd autonomous-dev-agent
uv sync
```

RAG 벡터 DB(LanceDB) 기능도 함께 설치하려면:

```bash
uv sync --extra rag
```

**2단계: 환경 변수 설정**

```bash
cp .env.example .env
```

`.env` 파일을 열어 필요한 키를 입력합니다:

```dotenv
# 필수: Anthropic API 키 (없으면 Claude Code 세션 자동 사용)
ANTHROPIC_API_KEY=sk-ant-your-key-here

# 선택: Voyage AI 임베딩 키 (없으면 BM25-only 모드로 동작)
VOYAGE_API_KEY=pa-your-voyage-key-here
```

**3단계: CLI 명령어 설치**

```bash
uv pip install -e .
```

이제 `adev` 또는 `autonomous-dev` 명령어를 사용할 수 있습니다.

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
│   ├── rag/                       # RAG 코드 검색 시스템 (Phase 1 완성)
│   │   ├── chunker.py             # ASTChunker: AST 기반 의미 단위 청킹
│   │   ├── scorer.py              # BM25Scorer: IDF 가중치 렉시컬 스코어링
│   │   ├── embedder.py            # AnthropicEmbedder: Voyage AI 임베딩 + 캐시
│   │   ├── vector_store.py        # VectorStore: 코사인 유사도 검색 (NumpyStore/LanceDBStore)
│   │   ├── hybrid_search.py       # HybridSearcher: BM25 + 벡터 가중 결합
│   │   ├── incremental_indexer.py # IncrementalIndexer: mtime 기반 증분 인덱싱 + 싱글톤
│   │   ├── mcp_server.py          # RAG MCP 서버: 5종 도구 제공
│   │   └── indexer.py             # CodebaseIndexer: 레거시 (하위 호환용)
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
│   ├── test_chunker.py            # ASTChunker 단위 테스트
│   ├── test_scorer.py             # BM25Scorer 단위 테스트
│   ├── test_embedder.py           # AnthropicEmbedder 단위 테스트
│   ├── test_vector_store.py       # VectorStore 단위 테스트
│   ├── test_hybrid_search.py      # HybridSearcher 단위 테스트
│   ├── test_incremental_indexer.py # IncrementalIndexer 단위 테스트
│   ├── test_mcp_server.py         # MCP 서버 단위 테스트
│   └── ...                        # 기타 모듈 테스트
├── docs/
│   ├── api/                       # API 레퍼런스 문서
│   │   ├── README.md              # API 문서 인덱스
│   │   └── modules/               # 모듈별 상세 API
│   ├── architecture/              # 아키텍처 설계 문서
│   │   ├── overview.md            # 시스템 전체 아키텍처
│   │   └── design-decisions.md    # 설계 결정 근거
│   ├── setup/                     # 개발 환경 설정 가이드
│   │   └── development.md         # 개발 환경 설정
│   └── phase1/                    # Phase 1 설계 문서
│       └── architecture.md        # Phase 1 RAG 아키텍처 설계
├── .claude/
│   ├── settings.json              # Agent Teams 활성화, 권한 설정
│   ├── skills/                    # RAG 검색용 코딩 가이드라인 (6종)
│   └── agents/                    # 서브에이전트 역할 정의 (5종)
├── config/
│   └── default.yaml               # 기본 설정값
├── pyproject.toml
├── .env.example
└── spec.md                        # 개발할 프로젝트 스펙 (사용자 작성)
```

---

## 환경 변수

| 변수명 | 필수 여부 | 설명 |
|--------|-----------|------|
| `ANTHROPIC_API_KEY` | 선택 | Anthropic API 키. 없으면 Claude Code 세션을 사용합니다. |
| `VOYAGE_API_KEY` | 선택 | Voyage AI 임베딩 API 키. 없으면 BM25-only 모드로 동작합니다. |
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

# RAG 모듈 테스트만
uv run pytest tests/test_chunker.py tests/test_scorer.py tests/test_embedder.py \
    tests/test_vector_store.py tests/test_hybrid_search.py \
    tests/test_incremental_indexer.py tests/test_mcp_server.py -v

# 특정 모듈 테스트
uv run pytest tests/test_chunker.py -v

# 린트
uv run ruff check src/

# 타입 체크
uv run mypy src/
```

### QC/QA 대용량 테스트 파일 생성

대용량 테스트 케이스 파일(~5.5GB)은 Git에 포함되지 않습니다. 아래 스크립트로 생성하세요:

```bash
# QC 전체 모듈 테스트 케이스 생성 (70,000건)
python tests/qc/generate_module_cases.py

# QA E2E 테스트 케이스 생성 (100,000건)
python tests/qa/generate_e2e_cases.py

# 개별 모듈별 생성도 가능
python tests/qc/generate_vector_store_cases.py
python tests/qc/generate_hybrid_search_cases.py
# ... (나머지 모듈)
```

생성되는 파일:
- `tests/qc/*/test_cases.jsonl`: 각 모듈 입력 케이스 (10,000건)
- `tests/qc/*/results.jsonl`: QC 실행 결과
- `tests/qa/test_cases.jsonl`: E2E 통합 테스트 (100,000건)
- `tests/qa/results.jsonl`: QA 실행 결과

TUI 코드(`src/ui/`)는 Textual 앱 구동이 필요하므로 자동화 테스트 대상에서 제외됩니다(`pyproject.toml`의 `tool.coverage.run.omit` 참조).

---

## Agent Teams

### 활성화 방법

Agent Teams는 **자동으로 활성화**됩니다:

1. **설치 시 자동 설정**: `install.sh`가 `.env` 파일에 필수 환경 변수를 자동으로 추가합니다
2. **자동 로딩**: CLI 실행 시 `.env` 파일이 자동으로 로드됩니다 (python-dotenv 사용)
3. **다중 설정**: `.env` 파일과 `.claude/settings.json` 모두에 Agent Teams 설정이 포함됩니다

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
