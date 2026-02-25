# autonomous-dev-agent 개편 TODO

> **전체 계획**: `.claude/plans/ancient-sleeping-petal.md` 참조
> **마지막 업데이트**: 2026-02-26
> **현재 상태**: Phase 0 완료, Phase 1 착수 전
> **프로젝트 버전**: v0.2.0
> **소스 현황**: 34개 파일, 4,028줄 (src/), 238개 테스트, 100% 커버리지

---

## 개편 배경 (왜 개편하는가?)

### 핵심 문제 5가지
1. **에이전트 간 협업 없음**: executor.execute() 결과(list[Message])가 버려짐, 파일시스템만 공유
2. **RAG가 Boolean BoW**: 의미 검색 불가, 매번 전체 재인덱싱 (O(n) 비효율)
3. **키워드 기반 에이전트 분류**: `_classify_task()`가 단순 substring 매칭, 혼합 의도 처리 불가
4. **Planner 컨텍스트 부족**: 스펙 500자 트런케이션, 실행 히스토리 없음
5. **설정 하드코딩**: 환경변수 오버라이드 불가, YAML 설정 제한적

### 사용자 결정 사항
- 웹 UI: 이번 개편에서 **제외** (TUI 개선에 집중)
- RAG: BM25 + 벡터 (Anthropic API 임베딩, subscription 활용)
- 상태 저장: SQLite + aiosqlite
- 범위: 단계적, 모듈별로 **전체** 구현

---

## Phase 0: 핵심 기반 구축 — DONE

> 기존 코드 터치 없이 새 추상화 계층과 인프라만 추가. 기존 238개 테스트 0개 영향.

### 0-1. src/core/ 도메인 모듈 (1,228줄 신규)

- [x] `src/core/__init__.py` — 패키지 마커
- [x] `src/core/interfaces.py` (211줄) — Protocol 기반 인터페이스 7개
  - [x] `AgentProtocol`: execute(task, context) → AgentResult
  - [x] `RouterProtocol`: route(task, available_agents) → agent_type
  - [x] `ChunkerProtocol`: chunk(file_path, content) → list[CodeChunk]
  - [x] `ScorerProtocol`: score(query, chunks) → list[(chunk, score)]
  - [x] `EmbeddingProtocol`: embed(texts) → list[list[float]]
  - [x] `UIAdapterProtocol`: emit_log, emit_progress, ask_question, emit_completed
  - [x] `PluginProtocol`: on_task_complete, on_phase_change
- [x] `src/core/domain.py` (123줄) — 값 객체 4개
  - [x] `AgentTask` (frozen dataclass): prompt, agent_type, priority, context
  - [x] `AgentResult`: agent_type, task_prompt, output_text, files_modified, success, error, metadata, created_at
  - [x] `ExecutionContext`: project_state, execution_history, rag_results + summary_for_planner(), last_result_of()
  - [x] `CodeChunk` (frozen): file_path, content, start_line, end_line, chunk_type, name
- [x] `src/core/exceptions.py` (100줄) — 예외 계층
  - [x] `AppError(Exception)` → `AgentError`, `RAGError`, `ConfigError`, `TokenLimitError`

### 0-2. src/infra/ 인프라 계층

- [x] `src/infra/__init__.py` — 패키지 마커
- [x] `src/infra/config.py` (141줄) — pydantic-settings 기반 설정
  - [x] `OrchestratorSettings`: planning_model, classifier_model
  - [x] `AgentSettings`: max_turns_per_task, permission_mode, use_rag
  - [x] `RAGSettings`: chunk_strategy, bm25_weight, vector_weight, top_k, use_vector_search, cache_enabled
  - [x] `TokenSettings`: initial_wait_seconds, max_wait_seconds
  - [x] `LoopSettings`: max_iterations
  - [x] `QualitySettings`: test_pass_rate, lint_errors, type_errors, coverage_min
  - [x] `AppSettings(BaseSettings)`: ADEV_ 접두사, env_nested_delimiter="__"
  - [x] `get_settings()` 싱글톤 + `load_config()` 호환 래퍼
- [x] `src/infra/events.py` (189줄) — 이벤트 버스 재설계
  - [x] `EventType(StrEnum)` 12종 (기존 6 + 신규 6: AGENT_STARTED/FINISHED, PIPELINE_STARTED/FINISHED, RAG_INDEXED, ERROR)
  - [x] `Event` dataclass: to_json() / from_json() 직렬화
  - [x] `EventChannel`: 멀티플렉스 답변 큐
  - [x] `EventBus`: 채널 분리 (question, completion), subscribe/publish/put_answer/wait_for_answer 호환
- [x] `src/infra/logger.py` (117줄) — structlog 기반 구조화 로그
  - [x] `setup_logger(name, level)` 기존 시그니처 유지
  - [x] `ADEV_LOG_LEVEL` 환경변수 오버라이드
  - [x] `RotatingFileHandler`: logs/agent.log, 5MB, 3 backups
  - [x] `_ColorFormatter`: ANSI 컬러 콘솔
  - [x] structlog 초기화 (graceful fallback)
- [x] `src/infra/state.py` (184줄) — SQLite 기반 상태 관리
  - [x] `StateStore`: init_db, save_state, load_state, record_session, get_recent_sessions
  - [x] 스키마: project_state (spec_hash UNIQUE) + agent_sessions 테이블
  - [x] ProjectState, PhaseType re-export (하위 호환)
- [x] `src/infra/claude_client.py` (163줄) — 기존 + 개선
  - [x] `retry_with_backoff` 데코레이터 (3회, 지수 백오프)
  - [x] SDK 모드 usage 추적 근사치

### 0-3. pyproject.toml 의존성 업데이트

