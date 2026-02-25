# 아키텍처 개요

Autonomous Dev Agent의 전체 시스템 구조와 모듈 간 관계.

---

## 시스템 구성

```
┌─────────────────────────────────────────────────────────────────┐
│                        사용자 인터페이스                            │
│   ┌───────────────────────────────────────────────────────┐    │
│   │  Textual TUI (src/ui/tui/)                             │    │
│   │  SpecScreen (스펙 확정) │ DevScreen (개발 대시보드)       │    │
│   └───────────────┬───────────────────────────────────────┘    │
│                   │ EventBus (양방향 비동기 통신)                  │
└───────────────────┼─────────────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────────────┐
│                     Orchestrator Layer (두뇌)                    │
│                    Claude API / SDK로 판단                        │
│                                                                  │
│   SpecBuilder → Planner → IssueClassifier → TokenManager        │
│   (스펙 확정)   (계획)      (이슈 분류)         (rate limit 관리)  │
└──────────────────────┬──────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────────┐
│                     Agent Layer (손발)                           │
│                Claude Agent SDK로 실행                           │
│                                                                  │
│   AgentExecutor ──→ architect / coder / tester                  │
│   (라우팅)           reviewer / documenter                       │
│                                                                  │
│   Verifier (pytest + ruff + mypy + build)                        │
└──────────────────────┬──────────────────────────────────────────┘
                       │ MCP 도구
┌──────────────────────▼──────────────────────────────────────────┐
│                     RAG Layer (지식)                             │
│                                                                  │
│   RAG MCP Server                                                 │
│   ├── search_code (유사 패턴 검색)                               │
│   └── reindex_codebase (인덱스 갱신)                             │
│                                                                  │
│   CodebaseIndexer (텍스트 기반 코드 인덱싱)                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 자율 루프 흐름

```
사용자가 스펙 입력
     │
     ▼
SpecBuilder (Claude와 대화 → spec.md 저장)
     │
     ▼
┌────────────────────────────────────────────────┐
│              자율 개발 루프 (최대 500회)           │
│                                                │
│  1. Planner.decide_next_task(state)            │
│         ↓ (Claude API: 다음 작업 결정)           │
│  2. AgentExecutor.execute(task)                │
│         ↓ (Claude Agent SDK: 코드 작성)          │
│  3. Verifier.verify_all()                      │
│         ↓ (pytest + ruff + mypy + build)       │
│  4. IssueClassifier.classify(verification)     │
│         ↓ (Critical? → 즉시 질문 / Non? → 보류) │
│  5. state.update(verification)                 │
│         ↓                                      │
│  완성 조건 충족? ──No──→ 루프 반복               │
│         │ Yes                                  │
└─────────┼──────────────────────────────────────┘
          │
          ▼
Documenter Agent (README, API 문서, CHANGELOG 생성)
          │
          ▼
완성 보고 + 비크리티컬 질문 전달
```

---

## 완성 조건

| 항목 | 기준 |
|------|------|
| 테스트 통과율 | 100% |
| 린트 에러 | 0건 |
| 타입 에러 | 0건 |
| 빌드 | 성공 |

---

## 모듈 의존성

```
src/
├── orchestrator/           # 두뇌 계층
│   ├── main.py            ←── agents/, utils/
│   ├── planner.py         ←── utils/claude_client
│   ├── issue_classifier.py←── utils/claude_client
│   ├── spec_builder.py    ←── utils/claude_client, utils/events
│   └── token_manager.py   ←── anthropic (외부)
│
├── agents/                 # 실행 계층
│   ├── executor.py        ←── claude_agent_sdk (외부), rag/mcp_server
│   └── verifier.py        ←── claude_agent_sdk (외부)
│
├── rag/                    # 지식 계층
│   ├── mcp_server.py      ←── claude_agent_sdk (외부), rag/indexer
│   └── indexer.py         (외부 의존성 없음)
│
├── ui/tui/                 # 표현 계층
│   ├── app.py             ←── orchestrator/main, orchestrator/spec_builder, utils/events
│   └── __main__.py        ←── ui/tui/app
│
└── utils/                  # 공통 유틸
    ├── events.py           (외부 의존성 없음)
    ├── state.py            (외부 의존성 없음)
    ├── claude_client.py   ←── anthropic, claude_agent_sdk (외부)
    └── logger.py           (외부 의존성 없음)
```

**의존성 방향 규칙**: 바깥 레이어 → 안쪽 레이어 (단방향)
- `ui` → `orchestrator` → `agents` → `rag`
- 모든 레이어 → `utils`
- `rag`, `utils`는 다른 내부 모듈에 의존하지 않음

---

## 이벤트 플로우

```
Orchestrator                EventBus                  TUI
     │                          │                       │
     │── publish(LOG) ─────────►│── get() ─────────────►│ 로그 표시
     │── publish(PROGRESS) ─────►│── get() ─────────────►│ 진행률 업데이트
     │── publish(QUESTION) ─────►│── get() ─────────────►│ 입력 활성화
     │                           │◄── put_answer() ───────│ 사용자 입력
     │◄── wait_for_answer() ─────│                        │
     │── publish(COMPLETED) ─────►│── get() ─────────────►│ 완성 보고
```
