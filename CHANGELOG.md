# CHANGELOG

Autonomous Dev Agent의 버전별 변경 이력.

이 프로젝트는 [Conventional Commits](https://www.conventionalcommits.org/) 규칙을 따릅니다.

---

## [0.2.0] - 2025-02-25

### 추가
- **원클릭 설치 스크립트** (`scripts/install.sh`): Python 버전 확인, uv 설치, 가상환경 생성, 의존성 설치, .env 생성, 설치 검증을 7단계로 자동화
- **`adev` CLI 명령어** (`src/cli.py`): `uv run python -m src.ui.tui` 대신 `adev` 명령어로 간단 실행
- **Agent Teams 사용 가이드** (`docs/architecture/agent-teams-usage.md`): Claude Code Agent Teams 설정 방법 문서
- **전체 API 문서** (`docs/api/`): Orchestrator, Agents, RAG, Utils 모듈 API 레퍼런스
- **아키텍처 문서** (`docs/architecture/overview.md`, `data-model.md`, `design-decisions.md`): 시스템 구조, 데이터 모델, 설계 결정 이유
- **배포 가이드** (`docs/setup/deployment.md`): 로컬, SSH 서버, Docker, systemd 배포 방법

### 변경
- 모델 ID 정규화: `claude-sonnet-4-6-20260217` → `claude-sonnet-4-6` (Planner, IssueClassifier, ClaudeClient, .env.example)
- README 개선: 원클릭 설치 및 `adev` 명령어 안내 추가, `uv run` 접두사 명시

### 수정
- `src/cli.py` 타입 에러 수정: `from src.ui.tui import main` → `from src.ui.tui.app import run_tui` (직접 import)
- `src/cli.py` 린트 에러 수정: `cli_main()` 내부 import 정렬

---

## [0.1.0] - 2025-02-24

### 추가
- **AgentExecutor 라우팅** (`src/agents/executor.py`): task_prompt 키워드 분석으로 architect/coder/tester/reviewer/documenter 자동 선택. 우선순위: `architect > tester > reviewer > documenter > coder`
- **5종 에이전트 프로필**: 각 에이전트별 전용 시스템 프롬프트, 모델, 허용 도구 정의
- **`execute_with_retry()`**: 실패 시 최대 3회 재시도 + 에러 컨텍스트 포함 재시도 프롬프트
- **TUI 인터페이스** (`src/ui/tui/`): SpecScreen(스펙 확정 대화) + DevScreen(개발 대시보드)
- **EventBus** (`src/utils/events.py`): Orchestrator-TUI 비동기 통신. 6가지 이벤트 타입
- **SpecBuilder** (`src/orchestrator/spec_builder.py`): Claude와 대화하며 spec.md 생성
- **RAG MCP 서버** (`src/rag/mcp_server.py`): `search_code`, `reindex_codebase` 도구 제공
- **CodebaseIndexer** (`src/rag/indexer.py`): 텍스트 기반 코드 인덱싱 및 TF 점수 랭킹
- **테스트 커버리지 100%** (178개 테스트 통과)

---

## [0.0.2] - 2025-02-23

### 추가
- **Claude subscription 지원**: `ANTHROPIC_API_KEY` 없을 때 Claude Code 세션 자동 사용 (`call_claude_for_text` SDK 폴백)
- 테스트 커버리지 91% → 이후 100% 달성

### 수정
- ruff 린트 에러 전체 수정
- mypy 타입 에러 전체 수정

---

## [0.0.1] - 2025-02-22

### 추가
- **프로젝트 초기 구성**: `pyproject.toml`, `.env.example`, 디렉토리 구조
- **AutonomousOrchestrator** (`src/orchestrator/main.py`): 자율 루프 (최대 500회), 크리티컬 이슈 처리, 자가 복구
- **Planner** (`src/orchestrator/planner.py`): 현재 상태 기반 다음 작업 결정
- **IssueClassifier** (`src/orchestrator/issue_classifier.py`): Critical/Non-critical 분류
- **TokenManager** (`src/orchestrator/token_manager.py`): 지수 백오프 rate limit 대기
- **Verifier** (`src/agents/verifier.py`): pytest + ruff + mypy + 빌드 검증
- **ProjectState** (`src/utils/state.py`): JSON 영속화, 재시작 이어받기
- **재시작 스크립트** (`scripts/run.sh`): 최대 50회 자동 재시작
