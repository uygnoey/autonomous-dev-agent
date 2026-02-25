# Autonomous Development Agent — 자율 개발 에이전트

Claude API로 판단하고, Claude Agent SDK로 실행하는 자율 무한 루프 개발 시스템.

**[English README](README_EN.md)**

## 개요

스펙을 입력하면, 에이전트가 테스트 100% 통과 + 전체 기능 완성까지 스스로 개발합니다.

```
사람 (스펙 입력)
    ↓
Orchestrator
    ├── Planner      ← Claude API (두뇌: 다음 작업 결정)
    ├── Executor     ← Claude Agent SDK (손발: 코드 작성)
    ├── Verifier     ← Claude Agent SDK (검증: 테스트/린트/타입)
    ├── Classifier   ← Claude API (판단: Critical vs Non-Critical)
    └── RAG MCP      ← 코드베이스 패턴 검색 (일관성 보장)
```

## 핵심 동작 방식

1. **스펙 확정** — 사람과 논의 후 `spec.md`에 작성
2. **자율 루프** — Orchestrator가 반복:
   - Planner가 다음 작업 결정
   - Executor가 코드 작성/수정
   - Verifier가 pytest + ruff + mypy 검증
   - 실패 시 스스로 수정, 사람에게 묻지 않음
3. **문서화** — 완성 후 documenter 에이전트가 자동 생성

## 설치

### 요구사항
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) 패키지 매니저
- `ANTHROPIC_API_KEY` 환경변수

### 환경 설정

```bash
# 저장소 클론
git clone <repo-url>
cd autonomous-dev-agent

# 가상환경 생성 및 의존성 설치
uv venv .venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"

# 환경변수 설정
cp .env.example .env
# .env 파일에 ANTHROPIC_API_KEY 입력
```

## 사용법

### 1. 스펙 작성

`spec.md`에 개발할 프로젝트 스펙을 작성합니다:

```markdown
## 기능 요구사항
1. 사용자 등록/로그인 (이메일+패스워드)
2. TODO 항목 CRUD
...

## 기술 스택
- Python 3.12
- FastAPI
- PostgreSQL
```

### 2. 에이전트 실행

```bash
python -m src.orchestrator.main spec.md
```

에이전트가 자동으로:
- 프로젝트 구조 생성
- 기능 구현
- 테스트 작성 및 실행
- 린트/타입 에러 수정
- 완성 후 문서 생성

### 3. 완성 보고

모든 테스트 통과 후 완성 보고와 함께 비크리티컬 질문 목록이 전달됩니다.

## 개발

```bash
# 테스트 실행
pytest tests/ -v --cov=src

# 린트
ruff check src/

# 타입 체크
mypy src/
```

## 프로젝트 구조

```
autonomous-dev-agent/
├── src/
│   ├── orchestrator/         # 자율 루프 두뇌
│   │   ├── main.py           # 메인 루프
│   │   ├── planner.py        # 다음 작업 결정 (Claude API)
│   │   ├── issue_classifier.py  # Critical/Non-Critical 분류
│   │   └── token_manager.py  # Rate limit 대기 로직
│   ├── agents/               # Agent SDK 실행 계층
│   │   ├── executor.py       # 코드 작성/수정 실행
│   │   └── verifier.py       # 테스트/린트/타입 검증
│   ├── rag/                  # RAG 코드 검색 시스템
│   │   ├── indexer.py        # 코드베이스 인덱서
│   │   └── mcp_server.py     # MCP 서버 (search_code 도구)
│   └── utils/
│       ├── state.py          # 프로젝트 상태 (재개 지원)
│       └── logger.py         # 구조화된 로깅
├── .claude/
│   ├── skills/               # RAG용 코딩 가이드라인
│   └── agents/               # 서브에이전트 정의
├── tests/                    # 유닛/통합 테스트
├── config/default.yaml       # 기본 설정
└── spec.md                   # 개발할 프로젝트 스펙
```

## 이슈 분류 규칙

| 구분 | 처리 방식 |
|------|-----------|
| 스펙 모호, 외부 API 키 필요, 스펙 모순, 보안 결정 | **즉시 사람에게 질문** |
| 빌드 실패, 테스트 실패, 린트/타입 에러 | **에이전트가 스스로 해결** |
| UI 세부 조정, 네이밍, 성능 최적화 방향 | **완성 후 모아서 전달** |

## 라이선스

MIT
