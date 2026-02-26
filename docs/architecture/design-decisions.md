# 설계 결정

Autonomous Dev Agent의 주요 아키텍처 결정과 그 이유.

---

## 1. 두뇌(Claude API)와 손발(Claude Agent SDK) 분리

**결정**: Orchestrator의 판단 로직은 `anthropic` SDK로 직접 호출하고, 실제 코딩 작업은 `claude-agent-sdk`로 실행한다.

**이유**:
- Planner, IssueClassifier처럼 JSON 응답이나 짧은 텍스트를 받는 판단 작업은 `anthropic` SDK가 더 빠르고 토큰 효율적
- 파일 읽기/쓰기, bash 실행, 코드 편집 등 실제 코딩 작업은 Claude Code의 도구 사용 능력을 활용하는 `claude-agent-sdk`가 적합
- 두 경로를 분리하면 API 키 없이 Claude Code 세션(subscription)만으로도 동작 가능 (`call_claude_for_text`의 SDK 폴백 경로)

---

## 2. 이슈 분류: 기술적 이슈는 Claude에게 묻지 않음

**결정**: 빌드 실패, 테스트 실패, 린트 에러, 타입 에러는 `IssueClassifier`가 키워드 기반으로 즉시 Non-critical로 판정하고, Claude API 호출을 생략한다.

**이유**:
- 기술적 이슈는 에이전트가 스스로 해결해야 하는 것이 이 시스템의 핵심 원칙
- Claude에게 분류를 물어보는 것 자체가 불필요한 토큰 낭비
- 키워드 매칭으로 충분히 정확하게 판별 가능

---

## 3. EventBus: asyncio.Queue 기반 단방향 발행-구독

**결정**: Orchestrator → UI 통신은 `asyncio.Queue`를 사용한 발행-구독 패턴, UI → Orchestrator 답변은 별도 `_answer_queue`로 분리.

**이유**:
- TUI의 `SpecScreen`과 `DevScreen`이 같은 이벤트를 동시에 받아야 할 때 다중 구독자 구조가 필요
- 질문(QUESTION)과 답변(answer) 채널을 분리하면 Orchestrator가 답변을 `await`할 때 다른 이벤트 발행이 블로킹되지 않음
- Textual TUI의 Worker 기반 비동기 모델과 자연스럽게 통합

---

## 4. RAG: 벡터 검색 대신 텍스트 기반 검색을 기본으로

**결정**: `CodebaseIndexer`의 기본 검색은 TF(Term Frequency) 기반 텍스트 검색이며, chromadb 벡터 검색은 선택적 의존성(`rag` extra)으로 남긴다.

**이유**:
- 코드베이스 검색에서 함수명, 클래스명, 파일명 등 정확한 키워드 매칭이 의미적 유사도보다 더 유용한 경우가 많음
- 벡터 DB(chromadb) + 임베딩 모델(sentence-transformers)은 설치 용량과 메모리가 크고, 반드시 필요하지 않음
- 텍스트 검색만으로도 에이전트가 기존 패턴을 찾는 데 충분히 효과적

---

## 5. AgentExecutor: 키워드 기반 라우팅

**결정**: task_prompt의 키워드를 분석하여 5종 에이전트 중 하나를 자동 선택. 우선순위: `architect > tester > reviewer > documenter > coder`.

**이유**:
- LLM을 사용한 에이전트 분류는 추가 API 호출 비용과 지연 발생
- task_prompt는 Planner가 명확한 키워드를 포함하여 생성하므로 키워드 매칭으로 충분히 정확
- Coder를 최하위 우선순위로 두고 기본값으로 사용하면 분류 불가 케이스를 안전하게 처리

---

## 6. ProjectState: JSON 파일 영속화

**결정**: 진행 상태를 `.claude/state.json`에 JSON으로 저장하고, 재시작 시 스펙 앞 100자로 동일성을 확인하여 이어받는다.

**이유**:
- 토큰 한도 초과 시 프로세스가 종료되므로 메모리 상태는 유지 불가
- DB, Redis 등 외부 의존성 없이 파일만으로 영속화 가능
- 100자 비교는 완전한 스펙 문자열 비교보다 빠르고, 실제 충돌 케이스를 충분히 방지

---

## 7. Verifier: Agent SDK로 검증 실행

**결정**: pytest, ruff, mypy를 직접 subprocess로 실행하지 않고, `Verifier`가 Claude Agent SDK를 통해 실행하고 결과를 JSON으로 파싱한다.

**이유**:
- Agent SDK를 통하면 도구 사용 권한 체계와 일관성 유지
- 에이전트가 검증 명령을 실행하면서 오류 메시지를 직접 보고 추가 컨텍스트를 수집할 수 있음
- `--ignore-missing-imports` 같은 플래그를 에이전트가 판단하여 유연하게 추가 가능

**단점 및 트레이드오프**:
- JSON 파싱 실패 시 기본값(0, False)으로 폴백하여 상태가 부정확해질 수 있음
- subprocess 직접 실행보다 느리고 토큰 소모 많음

---

## 8. TUI: Textual 프레임워크 선택

**결정**: 터미널 UI 프레임워크로 Textual을 사용.

**이유**:
- Python 네이티브 비동기(asyncio) 통합이 자연스러움 — Orchestrator의 `async/await`와 통합이 쉬움
- 선언적 CSS와 컴포넌트 모델로 복잡한 레이아웃(좌측 대시보드 + 우측 채팅) 구현 가능
- 터미널에서 실행되므로 원격 서버에서도 사용 가능 (웹 UI 불필요)

---

## Phase 1 RAG 재설계 설계 결정

---

## 9. AST 기반 청킹: 의미 단위 분할

