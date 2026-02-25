# Autonomous Development Agent — 자율 개발 에이전트

## 프로젝트 개요
상위 Orchestrator Agent가 Claude Code를 프로그래밍적으로 제어하여,
RAG 기반 코드 품질 관리 + 자율 무한 루프 개발을 수행하는 시스템.

- **Claude API**: Orchestrator의 두뇌 (계획, 판단, 이슈 분류)
- **Claude Agent SDK**: 실행 계층 (코드 작성, 테스트, 빌드)
- **RAG (Skills + MCP)**: 코드 품질과 일관된 디자인 패턴 보장

## 핵심 원칙

### 자율 루프 규칙
1. 기획/디자인/UI/UX → 사람과 논의하여 결정 (Orchestrator가 대화)
2. 스펙 확정 후 → 프로젝트 구성, 설계, 구현, 테스트 모두 자율 수행
3. **테스트 100% 통과 + 전체 기능 100% 완성**까지 무한 반복
4. 코드 완성 후 → **documenter 에이전트가 전체 문서 생성** (README, API 문서, 아키텍처 문서 등)
5. 토큰 한도 도달 시 → 리셋될 때까지 대기 후 이어서 진행
6. 크리티컬 이슈만 즉시 사람에게 질문, 나머지는 완성 후 모아서 전달

### 크리티컬 이슈 정의 (즉시 사람에게 질문)
- 스펙이 모호하여 진행 불가 (예: "로그인은 소셜만? 이메일도?")
- 외부 서비스 연동 정보 필요 (API 키, 엔드포인트 등)
- 스펙 간 모순 발견
- 보안 관련 아키텍처 결정 (인증 방식 등)

### 크리티컬이 아닌 것 (에이전트가 스스로 해결)
- 빌드 실패 → 에러 분석하고 수정 반복. 절대 사람에게 넘기지 않는다
- 테스트 실패 → 코드 수정하고 재실행. 100회든 200회든 통과할 때까지
- 린트 에러 → 자동 수정
- 타입 에러 → 자동 수정
- 의존성 충돌 → 자동 해결
- 런타임 에러 → 디버깅하고 수정
- 성능 이슈 → 최적화 시도

### 비크리티컬 질문 (완성 후 모아서 전달)
- UI 세부 조정 (색상, 간격, 폰트 등)
- 성능 최적화 선택지
- 네이밍 관련 질문
- 부가 기능 세부 구현 방식

## Agent Teams 활성화
이 프로젝트는 Agent Teams 기능을 사용합니다.
settings.json에 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` 설정 완료.

팀 구성:
- **Lead (팀 리드)**: 전체 조율, 작업 분배, 품질 검증
- **architect**: 설계, 구조 결정
- **coder**: 코드 구현
- **tester**: 테스트 작성 및 실행
- **reviewer**: 코드 리뷰, 품질 검증
- **documenter**: 결과물 문서 생성 (README, API 문서, 아키텍처 문서, CHANGELOG 등)

## 코드 품질 기준

### 읽기 쉬운 코드
- 변수명/함수명이 의도를 명확히 전달
- 함수는 단일 책임, 20줄 이내 권장
- 중첩 3단계 이하
- 매직 넘버 금지 → 상수 정의

### 일관된 디자인 패턴
- `.claude/skills/design-patterns/SKILL.md` 반드시 참조
- 같은 종류의 작업은 반드시 같은 방식으로 구현
- 새 파일 생성 시 기존 유사 파일의 구조를 먼저 확인

### 문서화
- 모든 public 함수에 docstring/JSDoc 필수
- 모듈 최상단에 목적 설명 주석
- 복잡한 로직에 why 주석 (what이 아닌 why)
- **프로젝트 완성 시 documenter 에이전트가 최종 문서 생성**:
  - README.md (설치~실행까지 완전한 가이드)
  - docs/api/ (전체 API 문서)
  - docs/architecture/ (아키텍처 개요, 데이터 모델, 설계 결정)
  - docs/setup/ (개발 환경, 배포 가이드)
  - CHANGELOG.md

### 테스트
- 모든 비즈니스 로직: 유닛 테스트 필수
- 모든 API: 통합 테스트 필수
- 커버리지 90% 이상 목표
- Edge case 테스트 포함

## 디렉토리 구조

```
autonomous-dev-agent/
├── CLAUDE.md                          ← 이 파일 (프로젝트 규칙)
├── .claude/
│   ├── settings.json                  ← Claude Code 설정 + Agent Teams 활성화
│   ├── settings.local.json            ← 로컬 설정 (git ignore)
│   ├── skills/                        ← RAG 역할의 코딩 지식
│   │   ├── design-patterns/SKILL.md
│   │   ├── code-standards/SKILL.md
│   │   ├── testing-strategy/SKILL.md
│   │   ├── error-handling/SKILL.md
│   │   ├── project-architecture/SKILL.md
│   │   └── rag-search/SKILL.md
│   └── agents/                        ← 서브에이전트 정의
│       ├── architect.md
│       ├── coder.md
│       ├── tester.md
│       ├── reviewer.md
│       └── documenter.md
├── src/
│   ├── orchestrator/                  ← 상위 Orchestrator (Claude API 사용)
│   │   ├── __init__.py
│   │   ├── main.py                    ← 메인 루프
│   │   ├── planner.py                 ← 작업 계획 수립
│   │   ├── issue_classifier.py        ← 이슈 분류 (critical/non-critical)
│   │   └── token_manager.py           ← 토큰 한도 관리 + 대기 로직
│   ├── agents/                        ← Agent SDK 래퍼
│   │   ├── __init__.py
│   │   ├── executor.py                ← Claude Agent SDK 실행기
│   │   └── verifier.py                ← 테스트/빌드 검증기
│   ├── rag/                           ← RAG 시스템 (MCP 서버)
│   │   ├── __init__.py
│   │   ├── mcp_server.py              ← MCP RAG 서버
│   │   └── indexer.py                 ← 코드베이스 인덱서
│   └── utils/
│       ├── __init__.py
│       ├── state.py                   ← 프로젝트 상태 관리
│       └── logger.py                  ← 구조화된 로깅
├── scripts/
│   ├── setup.sh                       ← 초기 환경 설정
│   └── run.sh                         ← 실행 스크립트
├── tests/
│   └── ...
├── docs/                              ← documenter 에이전트가 생성/관리
│   ├── api/                           ← API 엔드포인트 문서
│   ├── architecture/                  ← 아키텍처, 데이터모델, 설계결정
│   ├── setup/                         ← 개발환경, 배포 가이드
│   └── contributing.md                ← 기여 가이드
├── config/
│   └── default.yaml                   ← 기본 설정값
├── pyproject.toml
├── .env.example
└── .gitignore
```

## 커밋 규칙
- Conventional Commits 사용: feat:, fix:, refactor:, test:, docs:, chore:
- 기능 단위 작은 커밋
- 커밋 전 테스트 통과 필수

## 실행 명령어
- 테스트: `pytest tests/ -v --cov`
- 린트: `ruff check src/`
- 타입체크: `mypy src/`
- 실행: `python -m src.orchestrator.main`
