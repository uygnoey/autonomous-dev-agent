# RAG API

코드베이스 검색 시스템 API 문서.

---

## RAG MCP 서버

**파일**: `src/rag/mcp_server.py`

Claude Agent SDK의 in-process MCP 서버로 `search_code`, `reindex_codebase` 도구를 제공한다.

### `build_rag_mcp_server(project_path: str) -> McpSdkServerConfig`

프로젝트 경로를 기반으로 RAG MCP 서버를 생성한다.

```python
from src.rag.mcp_server import build_rag_mcp_server

rag_server = build_rag_mcp_server("/path/to/project")
options = ClaudeAgentOptions(
    mcp_servers={"rag": rag_server},
    ...
)
```

### MCP 도구: `search_code`

기존 코드베이스에서 유사 패턴을 검색한다.

**입력:**
```json
{
    "query": "error handling pattern",
    "top_k": 5
}
```

**출력:**
```
=== 검색 결과: 'error handling pattern' ===

--- 결과 1: src/agents/executor.py (L45-95) ---
<코드 내용>

--- 결과 2: src/utils/logger.py (L10-60) ---
<코드 내용>
```

### MCP 도구: `reindex_codebase`

코드 변경 후 인덱스를 갱신한다.

**입력:** 없음

**출력:** `재인덱싱 완료: 142개 청크`

---

## CodebaseIndexer

**파일**: `src/rag/indexer.py`

코드 파일을 청크로 분할하고 텍스트 기반 검색을 제공한다.

### 생성자

```python
CodebaseIndexer(
    project_path: str,
    chunk_size: int = 50,  # 청크당 최대 줄 수
)
```

### 지원 파일 확장자

`.py`, `.ts`, `.js`, `.tsx`, `.jsx`, `.go`, `.java`, `.rs`

### 무시 디렉토리

`__pycache__`, `.git`, `node_modules`, `.venv`, `venv`, `dist`, `build`

### 메서드

#### `index() -> int`

코드베이스를 인덱싱하고 청크 수를 반환한다.

```python
indexer = CodebaseIndexer("/path/to/project")
count = indexer.index()  # → 142
```

#### `search(query: str, top_k: int = 5) -> list[CodeChunk]`

쿼리에 가장 관련된 코드 청크를 반환한다. TF 점수 기반 랭킹.

```python
chunks = indexer.search("error handling", top_k=3)
for chunk in chunks:
    print(f"{chunk.file_path}:{chunk.start_line}-{chunk.end_line}")
    print(chunk.content)
```

### CodeChunk 데이터 클래스

```python
@dataclass
class CodeChunk:
    file_path: str    # 프로젝트 루트 기준 상대 경로
    content: str      # 코드 내용
    start_line: int   # 시작 줄 번호 (1-based)
    end_line: int     # 끝 줄 번호 (1-based)
```
