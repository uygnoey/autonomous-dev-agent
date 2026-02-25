---
name: rag-search
description: 기존 코드베이스에서 유사 패턴이나 구현을 찾을 때 사용. 새 코드 작성 전에 기존 코드를 먼저 검색하여 일관성 유지.
allowed-tools: Bash, Read, Glob, Grep
context:
  fork: true
  agent: Explore
---

# RAG Codebase Search

## 목적
새 코드를 작성하기 전에 기존 코드베이스에서 유사한 구현을 찾아 일관성을 유지한다.

## 사용 절차
1. 새 모듈/함수를 만들기 전에, 기존 코드에서 유사 패턴 검색
2. 찾은 패턴을 참고하여 동일한 스타일로 구현
3. 기존 패턴과 다르게 구현해야 할 이유가 있으면 주석으로 설명

## 검색 방법
```bash
# 유사 클래스 구조 찾기
grep -r "class.*Service" src/ --include="*.py" -l

# 유사 패턴 찾기
grep -r "async def" src/ --include="*.py" | head -20

# Repository 구현 패턴 찾기
grep -r "class.*Repository" src/ --include="*.py" -A 5

# 에러 처리 패턴 찾기
grep -r "raise.*Error" src/ --include="*.py"

# 테스트 패턴 찾기
grep -r "async def test_" tests/ --include="*.py" | head -20
```

## 규칙
- 새 파일을 만들기 전에 반드시 기존 유사 파일을 1개 이상 확인
- 기존 패턴과 다르게 구현하면 안 됨 (명확한 이유 없이)
- 새 패턴을 도입할 때는 기존 코드도 함께 마이그레이션