- [x] `aiosqlite>=0.20.0` 추가
- [x] `rank-bm25>=0.2.2` 추가
- [x] `structlog>=24.0` 추가
- [x] `numpy>=1.26.0` 추가
- [x] `[rag]` optional extra: `lancedb>=0.6.0`
- [x] `[dev-lite]` extra: 경량 CI용
- [x] `pytest-benchmark>=4.0` → [dev] extra
- [x] 버전 0.1.0 → 0.2.0

### 0-4. 미완료 (Phase 3에서 처리)

- [ ] `tests/conftest.py` 공통 픽스처 통합 (make_mock_query 등)
- [ ] `src/utils/__init__.py` → `src/infra/*` re-export 리다이렉트

### 0-5. 검증 결과

- [x] ruff check: All checks passed!
- [x] mypy: Success: no issues found in 34 source files
- [x] pytest: 238 passed, 100% coverage

---

## Phase 1: RAG 시스템 전면 재설계 — TODO (다음 단계)

> 현재 RAG: Boolean BoW(단어 존재 여부만 체크), 전체 재인덱싱, 50줄 고정 청크
> 목표: AST 기반 청크 + BM25 + 벡터 하이브리드 검색 + 증분 인덱싱

### 1-1. `src/rag/chunker.py` — AST 기반 청크 분할 (신규)

> 현재: indexer.py에서 50줄 고정 크기로 분할 → 함수/클래스 경계 무시

- [ ] `ASTChunker` 클래스 구현 (ChunkerProtocol 구현체)
- [ ] Python 파일 처리:
  - [ ] `ast` built-in으로 `FunctionDef`, `AsyncFunctionDef`, `ClassDef` 노드 추출
  - [ ] 노드별 시작/끝 라인 추출 → CodeChunk 생성
  - [ ] 클래스 내부 메서드: 클래스 청크 + 개별 메서드 청크 모두 생성
  - [ ] 데코레이터 포함: `@decorator` 라인부터 함수 끝까지
  - [ ] 모듈 레벨 코드: 함수/클래스에 속하지 않는 코드 → "module" 타입 청크
- [ ] 비Python 파일 처리:
  - [ ] `.js`, `.ts`, `.yaml`, `.md` 등 → 고정 크기(50줄) 폴백
  - [ ] 줄 수 기반 오버랩 (10줄) 적용
- [ ] 크기 제한:
  - [ ] `MIN_LINES=5`: 5줄 미만 함수 → 모듈 청크에 포함
  - [ ] `MAX_LINES=100`: 100줄 초과 → 서브 청킹 (메서드별 분리)
- [ ] `CodeChunk` 확장 필드 활용:
  - [ ] `chunk_type`: "function" | "class" | "method" | "module" | "block"
  - [ ] `name`: 함수명/클래스명 (검색용)
- [ ] 에러 처리: 파싱 실패 시 고정 크기 폴백 (SyntaxError 등)
- [ ] 테스트: `tests/test_chunker.py`
  - [ ] Python 함수 추출 정확도
  - [ ] 클래스 + 메서드 분리
  - [ ] 비Python 폴백
  - [ ] MIN/MAX_LINES 경계 케이스
  - [ ] SyntaxError 파일 처리
  - [ ] 빈 파일 처리
  - [ ] 데코레이터 포함 확인
  - [ ] 모듈 레벨 코드 추출

### 1-2. `src/rag/scorer.py` — BM25 스코어링 (신규)

> 현재: Boolean BoW (단어가 있으면 1, 없으면 0) → IDF 없음, 희귀 토큰 가중치 없음

- [ ] `BM25Scorer` 클래스 구현 (ScorerProtocol 구현체)
- [ ] `rank-bm25` 라이브러리 활용 (`BM25Okapi`)
- [ ] `fit(documents: list[str])`: 문서 컬렉션으로 IDF 계산
  - [ ] 토큰화: 공백 분리 + 소문자 변환 + 특수문자 제거
  - [ ] Python 식별자 분리: `camelCase` → `camel`, `case` / `snake_case` → `snake`, `case`
  - [ ] 한글 지원: 형태소 분석 없이 공백 기반 (차후 개선)
- [ ] `score(query: str, top_k: int)` → `list[tuple[CodeChunk, float]]`
  - [ ] 쿼리 토큰화 (동일 방식)
  - [ ] BM25 스코어 계산
  - [ ] top_k 결과 반환 (스코어 내림차순)
- [ ] 파라미터 설정:
  - [ ] k1=1.5 (기본값, config에서 오버라이드 가능)
  - [ ] b=0.75 (기본값)
- [ ] 테스트: `tests/test_scorer.py`
  - [ ] 기본 BM25 스코어링
  - [ ] IDF 가중치 (희귀 단어 높은 점수)
  - [ ] 빈 쿼리/빈 문서
  - [ ] top_k 제한
  - [ ] Python 식별자 토큰화

### 1-3. `src/rag/embedder.py` — Anthropic API 임베딩 (신규)

> Anthropic API의 임베딩 엔드포인트 활용 (subscription으로 추가 비용 없음)

- [ ] `AnthropicEmbedder` 클래스 구현 (EmbeddingProtocol 구현체)
- [ ] Anthropic API 직접 호출:
  - [ ] `ANTHROPIC_API_KEY` 환경변수 사용 시: `anthropic.Anthropic().embeddings.create()`
  - [ ] API 키 없을 때: claude-agent-sdk subscription 모드로 폴백
  - [ ] 모델: `voyage-3` 또는 Anthropic 기본 임베딩 모델
- [ ] 배치 처리:
  - [ ] 한 번에 최대 96개 텍스트 (API 제한)
  - [ ] 96개 초과 시 자동 분할 + 순차 처리
- [ ] 임베딩 캐시:
  - [ ] 텍스트 해시(SHA256) → 임베딩 벡터 매핑
  - [ ] `.rag_cache/embeddings.json` 파일 저장
  - [ ] 동일 텍스트 재임베딩 방지 (캐시 히트율 로깅)