**결정**: Python 파일은 `ast` 모듈로 함수·클래스·메서드 경계를 추출하여 청킹한다. 비Python 파일은 50줄 고정 + 10줄 오버랩 폴백을 유지한다.

**이유**:
- 함수나 클래스 중간에서 잘린 청크는 LLM이 컨텍스트를 파악하기 어려움
- AST로 정확한 경계(시작줄~끝줄)를 추출하면 함수 전체가 하나의 청크로 유지됨
- 데코레이터를 청크에 포함(`_decorator_start()`)하여 `@property`, `@staticmethod` 같은 의미 정보 보존

**트레이드오프**:
- Python AST만 지원 → 비Python 파일은 폴백. Go, Java AST 지원은 복잡도 대비 이득이 작음
- SyntaxError 발생 시 폴백으로 graceful 처리하여 파싱 실패가 인덱싱을 중단시키지 않음

---

## 10. Protocol 기반 인터페이스: 구조적 타이핑

**결정**: `ChunkerProtocol`, `ScorerProtocol`, `EmbeddingProtocol`은 `src/core/interfaces.py`에 정의하고, 구현체는 명시적 `implements` 없이 구조적으로 준수한다. `VectorStoreProtocol`은 `src/rag/vector_store.py` 내부에 정의한다.

**이유**:
- Python의 구조적 타이핑(structural subtyping)을 활용하면 상속 없이도 `isinstance(ASTChunker(), ChunkerProtocol) == True` 보장
- 테스트에서 Mock 객체를 Protocol 체크 없이 주입 가능 → 테스트 용이성 향상
- `@runtime_checkable`로 런타임 체크도 지원하여 디버깅 편의

---

## 11. BM25 선택: Boolean BoW 대체

**결정**: 기존 Boolean BoW(0/1 존재 여부) 대신 `rank-bm25` 라이브러리의 `BM25Okapi`를 사용한다.

**이유**:
- Boolean BoW는 희귀 키워드(`BM25Okapi`, `cosine_similarity`)와 흔한 키워드(`def`, `class`)를 동등하게 취급
- BM25의 IDF(Inverse Document Frequency)는 흔한 단어의 가중치를 낮추고 희귀 단어의 가중치를 높여 검색 정확도 향상
- `rank-bm25`는 순수 Python 라이브러리로 추가 빌드 의존성 없음

**코드 특화 토큰화**:
- camelCase 분리 (`getUserById` → `get`, `user`, `by`, `id`)
- `_`를 공백으로 치환하여 snake_case 자동 분리
- 특수문자 제거로 연산자·괄호 노이즈 제거

---

## 12. Voyage AI 임베딩: Anthropic 생태계 통합

**결정**: 벡터 임베딩 모델로 Voyage AI의 `voyage-3`를 사용한다. `VOYAGE_API_KEY` 없으면 `ANTHROPIC_API_KEY`로 폴백한다.

**이유**:
- Voyage AI는 Anthropic 투자 회사로 Claude와 통합 최적화된 임베딩 모델 제공
- `voyage-3`는 코드 검색에 최적화된 1024차원 임베딩
- `ANTHROPIC_API_KEY`로 Voyage AI API를 사용할 수 있어 추가 키 관리 부담 최소화

**SHA256 캐시 설계**:
- 텍스트 SHA256 해시를 캐시 키로 사용하여 동일 텍스트의 중복 API 호출 방지
- JSON 직렬화로 재시작 후에도 캐시 유지 → 전체 재인덱싱 시 API 호출 최소화

---

## 13. NumpyStore vs LanceDBStore: 단계적 확장

**결정**: 기본은 `NumpyStore`(인메모리 numpy), `lancedb` 설치 시 `LanceDBStore`(디스크 ANN)로 자동 전환. `create_vector_store()` 팩토리로 선택 로직 캡슐화.

**이유**:
- 소~중형 프로젝트(<10,000 청크)는 numpy 코사인 유사도 검색으로 충분히 빠름
- lancedb는 ANN 검색으로 대형 프로젝트에서 성능 우위 + 디스크 영속화
- 선택적 의존성(`uv sync --extra rag`)으로 기본 설치 용량 최소화
- `LanceDBStore` 초기화 실패 시 `NumpyStore`로 폴백하여 안정성 보장

---

## 14. 모듈 레벨 싱글톤: 재생성 방지

**결정**: `IncrementalIndexer`는 `get_indexer(project_path)` 함수로 모듈 레벨 싱글톤을 관리한다.

**이유**:
- `AgentExecutor._build_options()`는 에이전트 실행마다 호출됨
- 매번 새 인덱서를 생성하면 전체 재인덱싱 발생 → 수십 초 지연
- 싱글톤으로 동일 인덱서를 재사용하면 `update()`만 호출하면 됨

**`reset_indexer()` 제공**:
- 테스트에서 격리를 위해 싱글톤 초기화 함수를 공개 API로 제공

---

## 15. 하이브리드 검색 가중치: 0.6 BM25 + 0.4 벡터

**결정**: 기본 가중치를 BM25 0.6, 벡터 0.4로 설정한다.

**이유**:
- 코드 검색에서 함수명, 클래스명 같은 정확한 키워드 매칭(BM25)이 의미적 유사도(벡터)보다 더 중요한 경우가 많음
- 0.6/0.4 비율은 키워드 중심이지만 동의어·유사 구현도 검색 가능한 균형점
- `HybridSearcher` 생성자 파라미터로 가중치를 주입 가능하여 특수 케이스에서 조정 가능

**min-max 정규화 선택 이유**:
- BM25 점수와 코사인 유사도는 스케일이 다름 (BM25는 0~수십, 코사인은 -1~1)
- min-max 정규화로 [0, 1] 범위 통일 후 가중 합산하면 스케일 불균형 제거
