# Phase 1 모듈 API 요약

Phase 1에서 구현된 7개 모듈의 공개 API 빠른 참조 문서입니다.
각 모듈의 상세 API는 `docs/api/modules/` 디렉토리를 참조하세요.

---

## 1. ASTChunker (`src/rag/chunker.py`)

```python
from src.rag.chunker import ASTChunker

chunker = ASTChunker()

# 파일 청킹
chunks: list[CodeChunk] = chunker.chunk(
    file_path="src/rag/scorer.py",  # 확장자로 처리 방식 결정
    content="...",                   # 파일 텍스트
)

# 클래스 속성
ASTChunker.MIN_LINES  # = 5   (5줄 미만 함수 → module 청크에 병합)
ASTChunker.MAX_LINES  # = 100 (100줄 초과 ClassDef → 메서드별 서브청킹)
ASTChunker.BLOCK_SIZE # = 50  (비Python 파일 블록 크기)
ASTChunker.OVERLAP    # = 10  (비Python 파일 오버랩 줄 수)
```

**chunk_type 값**: `"function"` | `"class"` | `"method"` | `"module"` | `"block"`

---

## 2. BM25Scorer (`src/rag/scorer.py`)

```python
from src.rag.scorer import BM25Scorer

scorer = BM25Scorer()

# 학습 (코퍼스 변경 시 재호출)
scorer.fit(documents=["def func(): ...", "class Foo: ..."])

# 단일 문서 스코어
score: float = scorer.score(query="get user", doc_index=0)

# 상위 k개 결과 [(doc_index, score), ...]
results: list[tuple[int, float]] = scorer.top_k(query="user", k=5)

# 클래스 속성
BM25Scorer.K1  # = 1.5 (단어 빈도 포화점)
BM25Scorer.B   # = 0.75 (문서 길이 정규화)
```

---

## 3. AnthropicEmbedder (`src/rag/embedder.py`)

```python
from src.rag.embedder import AnthropicEmbedder

embedder = AnthropicEmbedder(
    cache_path=".rag_cache/embeddings.json"  # 기본값
)

# 가용 여부 확인
available: bool = embedder.is_available

# 임베딩 (비동기)
vectors: list[list[float]] = await embedder.embed(
    texts=["def func(): ...", "class Foo: ..."]
)

# 클래스 속성
AnthropicEmbedder.BATCH_SIZE  # = 96 (Voyage AI API 배치 제한)
```

**인증**: `VOYAGE_API_KEY` → `ANTHROPIC_API_KEY` 환경변수 순서로 시도.

---

## 4. VectorStore (`src/rag/vector_store.py`)

```python
from src.rag.vector_store import create_vector_store, VectorStoreProtocol

# 팩토리 (lancedb 설치 여부에 따라 자동 선택)
store: NumpyStore | LanceDBStore = create_vector_store()

# 청크 추가
store.add(chunks=list[CodeChunk], embeddings=list[list[float]])

# 유사도 검색
results: list[tuple[CodeChunk, float]] = store.search(
    query_embedding=list[float],
    top_k=5,
)

# 파일 청크 삭제 (증분 인덱싱용)
store.remove(file_path="src/rag/scorer.py")

# 전체 초기화
store.clear()

# NumpyStore 전용
numpy_store.size  # 저장된 청크 수
```

**Protocol 체크**: `isinstance(store, VectorStoreProtocol)` → True

---

## 5. HybridSearcher (`src/rag/hybrid_search.py`)

```python
from src.rag.hybrid_search import HybridSearcher

searcher = HybridSearcher(
    scorer=scorer,           # BM25Scorer (fit 완료)
    store=store,             # VectorStoreProtocol
    embedder=embedder,       # AnthropicEmbedder
    bm25_weight=0.6,         # 기본값
    vector_weight=0.4,       # 기본값
)

# 하이브리드 검색 (비동기)
results: list[tuple[CodeChunk, float]] = await searcher.search(
    query="BM25 tokenize",
    top_k=5,
    chunks=list[CodeChunk],  # BM25 fit() 코퍼스와 동일 순서
)
```