- [ ] 에러 처리:
  - [ ] API 실패 시 재시도 (3회, 지수 백오프)
  - [ ] Rate limit 시 대기 후 재시도
  - [ ] 임베딩 불가 시: 벡터 검색 비활성화 (graceful degradation)
- [ ] 테스트: `tests/test_embedder.py`
  - [ ] API 호출 mock
  - [ ] 배치 분할 로직
  - [ ] 캐시 히트/미스
  - [ ] 에러 시 graceful degradation
  - [ ] SDK 폴백 모드

### 1-4. `src/rag/vector_store.py` — 벡터 저장소 (신규)

> 임베딩 벡터를 저장하고 유사도 검색을 수행

- [ ] `VectorStore` 인터페이스 정의:
  - [ ] `add(chunks: list[CodeChunk], embeddings: list[list[float]])`
  - [ ] `search(query_embedding: list[float], top_k: int) → list[tuple[CodeChunk, float]]`
  - [ ] `remove(file_path: str)` — 파일별 삭제 (증분 인덱싱용)
  - [ ] `clear()` — 전체 초기화
- [ ] `LanceDBStore` 구현 (lancedb optional):
  - [ ] `lancedb` 가 설치되어 있을 때 사용
  - [ ] 테이블: file_path, chunk_content, start_line, end_line, chunk_type, name, vector
  - [ ] ANN 검색 (Approximate Nearest Neighbor)
- [ ] `NumpyStore` 폴백 구현:
  - [ ] `lancedb` 없을 때 numpy cosine similarity 사용
  - [ ] 인메모리 저장 (작은 프로젝트에 적합)
  - [ ] `numpy.dot(a, b) / (norm(a) * norm(b))` 코사인 유사도
- [ ] 팩토리 함수: `create_vector_store()` → 환경에 따라 자동 선택
- [ ] 테스트: `tests/test_vector_store.py`
  - [ ] NumpyStore 기본 add/search
  - [ ] 코사인 유사도 정확도
  - [ ] remove 후 검색 결과 변경
  - [ ] 빈 스토어 검색
  - [ ] LanceDBStore mock 테스트

### 1-5. `src/rag/hybrid_search.py` — BM25 + 벡터 하이브리드 검색 (신규)

> BM25 렉시컬 검색 + 벡터 시맨틱 검색을 가중 결합

- [ ] `HybridSearcher` 클래스 구현:
  - [ ] 의존성 주입: `BM25Scorer`, `VectorStore`, `AnthropicEmbedder`
  - [ ] `search(query: str, top_k: int) → list[tuple[CodeChunk, float]]`
- [ ] 검색 흐름:
  - [ ] BM25 검색: top_k * 2 개 후보 추출 (over-fetch)
  - [ ] 벡터 검색: 쿼리 임베딩 → top_k * 2 개 후보 추출
  - [ ] 스코어 정규화: 각각 0~1 범위로 min-max 정규화
  - [ ] 가중 결합: `final = bm25_weight * bm25_score + vector_weight * vector_score`
  - [ ] 가중치: config에서 설정 (기본: bm25=0.6, vector=0.4)
  - [ ] 중복 제거: 동일 파일+라인 범위 → 높은 스코어 유지
  - [ ] top_k 최종 결과 반환
- [ ] Graceful degradation:
  - [ ] 벡터 검색 비활성화 시 (`use_vector_search=False`): BM25만 사용
  - [ ] 임베딩 실패 시: 자동으로 BM25-only 모드 전환
  - [ ] BM25 + 벡터 결과가 겹치지 않을 때: 각각 top_k/2씩
- [ ] 테스트: `tests/test_hybrid_search.py`
  - [ ] BM25-only 모드
  - [ ] 하이브리드 모드 (mock embedder)
  - [ ] 가중치 변경에 따른 결과 순서 변화
  - [ ] 중복 제거
  - [ ] graceful degradation

### 1-6. `src/rag/incremental_indexer.py` — 증분 인덱싱 (신규)

> 현재: 매번 전체 파일 재인덱싱 → 변경된 파일만 재인덱싱

- [ ] `IncrementalIndexer` 클래스 구현:
  - [ ] 의존성 주입: `ASTChunker`, `BM25Scorer`, `VectorStore`
  - [ ] `index(project_path: str)` — 전체 인덱싱 (최초 1회)
  - [ ] `update()` — 증분 인덱싱 (변경분만)
  - [ ] `search(query: str, top_k: int)` → HybridSearcher 위임
- [ ] 변경 감지:
  - [ ] 파일 mtime (수정 시각) 기반
  - [ ] `.rag_cache/file_index.json`: {file_path: mtime, chunk_count, last_indexed}
  - [ ] 새 파일: 인덱싱 추가
  - [ ] 수정 파일: 기존 청크 삭제 → 재인덱싱
  - [ ] 삭제 파일: 인덱스에서 제거
- [ ] 인덱스 캐시:
  - [ ] `.rag_cache/` 디렉토리
  - [ ] `bm25_index.pkl`: BM25 인덱스 직렬화 (pickle)
  - [ ] `file_index.json`: 파일 메타데이터
  - [ ] `embeddings.json`: 임베딩 캐시
  - [ ] `.gitignore`에 `.rag_cache/` 추가
- [ ] 파일 필터링:
  - [ ] `.gitignore` 패턴 준수
  - [ ] 바이너리 파일 제외
  - [ ] `__pycache__/`, `.git/`, `node_modules/`, `.venv/` 제외
  - [ ] 설정 가능한 include/exclude 패턴
- [ ] 싱글톤 패턴:
  - [ ] `AgentExecutor._build_options()` 에서 매번 새 MCP 서버 생성하는 문제 해결
  - [ ] 모듈 레벨 싱글톤 또는 의존성 주입으로 전환
- [ ] 테스트: `tests/test_incremental_indexer.py`
  - [ ] 최초 전체 인덱싱
  - [ ] 파일 수정 후 증분 인덱싱 (변경분만 처리 확인)
  - [ ] 파일 삭제 후 인덱스 정리
  - [ ] 캐시 저장/로드
  - [ ] .gitignore 패턴 필터링
  - [ ] 빈 프로젝트 처리

