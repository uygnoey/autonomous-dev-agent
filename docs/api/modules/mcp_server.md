# MCP Server API

**파일**: `src/rag/mcp_server.py`

RAG MCP 서버. `claude_agent_sdk`의 `create_sdk_mcp_server`를 사용하여 인-프로세스 MCP 서버를 제공합니다. `AgentExecutor`가 이 서버를 `mcp_servers`에 추가하면 에이전트가 5종 도구를 사용할 수 있습니다.

## 팩토리 함수

### `build_rag_mcp_server(project_path) -> McpSdkServerConfig`

프로젝트 경로를 기반으로 RAG MCP 서버를 생성합니다.

```python
def build_rag_mcp_server(project_path: str) -> McpSdkServerConfig
```

**파라미터**

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `project_path` | `str` | 인덱싱할 프로젝트 루트 경로 |

**반환값**: `McpSdkServerConfig` — `ClaudeAgentOptions.mcp_servers`에 전달할 설정 객체.

**동작**: `get_indexer(project_path).index()`를 호출하여 최초 전체 인덱싱을 수행합니다. `IncrementalIndexer` 싱글톤을 공유하여 모든 도구가 동일 인덱스를 사용합니다.

**사용 예시**

```python
from src.rag.mcp_server import build_rag_mcp_server
from claude_agent_sdk import ClaudeAgentOptions, AgentExecutor

rag_server = build_rag_mcp_server("/path/to/project")

options = ClaudeAgentOptions(
    mcp_servers={"rag": rag_server},
    # ...
)
```

---

## MCP 도구 5종

### 1. `search_code`

BM25+벡터 하이브리드 검색으로 코드베이스에서 관련 코드를 검색합니다.

**입력 스키마**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|------|--------|------|
| `query` | `string` | 필수 | — | 검색 쿼리 (예: "error handling pattern") |
| `top_k` | `integer` | 선택 | `5` | 반환할 결과 수 |

**응답 예시**

```
=== 검색 결과: 'error handling' (3개) ===

--- 1. src/rag/embedder.py:174 ---
Name: _call_api_with_retry
Type: method
Content:
    async def _call_api_with_retry(self, texts: list[str]) -> list[list[float]] | None:
        ...

--- 2. src/agents/executor.py:45 ---
Name: execute_with_retry
Type: function
...
```

---

### 2. `reindex_codebase`

변경된 파일만 증분 재인덱싱합니다. 코드 수정 후 검색 결과가 오래된 경우 호출합니다.

**입력 스키마**: 파라미터 없음.

**응답 예시**

```
증분 재인덱싱 완료
  추가: 2개 파일
  수정: 1개 파일
  삭제: 0개 파일
```

---

### 3. `search_by_symbol`

코드 심볼(함수, 클래스, 메서드)을 이름으로 검색합니다.

**입력 스키마**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|------|--------|------|
| `name` | `string` | 필수 | — | 심볼 이름 (예: "get_user", "UserService") |
| `mode` | `string` | 선택 | `"contains"` | 매칭 방식: `"exact"`, `"prefix"`, `"contains"` |

**매칭 모드**

| 모드 | 설명 | 예시 (`name="get_user"`) |
|------|------|------------------------|
| `exact` | 정확히 일치 | `get_user` 만 |
| `prefix` | 접두사 일치 | `get_user`, `get_user_by_id`, `get_user_list` |
| `contains` | 포함 여부 | `get_user`, `get_user_by_id`, `admin_get_user` |

---

### 4. `get_file_structure`

프로젝트 디렉토리 트리를 텍스트로 반환합니다.

**입력 스키마**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|------|--------|------|
| `path` | `string` | 선택 | 프로젝트 루트 | 조회할 디렉토리 경로 |
| `depth` | `integer` | 선택 | `3` | 최대 탐색 깊이 |

**응답 예시**

```
autonomous-dev-agent
  src
    rag
      chunker.py
      scorer.py
      embedder.py
      vector_store.py
      hybrid_search.py
      incremental_indexer.py
      mcp_server.py
    agents
      executor.py
      verifier.py
  tests
  docs
```

`IGNORED_DIRS`(`__pycache__`, `.git`, `node_modules`, `.venv` 등)는 자동으로 제외됩니다.

---

### 5. `get_similar_patterns`

코드 스니펫과 의미적으로 유사한 코드를 임베딩 기반 벡터 검색으로 찾습니다.

**입력 스키마**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|------|--------|------|
| `code_snippet` | `string` | 필수 | — | 유사 패턴을 찾을 코드 스니펫 |
| `top_k` | `integer` | 선택 | `5` | 반환할 유사 패턴 수 |

`VOYAGE_API_KEY` 또는 `ANTHROPIC_API_KEY`가 없으면 임베딩 생성에 실패하고 오류 메시지를 반환합니다.

---

## MCP 응답 형식

모든 도구는 MCP 표준 응답 형식을 따릅니다:

```json
{
  "content": [
    {
      "type": "text",
      "text": "응답 내용..."
    }
  ]
}
```

## MCP 서버 메타데이터

| 항목 | 값 |
|------|-----|
| 서버 이름 | `"rag"` |
| 버전 | `"2.0.0"` |
| 도구 수 | 5개 |
