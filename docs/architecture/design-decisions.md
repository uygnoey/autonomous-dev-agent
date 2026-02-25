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