### 1-7. `src/rag/mcp_server.py` — MCP 도구 확장 (기존 수정)

> 현재: search_code, reindex_codebase (2개만)

- [ ] 기존 도구 유지 + IncrementalIndexer 연동:
  - [ ] `search_code` → HybridSearcher 사용으로 전환
  - [ ] `reindex_codebase` → IncrementalIndexer.update() 사용
- [ ] 신규 도구 추가:
  - [ ] `search_by_symbol(name: str)`: 함수명/클래스명으로 정확 검색
    - CodeChunk.name 필드 활용
    - 부분 매칭 지원 (prefix, contains)
  - [ ] `get_file_structure(path?: str)`: 프로젝트 디렉토리 구조 반환
    - 트리 형태 문자열
    - 깊이 제한 옵션
  - [ ] `get_similar_patterns(code_snippet: str)`: 유사 코드 패턴 검색
    - 임베딩 기반 유사도 검색
    - "이런 패턴의 코드가 어디에 있나?" 질문 대응
- [ ] 기존 test_indexer.py, test_mcp_server.py 재작성
- [ ] 테스트: 신규 도구별 테스트 추가

### Phase 1 검증 체크리스트

- [ ] `pytest tests/ -v --cov` — 전체 통과
- [ ] `ruff check src/` — 린트 클린
- [ ] `mypy src/` — 타입 체크 통과
- [ ] 커버리지 90%+ 유지
- [ ] BM25가 기존 Boolean BoW보다 관련 파일을 상위에 반환하는지 수동 검증
- [ ] 증분 인덱싱: 파일 수정 후 변경분만 처리되는지 확인
- [ ] MCP 서버 새 도구 3개 동작 확인

---

## Phase 2: 에이전트 실행 엔진 재설계 — TODO

> 현재: executor.execute() → list[Message] 버려짐, 키워드 라우터, 파이프라인 없음
> 목표: LLM 라우터 + 파이프라인 실행 + 결과 환류 + 에이전트 메모리

### 2-1. `src/agents/router.py` — LLM 기반 라우터 (신규)

> 현재: executor.py의 _classify_task()가 단순 substring 매칭
> ("테스트" in prompt → TESTER, "설계" in prompt → ARCHITECT, ...)

- [ ] `LLMRouter` 클래스 구현 (RouterProtocol 구현체)
- [ ] Claude API로 에이전트 타입 판단:
  - [ ] 시스템 프롬프트: "다음 작업을 수행할 가장 적합한 에이전트를 선택하세요: ARCHITECT, CODER, TESTER, REVIEWER, DOCUMENTER"
  - [ ] 응답 파싱: JSON 형식 {"agent_type": "CODER", "reason": "..."}
  - [ ] subscription 활용 (추가 비용 없음)
- [ ] 캐싱:
  - [ ] 프롬프트 해시 → 에이전트 타입 매핑 캐시
  - [ ] TTL 설정 (기본 1시간)
  - [ ] 동일 패턴 반복 호출 방지
- [ ] 폴백:
  - [ ] API 호출 실패 시 기존 키워드 매칭으로 폴백
  - [ ] 타임아웃: 5초 (라우팅이 느려지면 안 됨)
- [ ] 혼합 의도 처리:
  - [ ] "코드 작성하고 테스트도 해줘" → CODER (파이프라인이 TESTER 자동 추가)
  - [ ] 파이프라인 제안: 라우터가 추가 단계 제안 가능
- [ ] 테스트: `tests/test_router.py`
  - [ ] 기본 라우팅 (API mock)
  - [ ] 캐시 히트/미스
  - [ ] API 실패 시 키워드 폴백
  - [ ] 혼합 의도 처리
  - [ ] 타임아웃 처리

### 2-2. `src/agents/pipeline.py` — 에이전트 파이프라인 (신규)

> 현재: Orchestrator가 단일 execute() 호출, 결과 무시
> 목표: CODER → TESTER → REVIEWER 순차 실행, 결과 전달

- [ ] `PipelineStep` dataclass:
  - [ ] agent_type: AgentType
  - [ ] condition: Callable[[AgentResult], bool] | None (조건부 실행)
  - [ ] inject_previous_result: bool (이전 결과를 프롬프트에 포함)
  - [ ] transform_prompt: Callable[[str, AgentResult], str] | None (프롬프트 변환)
- [ ] `Pipeline` 클래스:
  - [ ] `steps: list[PipelineStep]`
  - [ ] `run(initial_task: AgentTask, executor: AgentExecutor) → list[AgentResult]`
  - [ ] 순차 실행: step1 결과 → step2 입력 → step3 입력
  - [ ] 조건부 실행: step1 성공 시에만 step2 실행
  - [ ] 에러 시: 파이프라인 중단 + 실패 결과 반환
- [ ] 표준 파이프라인 프리셋:
  - [ ] `CODING_PIPELINE`: CODER → TESTER → REVIEWER
    - CODER 성공 → TESTER에 files_modified 주입
    - TESTER 성공 → REVIEWER에 테스트 결과 + 코드 변경 주입
    - REVIEWER 실패 → CODER에 리뷰 피드백으로 재실행 (1회)
  - [ ] `DESIGN_PIPELINE`: ARCHITECT → CODER
  - [ ] `FIX_PIPELINE`: CODER (수정) → TESTER (검증)
- [ ] 이벤트 발행:
  - [ ] PIPELINE_STARTED: 파이프라인 시작 시
  - [ ] AGENT_STARTED/FINISHED: 각 스텝 시작/종료 시
  - [ ] PIPELINE_FINISHED: 파이프라인 완료 시
