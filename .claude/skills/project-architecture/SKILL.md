---
name: project-architecture
description: 프로젝트 구조와 모듈 간 관계. 새 모듈 추가, 디렉토리 생성, 파일 배치 결정 시 참조.
---

# Project Architecture

## 기술 스택
- Language: Python 3.12+
- Orchestrator: Claude API (anthropic SDK)
- Agent Execution: Claude Agent SDK (claude_agent_sdk)
- RAG: ChromaDB + Sentence Transformers (선택) / Skills (기본)
- Testing: pytest + pytest-asyncio + pytest-cov
- Linting: ruff
- Type Checking: mypy
- Config: pydantic-settings + YAML

## 모듈 의존성 (안쪽으로만)

```
src/orchestrator/main.py
    ├── src/orchestrator/planner.py        → Claude API로 계획 수립
    ├── src/orchestrator/issue_classifier.py → Claude API로 이슈 분류
    ├── src/orchestrator/token_manager.py   → 토큰 한도 관리
    ├── src/agents/executor.py             → Agent SDK로 작업 실행
    ├── src/agents/verifier.py             → Agent SDK로 검증 실행
    ├── src/rag/mcp_server.py              → MCP RAG 서버 (선택)
    └── src/utils/state.py                 → 프로젝트 상태 관리
```

## 새 파일 추가 시 체크리스트
1. 적절한 디렉토리에 배치했는가?
2. `__init__.py`에 export 추가했는가?
3. 타입 힌트를 모두 작성했는가?
4. docstring을 작성했는가?
5. 테스트 파일을 생성했는가?
6. 기존 유사 파일의 패턴을 따랐는가?

## 설정 관리
```python
# config/settings.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    anthropic_api_key: str
    default_model: str = "claude-opus-4-6"
    subagent_model: str = "claude-sonnet-4-6"
    max_iterations: int = 500
    max_turns_per_task: int = 100
    token_wait_seconds: int = 60
    project_path: str = "."
    
    class Config:
        env_file = ".env"
```
