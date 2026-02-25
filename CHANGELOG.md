# Changelog

이 파일은 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) 형식을 따릅니다.

## [0.1.0] - 2026-02-25

### Added

#### 핵심 자율 루프

- `AutonomousOrchestrator` (`src/orchestrator/main.py`): Claude API로 판단하고 Claude Agent SDK로 실행하는 자율 무한 루프 개발 시스템. 최대 500회 반복, 완성 조건(테스트 100%, 린트 0, 타입 에러 0, 빌드 성공) 달성 시 종료.
- `Planner` (`src/orchestrator/planner.py`): 현재 `ProjectState`를 기반으로 Claude API에게 다음 작업 프롬프트를 요청합니다. 기본 모델은 `claude-sonnet-4-6`.
- `IssueClassifier` (`src/orchestrator/issue_classifier.py`): 검증 결과의 이슈를 `critical` / `non_critical`로 분류합니다. 기술적 이슈(빌드/테스트/린트/타입)는 분류 없이 에이전트가 직접 해결합니다.
- `TokenManager` (`src/orchestrator/token_manager.py`): API rate limit 초과 시 지수 백오프(60초 → 120초 → 240초 → 최대 300초)로 대기 후 재시도합니다.

#### 스펙 확정

- `SpecBuilder` (`src/orchestrator/spec_builder.py`): TUI에서 Claude와 대화하며 프로젝트 스펙을 확정합니다. `SPEC_CONFIRMED` 태그가 포함된 응답이 나오면 `spec.md`로 저장합니다.

#### Agent SDK 실행 계층

- `AgentExecutor` (`src/agents/executor.py`): task_prompt의 키워드를 분석하여 5개 에이전트(architect, coder, tester, reviewer, documenter) 중 하나를 자동으로 선택합니다. `agent_type` 파라미터로 명시적 선택도 가능합니다. `execute_with_retry()`로 최대 3회 재시도를 지원합니다.
- `AgentType` enum (`src/agents/executor.py`): `ARCHITECT`, `CODER`, `TESTER`, `REVIEWER`, `DOCUMENTER` 5개 에이전트 유형. 분류 우선순위: `ARCHITECT > TESTER > REVIEWER > DOCUMENTER > CODER`.
- `AgentProfile` dataclass (`src/agents/executor.py`): 에이전트별 model, system_prompt, allowed_tools를 불변 객체로 정의합니다. ARCHITECT는 `claude-opus-4-6`, 나머지는 `claude-sonnet-4-6` 사용.
- `Verifier` (`src/agents/verifier.py`): Claude Agent SDK로 pytest, ruff, mypy, 빌드를 실행하고 결과를 구조화된 dict로 반환합니다.

#### RAG 코드 검색 시스템

- `CodebaseIndexer` (`src/rag/indexer.py`): `.py`, `.ts`, `.js`, `.tsx`, `.jsx`, `.go`, `.java`, `.rs` 파일을 50줄 단위 청크로 인덱싱합니다. 텍스트 토큰 매칭 기반 검색(`search()`)을 제공합니다.
- RAG MCP 서버 (`src/rag/mcp_server.py`): `build_rag_mcp_server()`로 인-프로세스 MCP 서버를 생성합니다. `search_code(query, top_k=5)`, `reindex_codebase()` 두 개의 도구를 제공합니다. AgentExecutor가 `mcp_servers`에 주입합니다.

#### Textual TUI

- `AgentApp` (`src/ui/tui/app.py`): Textual 기반 TUI 앱. 시작 시 spec_path 존재 여부에 따라 SpecScreen 또는 DevScreen으로 진입합니다.
- `SpecScreen` (`src/ui/tui/app.py`): Claude와의 스펙 확정 대화 화면. 스펙 확정 후 DevScreen으로 자동 전환합니다.
- `DevScreen` (`src/ui/tui/app.py`): 개발 진행 대시보드. 좌측에 StatusPanel(완성도/테스트율 프로그레스바, 린트/타입 에러 수, 빌드 상태)과 RichLog(실시간 로그), 우측에 크리티컬 이슈 답변 입력란을 표시합니다.
- TUI 진입점 (`src/ui/tui/__main__.py`): `python -m src.ui.tui [project_path] [spec_file]`로 실행합니다.

#### 이벤트 버스

- `EventBus` (`src/utils/events.py`): asyncio.Queue 기반 Orchestrator-UI 비동기 통신. 여러 구독자를 지원하며 사용자 답변은 별도 채널(`_answer_queue`)로 처리합니다.
- `EventType` enum (`src/utils/events.py`): `LOG`, `PROGRESS`, `QUESTION`, `SPEC_MESSAGE`, `AGENT_OUTPUT`, `COMPLETED` 6개 이벤트 타입.

#### 상태 관리

- `ProjectState` dataclass (`src/utils/state.py`): 프로젝트 상태를 추적합니다. `save()`로 `.claude/state.json`에 저장하고, `load_or_create()`로 재시작 시 이전 상태를 복원합니다.
- `PhaseType` enum (`src/utils/state.py`): `INIT`, `SETUP`, `BUILD`, `VERIFY`, `DOCUMENT`, `COMPLETE` 6개 단계.

#### 유틸리티

- `call_claude_for_text()` (`src/utils/claude_client.py`): `ANTHROPIC_API_KEY` 존재 시 Anthropic API 직접 호출, 없으면 Claude Code 세션(claude SDK)을 사용합니다.
- `setup_logger()` (`src/utils/logger.py`): `[YYYY-MM-DD HH:MM:SS] LEVEL name: message` 형식의 stdout 로거를 생성합니다.

#### 설정 및 권한

- `.claude/settings.json`: Agent Teams 활성화(`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`), 허용/거부 도구 권한 설정.
- `.claude/skills/`: design-patterns, code-standards, error-handling, testing-strategy, project-architecture, rag-search 6개 코딩 가이드라인 스킬 문서.

#### 테스트

- `tests/` 디렉토리에 13개 테스트 파일 작성: `test_executor.py`, `test_verifier.py`, `test_events.py`, `test_state.py`, `test_planner.py`, `test_issue_classifier.py`, `test_token_manager.py`, `test_indexer.py`, `test_mcp_server.py`, `test_main.py`, `test_spec_builder.py`, `test_claude_client.py`, `test_events.py`.

#### 문서

- `docs/architecture/agent-routing.md`: AgentExecutor 작업 유형별 라우팅 설계 문서. AgentType 정의, 키워드 분류 로직, 에이전트별 프로필, 설계 결정 근거 포함.