- [ ] 테스트: `tests/test_pipeline.py`
  - [ ] 기본 순차 실행
  - [ ] 조건부 실행 (성공/실패 분기)
  - [ ] 이전 결과 주입
  - [ ] 파이프라인 중단 (에러 시)
  - [ ] 표준 프리셋 동작
  - [ ] 이벤트 발행 확인

### 2-3. `src/agents/memory.py` — 에이전트 메모리 (신규)

> 현재: 실행 이력 없음. 같은 실수를 반복할 수 있음
> 목표: SQLite에 실행 이력 저장, Planner 컨텍스트에 주입

- [ ] `AgentMemory` 클래스:
  - [ ] 의존성: `StateStore` (src/infra/state.py)
  - [ ] `record(result: AgentResult)`: DB에 실행 결과 저장
    - agent_type, task_prompt, output_text (요약), success, error, files_modified, timestamp
  - [ ] `get_recent(n: int = 10) → list[AgentResult]`: 최근 n개 결과 조회
  - [ ] `get_by_agent_type(agent_type: str, n: int = 5)`: 에이전트별 최근 결과
  - [ ] `summary_for_planner(n: int = 5) → str`: Planner에 주입할 이력 요약 텍스트
    - "최근 5개 실행: CODER(성공) → TESTER(실패: 3개 테스트 실패) → CODER(성공) → ..."
  - [ ] `get_failure_patterns() → list[str]`: 반복 실패 패턴 감지
    - 같은 에러가 3회 이상 반복 → 크리티컬 이슈 후보
- [ ] 재시작 시 이력 복원:
  - [ ] SQLite에서 현재 세션 이력 로드
  - [ ] session_id 기반 세션 구분
- [ ] 테스트: `tests/test_memory.py`
  - [ ] record + get_recent
  - [ ] summary_for_planner 포맷
  - [ ] 에이전트별 조회
  - [ ] 실패 패턴 감지
  - [ ] 세션 복원

### 2-4. `src/agents/profiles.py` — 에이전트 프로필 분리 (기존에서 추출)

> 현재: executor.py에 AgentType, AgentProfile, AGENT_PROFILES 모두 포함 (50줄+)

- [ ] executor.py에서 추출:
  - [ ] `AgentType(StrEnum)`: ARCHITECT, CODER, TESTER, REVIEWER, DOCUMENTER
  - [ ] `AgentProfile` dataclass: agent_type, system_prompt, allowed_tools, model, max_turns
  - [ ] `AGENT_PROFILES` 딕셔너리
- [ ] 설정 연동:
  - [ ] config에서 모델 오버라이드: `ADEV_AGENT__CODER_MODEL=claude-opus-4-6`
  - [ ] config에서 도구 추가/제거
  - [ ] `get_profile(agent_type, settings)` → 설정 적용된 프로필 반환
- [ ] executor.py 수정: profiles.py에서 import
- [ ] 테스트: `tests/test_profiles.py`
  - [ ] 기본 프로필 로드
  - [ ] 설정 오버라이드
  - [ ] 없는 에이전트 타입 처리

### 2-5. `src/agents/executor.py` — 슬림화 (기존 대폭 수정)

> 현재: 390줄, _classify_task + execute + execute_with_retry + 프로필 정의 모두 포함
> 목표: 200줄 이내, 순수 실행 로직만

- [ ] 제거 대상:
  - [ ] `_classify_task()` → LLMRouter로 대체
  - [ ] `AgentType`, `AgentProfile`, `AGENT_PROFILES` → profiles.py로 이동
- [ ] execute() 반환 타입 변경:
  - [ ] `list[Message]` → `AgentResult` (구조화된 결과)
  - [ ] Message에서 텍스트 추출 → output_text
  - [ ] ToolUseBlock에서 파일 수정 감지 → files_modified
  - [ ] 성공/실패 판단 로직 포함
- [ ] execute_with_retry() 개선:
  - [ ] 빈 결과도 실패로 처리
  - [ ] 재시도 간 대기 시간 설정 (지수 백오프)
  - [ ] 재시도 시 이전 에러 메시지를 프롬프트에 포함
- [ ] MCP 서버 싱글톤:
  - [ ] `_build_options()` 에서 매번 `MCPServer` 재생성 → init에서 1회
  - [ ] 인덱서 싱글톤 참조
- [ ] 테스트: `tests/test_executor.py` 재작성 (기존 50개)
  - [ ] AgentResult 반환 확인
  - [ ] files_modified 추출
  - [ ] 성공/실패 판단
  - [ ] 재시도 로직
  - [ ] MCP 서버 싱글톤

### 2-6. Orchestrator 핵심 루프 변경 (`src/orchestrator/main.py`) (기존 대폭 수정)

> 현재: executor.execute() 결과 버림, planner 컨텍스트 빈약
> 목표: AgentResult 누적, ExecutionContext 풍부화

- [ ] `execute()` 결과 활용:
  - [ ] `AgentResult`를 `ExecutionContext.execution_history`에 누적
  - [ ] 최근 5개 결과를 Planner에 전달
  - [ ] 실패 결과: 에러 메시지를 다음 작업 프롬프트에 포함
- [ ] Pipeline 연동:
  - [ ] 단일 `execute()` → `pipeline.run()` 호출
  - [ ] 태스크 종류에 따라 적절한 파이프라인 선택
  - [ ] 파이프라인 결과를 ExecutionContext에 통합
- [ ] `_build_context()` 풍부화 (planner.py):
  - [ ] 스펙 500자 제한 제거 → 전체 스펙 전달
  - [ ] `execution_history` 최근 5개 주입
  - [ ] `language`, `framework` 정보 포함
  - [ ] 실패 원인 + 실패 횟수 포함
  - [ ] RAG 검색 결과 포함 (관련 코드 컨텍스트)
- [ ] `_update_state()` 개선:
  - [ ] 이진 스텝(0/1) → 그래디언트 진전 반영
  - [ ] 린트 에러 10→5 감소: 진전으로 인정 (현재는 "에러 있음"으로만 처리)
  - [ ] 테스트 통과율 80%→95%: 진전으로 인정
  - [ ] 진전 없으면 전략 변경 시그널 발생