**알고리즘**: BM25 over-fetch(top_k*2) + 벡터 over-fetch(top_k*2) → min-max 정규화 → 가중 합산 → 정렬 → top_k 반환.

---

## 6. IncrementalIndexer (`src/rag/incremental_indexer.py`)

```python
from src.rag.incremental_indexer import get_indexer, reset_indexer

# 싱글톤 인스턴스
indexer = get_indexer(project_path="/path/to/project")

# 전체 인덱싱
chunk_count: int = indexer.index()

# 증분 업데이트
counts: dict[str, int] = indexer.update()
# counts = {"added": n, "updated": n, "removed": n}

# 검색 (비동기)
chunks: list[CodeChunk] = await indexer.search(query="BM25", top_k=5)

# 전체 청크 목록
all_chunks: list[CodeChunk] = indexer.all_chunks

# 싱글톤 초기화 (테스트용)
reset_indexer()
```

**캐시 위치**: `{project_path}/.rag_cache/`

**파일 필터**:
- 지원: `.py .ts .js .tsx .jsx .go .java .rs .yaml .yml .md`
- 제외 디렉토리: `__pycache__ .git node_modules .venv venv dist build .rag_cache`

---

## 7. MCP Server (`src/rag/mcp_server.py`)

```python
from src.rag.mcp_server import build_rag_mcp_server
from claude_agent_sdk import ClaudeAgentOptions

# MCP 서버 생성 (최초 인덱싱 포함)
rag_server = build_rag_mcp_server(project_path="/path/to/project")

# AgentExecutor에 전달
options = ClaudeAgentOptions(
    mcp_servers={"rag": rag_server},
    ...
)
```

**제공 도구 5종**:

| 도구명 | 파라미터 | 설명 |
|--------|---------|------|
| `search_code` | `query: str, top_k: int = 5` | BM25+벡터 하이브리드 검색 |
| `reindex_codebase` | 없음 | 증분 재인덱싱 |
| `search_by_symbol` | `name: str, mode: str = "contains"` | 심볼 이름 검색 |
| `get_file_structure` | `path: str = "", depth: int = 3` | 디렉토리 트리 |
| `get_similar_patterns` | `code_snippet: str, top_k: int = 5` | 유사 코드 검색 |

**MCP 응답 형식**: `{"content": [{"type": "text", "text": "..."}]}`

---

## 데이터 타입

```python
from src.core.domain import CodeChunk
from dataclasses import dataclass

@dataclass
class CodeChunk:
    file_path: str       # 상대 파일 경로 (프로젝트 루트 기준)
    content: str         # 청크 텍스트 내용
    start_line: int      # 시작 줄 번호 (1-indexed)
    end_line: int        # 끝 줄 번호 (1-indexed)
    chunk_type: str      # "function" | "class" | "method" | "module" | "block"
    name: str | None     # 함수/클래스 이름, 없으면 None
```

---

## 전체 파이프라인 예시

```python
import asyncio
from src.rag.chunker import ASTChunker
from src.rag.scorer import BM25Scorer
from src.rag.embedder import AnthropicEmbedder
from src.rag.vector_store import create_vector_store
from src.rag.hybrid_search import HybridSearcher
from src.rag.incremental_indexer import get_indexer, reset_indexer

async def main():
    # 싱글톤 인덱서 사용 (권장)
    indexer = get_indexer("/path/to/project")
    count = indexer.index()
    print(f"인덱싱된 청크: {count}개")

    results = await indexer.search("BM25 scoring function", top_k=5)
    for chunk in results:
        print(f"{chunk.file_path}:{chunk.start_line} [{chunk.chunk_type}] {chunk.name}")

    # 코드 수정 후 증분 업데이트
    counts = indexer.update()
    print(f"업데이트: {counts}")

asyncio.run(main())
```
