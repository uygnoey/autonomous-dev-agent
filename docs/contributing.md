# Contributing Guide

## 개발 환경 설정

```bash
git clone <repo>
cd autonomous-dev-agent
uv sync --extra dev
cp .env.example .env  # ANTHROPIC_API_KEY 입력
```

## 브랜치 전략

- `main`: 안정 버전
- `feat/<기능>`: 기능 추가
- `fix/<이슈>`: 버그 수정

## 테스트

```bash
uv run pytest tests/ -v --cov=src
uv run ruff check src/
uv run mypy src/
```

모든 PR은 테스트 100% 통과 + 린트/타입 오류 0개 기준.

## 커밋 메시지

Conventional Commits 사용:

```
feat: 새 기능
fix: 버그 수정
refactor: 코드 개선 (기능 변경 없음)
test: 테스트 추가/수정
docs: 문서 수정
chore: 빌드/설정 변경
```

## 코드 스타일

- [`.claude/skills/code-standards/SKILL.md`](.claude/skills/code-standards/SKILL.md) 참조
- 새 파일 추가 시 [`design-patterns/SKILL.md`](.claude/skills/design-patterns/SKILL.md) 먼저 확인
- 모든 public 함수에 docstring 필수

## 아키텍처

- [`docs/architecture/overview.md`](architecture/overview.md): 전체 구조
- [`docs/architecture/design-decisions.md`](architecture/design-decisions.md): 주요 설계 결정