- [ ] `_handle_issues()` 후 재검증:
  - [ ] 이슈 수정 후 자동으로 verifier 재실행
  - [ ] 수정 → 검증 → 수정 미니 루프
- [ ] AgentMemory 연동:
  - [ ] 매 실행 결과를 memory.record()로 저장
  - [ ] 세션 재시작 시 이력 복원
- [ ] 테스트: `tests/test_main.py` 재작성 (기존 39개)
  - [ ] AgentResult 누적 확인
  - [ ] Pipeline 실행 확인
  - [ ] 컨텍스트 풍부화 확인
  - [ ] 그래디언트 진전 반영
  - [ ] 이슈 수정 후 재검증

### 2-7. `src/orchestrator/planner.py` — 컨텍스트 풍부화 (기존 수정)

- [ ] `_build_context()` 변경:
  - [ ] spec 전체 전달 (500자 제한 제거)
  - [ ] execution_history 주입
  - [ ] language/framework 포함
  - [ ] 실패 원인 포함
- [ ] 테스트: `tests/test_planner.py` 재작성 (기존 6개)

### Phase 2 검증 체크리스트

- [ ] `pytest tests/ -v --cov` — 전체 통과
- [ ] `ruff check src/` — 린트 클린
- [ ] `mypy src/` — 타입 체크 통과
- [ ] 커버리지 90%+ 유지
- [ ] 파이프라인: CODER → TESTER → REVIEWER 결과 전달 확인
- [ ] 메모리: 실행 이력 저장/조회 확인
- [ ] Planner: 풍부한 컨텍스트 포함 확인
- [ ] LLM 라우터: 키워드 매칭보다 정확한 분류 확인

---

## Phase 3: 설정 + 로거 + CLI 개선 — TODO

> 기존 src/utils/ → src/infra/ 완전 전환 + CLI 강화

### 3-1. 설정 시스템 완전 전환

- [ ] `src/utils/config.py` 의 모든 사용처를 `src/infra/config.py`로 전환:
  - [ ] `src/orchestrator/main.py`: `from src.utils.config import load_config` → `from src.infra.config import get_settings`
  - [ ] `src/orchestrator/planner.py`: 설정 참조 경로 변경
  - [ ] `src/orchestrator/token_manager.py`: 설정 참조 경로 변경
  - [ ] `src/agents/executor.py`: 설정 참조 경로 변경
  - [ ] `src/agents/verifier.py`: 설정 참조 경로 변경
  - [ ] `src/cli.py`: 설정 참조 경로 변경
  - [ ] `src/ui/tui/app.py`: 설정 참조 경로 변경
- [ ] `config/default.yaml` 확장:
  - [ ] RAG 설정 섹션 추가 (chunk_strategy, bm25_weight 등)
  - [ ] 파이프라인 설정 추가 (default_pipeline, retry_count)
  - [ ] 에이전트 모델 오버라이드 설정
- [ ] `.env.example` 업데이트:
  - [ ] ADEV_ORCHESTRATOR__PLANNING_MODEL
  - [ ] ADEV_AGENT__MAX_TURNS_PER_TASK
  - [ ] ADEV_RAG__USE_VECTOR_SEARCH
  - [ ] ADEV_LOG_LEVEL
- [ ] `src/utils/config.py` → 호환 래퍼만 남기기 (import redirect)

### 3-2. 로거 전환

- [ ] `src/utils/logger.py` 사용처를 `src/infra/logger.py`로 전환:
  - [ ] 모든 `from src.utils.logger import setup_logger` → `from src.infra.logger import setup_logger`
  - [ ] 또는 `src/utils/logger.py`를 리다이렉트 래퍼로 변경
- [ ] TUI 실행 시 stdout 핸들러 비활성화 (충돌 방지):
  - [ ] `ADEV_TUI_MODE=1` 환경변수 체크
  - [ ] TUI 모드에서는 파일 핸들러만 활성화

### 3-3. CLI 개선 (`src/cli.py`)

> 현재: 단순 TUI 실행만 가능

- [ ] `argparse` 도입:
  - [ ] `adev` — 기본: TUI 모드
  - [ ] `adev --no-tui` — headless 모드 (TUI 없이 Orchestrator 직접 실행)
  - [ ] `adev --spec <path>` — 스펙 파일 지정
  - [ ] `adev --project <path>` — 프로젝트 경로 지정
  - [ ] `adev --version` — 버전 출력
  - [ ] `adev --log-level <level>` — 로그 레벨 지정
  - [ ] `adev --config <path>` — 설정 파일 경로 지정
- [ ] headless 모드:
  - [ ] Orchestrator를 직접 실행
  - [ ] stdout에 진행 상황 출력
  - [ ] 크리티컬 이슈 시 stdin으로 입력 받기
- [ ] 환경 검증:
  - [ ] Python 버전 체크 (>=3.12)
  - [ ] 필수 패키지 설치 확인
  - [ ] Claude Code 인증 확인

### 3-4. src/utils/ → src/infra/ 리다이렉트

- [ ] `src/utils/__init__.py` 수정:
  - [ ] `from src.infra.config import get_settings, load_config, AppSettings`
  - [ ] `from src.infra.events import EventBus, EventType, Event`
  - [ ] `from src.infra.logger import setup_logger`
  - [ ] `from src.infra.state import ProjectState, PhaseType, StateStore`
  - [ ] `from src.infra.claude_client import call_claude_for_text`
  - [ ] deprecation warning 추가

### 3-5. tests/conftest.py 공통 픽스처

- [ ] `make_mock_query()` 헬퍼 통합 (현재 3개 파일에 중복)
- [ ] `make_assistant_message(text)` 팩토리
- [ ] 공통 픽스처: event_bus, tmp_project, mock_settings 등

### Phase 3 검증 체크리스트

- [ ] `pytest tests/ -v --cov` — 전체 통과
- [ ] `ruff check src/` — 린트 클린
- [ ] `mypy src/` — 타입 체크 통과
- [ ] `adev --version` 동작 확인
- [ ] `adev --no-tui --spec test.md` 동작 확인
- [ ] 환경변수 오버라이드 동작 확인 (ADEV_*)
- [ ] 기존 import 경로 호환 확인

---

## Phase 4: TUI 개선 + 이벤트 시스템 — TODO

> 현재: 기본 TUI + 단순 이벤트 버스
> 목표: 에이전트 실행 현황, 파이프라인 시각화, 채널 분리

### 4-1. EventBus 전환 적용

- [ ] `src/utils/events.py` → `src/infra/events.py` 완전 전환
  - [ ] 모든 사용처 import 경로 변경
  - [ ] src/utils/events.py → 리다이렉트 래퍼
- [ ] 신규 이벤트 타입 활용:
  - [ ] `AGENT_STARTED`: TUI에서 "CODER 실행 중..." 표시
  - [ ] `AGENT_FINISHED`: TUI에서 결과 요약 표시
  - [ ] `PIPELINE_STARTED/FINISHED`: 파이프라인 진행률 표시
  - [ ] `ERROR`: 에러 패널에 표시
  - [ ] `RAG_INDEXED`: 인덱싱 상태 표시
- [ ] 채널 분리 적용:
  - [ ] "question" 채널: 사용자 입력 요청
  - [ ] "completion" 채널: 작업 완료 알림
  - [ ] 채널별 독립 큐

### 4-2. TUI 개선 (`src/ui/tui/app.py`)

- [ ] `UIAdapterProtocol` 기반 리팩토링:
  - [ ] 이벤트 핸들러를 Protocol 메서드에 매핑
  - [ ] emit_log → 로그 패널 업데이트
  - [ ] emit_progress → 진행률 바 업데이트
  - [ ] ask_question → 입력 다이얼로그 표시
  - [ ] emit_completed → 완료 화면 표시
- [ ] 에이전트 실행 현황 패널 추가:
  - [ ] 현재 실행 중인 에이전트 표시 (이름 + 스피너)
  - [ ] 파이프라인 단계 표시 (CODER ✓ → TESTER ⟳ → REVIEWER ○)
  - [ ] 각 단계 소요 시간
  - [ ] 실패 시 에러 요약
- [ ] 파이프라인 진행 상황 시각화:
  - [ ] 전체 진행률 바
  - [ ] 단계별 상태 (대기/실행중/성공/실패)
- [ ] 이력 패널:
  - [ ] 최근 실행 결과 목록
  - [ ] 성공/실패 통계

### 4-3. CLAUDE.md 동기화

- [ ] 디렉토리 구조 업데이트:
  - [ ] `src/core/` 추가
  - [ ] `src/infra/` 추가
  - [ ] `src/agents/` 변경 사항 반영 (router, pipeline, memory, profiles)
  - [ ] `src/rag/` 변경 사항 반영 (chunker, scorer, embedder 등)
- [ ] 신규 명령어 문서화
- [ ] 의존성 목록 업데이트

### Phase 4 검증 체크리스트

- [ ] `pytest tests/ -v --cov` — 전체 통과
- [ ] `ruff check src/` — 린트 클린
- [ ] `mypy src/` — 타입 체크 통과
- [ ] TUI에서 에이전트 실행 현황 표시 확인
- [ ] 이벤트 채널 분리 동작 확인
- [ ] CLAUDE.md 실제 구조와 일치 확인

---

## Phase 5: 플러그인 시스템 + 문서화 — TODO

> 확장 포인트 + 최종 문서 + 통합 테스트

### 5-1. `src/plugins/` 플러그인 시스템 (신규)

- [ ] `src/plugins/__init__.py`
- [ ] `src/plugins/base.py`:
  - [ ] `PluginProtocol` 재export (src/core/interfaces.py)
  - [ ] 플러그인 기본 클래스
- [ ] `src/plugins/registry.py`:
  - [ ] `PluginRegistry`: 플러그인 등록/조회/실행
  - [ ] `register(plugin)`, `unregister(name)`
  - [ ] `on_task_complete(result)` → 등록된 모든 플러그인에 전달
  - [ ] `on_phase_change(old_phase, new_phase)` → 등록된 모든 플러그인에 전달
  - [ ] 플러그인 실행 에러 격리 (한 플러그인 실패해도 나머지 실행)
- [ ] `src/plugins/builtin/github.py`:
  - [ ] PR 자동 생성 플러그인
  - [ ] 기능 완료 시 자동 PR 생성
  - [ ] 커밋 메시지에서 PR 제목/본문 생성
- [ ] 테스트: `tests/test_plugins.py`

### 5-2. 문서 전체 재생성

- [ ] documenter 에이전트로 docs/ 전체 재작성:
  - [ ] `docs/architecture/overview.md` — 신규 아키텍처 개요
  - [ ] `docs/architecture/data-models.md` — 도메인 모델 설명
  - [ ] `docs/architecture/rag-system.md` — RAG 시스템 설계
  - [ ] `docs/architecture/agent-pipeline.md` — 파이프라인 설계
  - [ ] `docs/api/` — API 문서 업데이트
  - [ ] `docs/setup/development.md` — 개발 환경 설정
  - [ ] `docs/setup/deployment.md` — 배포 가이드
  - [ ] `README.md` 업데이트
  - [ ] `CHANGELOG.md` 업데이트

### 5-3. 통합 테스트 추가

- [ ] `tests/integration/` 디렉토리 생성
- [ ] `tests/integration/test_agent_pipeline.py`:
  - [ ] CODER → TESTER → REVIEWER E2E (mock Claude API)
  - [ ] 파이프라인 결과 전달 확인
  - [ ] 조건부 실행 확인
- [ ] `tests/integration/test_rag_hybrid.py`:
  - [ ] BM25 + 벡터 하이브리드 검색 E2E
  - [ ] 실제 Python 파일로 인덱싱 → 검색 → 결과 평가
- [ ] `tests/integration/test_orchestrator_loop.py`:
  - [ ] Orchestrator 1-iteration 통합 테스트
  - [ ] Planner → Router → Pipeline → Verifier 전체 흐름

### 5-4. tests/conftest.py 최종 정리

- [ ] 통합 테스트용 픽스처 추가
- [ ] 불필요한 중복 픽스처 제거
- [ ] conftest 계층 정리 (tests/, tests/unit/, tests/integration/)

### Phase 5 검증 체크리스트

- [ ] `pytest tests/ -v --cov` — 전체 통과 (유닛 + 통합)
- [ ] `ruff check src/` — 린트 클린
- [ ] `mypy src/` — 타입 체크 통과
- [ ] 커버리지 90%+ 유지
- [ ] 플러그인 시스템 동작 확인
- [ ] 문서 완성도 검토
- [ ] 통합 테스트 전체 통과

---

## 파일 수정 매트릭스

| 파일 | Phase | 변경 내용 | 영향 테스트 |
|------|-------|----------|------------|
| `src/core/interfaces.py` | 0 DONE | Protocol 7개 | - |
| `src/core/domain.py` | 0 DONE | 값 객체 4개 | - |
| `src/core/exceptions.py` | 0 DONE | 예외 계층 | - |
| `src/infra/config.py` | 0 DONE | pydantic-settings | - |
| `src/infra/events.py` | 0 DONE | 채널 분리 EventBus | - |
| `src/infra/logger.py` | 0 DONE | structlog 로거 | - |
| `src/infra/state.py` | 0 DONE | SQLite StateStore | - |
| `src/infra/claude_client.py` | 0 DONE | retry + usage 추적 | - |
| `pyproject.toml` | 0 DONE | 의존성 개편 | - |
| `src/rag/chunker.py` | 1 | AST 기반 청크 | 신규 |
| `src/rag/scorer.py` | 1 | BM25 스코어링 | 신규 |
| `src/rag/embedder.py` | 1 | Anthropic 임베딩 | 신규 |
| `src/rag/vector_store.py` | 1 | 벡터 저장소 | 신규 |
| `src/rag/hybrid_search.py` | 1 | 하이브리드 검색 | 신규 |
| `src/rag/incremental_indexer.py` | 1 | 증분 인덱싱 | 신규 |
| `src/rag/mcp_server.py` | 1 | MCP 도구 확장 | test_mcp_server 재작성 |
| `src/rag/indexer.py` | 1 | IncrementalIndexer로 대체 | test_indexer 재작성 |
| `src/agents/router.py` | 2 | LLM 기반 라우터 | 신규 |
| `src/agents/pipeline.py` | 2 | 에이전트 파이프라인 | 신규 |
| `src/agents/memory.py` | 2 | 에이전트 메모리 | 신규 |
| `src/agents/profiles.py` | 2 | 프로필 분리 | 신규 |
| `src/agents/executor.py` | 2 | 슬림화 | test_executor (50개) 재작성 |
| `src/orchestrator/main.py` | 2 | 파이프라인+결과환류 | test_main (39개) 재작성 |
| `src/orchestrator/planner.py` | 2 | 컨텍스트 풍부화 | test_planner (6개) 재작성 |
| `src/utils/config.py` | 3 | infra 리다이렉트 | test_config (10개) 재작성 |
| `src/utils/logger.py` | 3 | infra 리다이렉트 | - |
| `src/utils/events.py` | 4 | infra 리다이렉트 | test_events (10개) 재작성 |
| `src/cli.py` | 3 | argparse 도입 | test_cli (9개) 재작성 |
| `src/ui/tui/app.py` | 4 | UIAdapter+현황패널 | test_tui (34개) 재작성 |
| `config/default.yaml` | 3 | 설정 항목 확장 | - |
| `CLAUDE.md` | 4 | 구조 동기화 | - |

---

## 새 PC에서 이어서 작업하는 방법

```bash
# 1. 저장소 클론
git clone <repo-url> autonomous-dev-agent
cd autonomous-dev-agent

# 2. 가상환경 생성 + 의존성 설치
python -m venv .venv
source .venv/Scripts/activate  # Windows Git Bash
# 또는
.venv\Scripts\activate  # Windows CMD
pip install -e ".[dev]"

# 3. 현재 상태 확인
python -m pytest tests/ -v --cov
python -m ruff check src/
python -m mypy src/

# 4. 다음 작업: Phase 1 시작
# 전체 계획 확인: .claude/plans/ancient-sleeping-petal.md
# 이 파일의 Phase 1 섹션부터 순서대로 진행

# 5. Claude Code 사용 시
# "Phase 1 RAG 시스템 재설계 진행해줘" 라고 요청
```

---

## 의존성 목록 (v0.2.0)

### 필수
- anthropic>=0.40.0
- claude-agent-sdk>=0.1.0
- pydantic>=2.0
- pydantic-settings>=2.0
- pyyaml>=6.0
- textual>=0.80.0
- python-dotenv>=1.0.0
- aiosqlite>=0.20.0 (Phase 0에서 추가)
- rank-bm25>=0.2.2 (Phase 0에서 추가)
- structlog>=24.0 (Phase 0에서 추가)
- numpy>=1.26.0 (Phase 0에서 추가)

### Optional [rag]
- lancedb>=0.6.0

### Dev [dev]
- pytest>=8.0
- pytest-cov>=5.0
- pytest-asyncio>=0.23.0
- pytest-benchmark>=4.0
- ruff>=0.5.0
- mypy>=1.10.0
- textual-dev>=1.0.0

### Dev Lite [dev-lite]
- pytest>=8.0
- pytest-cov>=5.0
- ruff>=0.5.0
