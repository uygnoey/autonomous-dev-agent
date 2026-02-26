# RAG API 문서 인덱스

Phase 1 RAG 시스템의 7개 모듈 API 레퍼런스.

## 모듈 목록

| 모듈 | 파일 | 주요 클래스 | 문서 |
|------|------|------------|------|
| ASTChunker | `src/rag/chunker.py` | `ASTChunker` | [chunker.md](modules/chunker.md) |
| BM25Scorer | `src/rag/scorer.py` | `BM25Scorer` | [scorer.md](modules/scorer.md) |
| AnthropicEmbedder | `src/rag/embedder.py` | `AnthropicEmbedder` | [embedder.md](modules/embedder.md) |
| VectorStore | `src/rag/vector_store.py` | `NumpyStore`, `LanceDBStore`, `VectorStoreProtocol` | [vector_store.md](modules/vector_store.md) |
| HybridSearcher | `src/rag/hybrid_search.py` | `HybridSearcher` | [hybrid_search.md](modules/hybrid_search.md) |
| IncrementalIndexer | `src/rag/incremental_indexer.py` | `IncrementalIndexer` | [incremental_indexer.md](modules/incremental_indexer.md) |
| MCP Server | `src/rag/mcp_server.py` | `build_rag_mcp_server` | [mcp_server.md](modules/mcp_server.md) |

## 모듈 의존성 그래프

```
core/domain.py (CodeChunk)
    ↑
    ├── chunker.py (ASTChunker)
    │
    ├── vector_store.py (NumpyStore / LanceDBStore)
    │       ↑
    │   scorer.py (BM25Scorer) ←──────────────────────┐
    │       ↑                                          │
    │   embedder.py (AnthropicEmbedder)                │
    │       ↑                                          │
    └── hybrid_search.py (HybridSearcher) ─────────────┘
            ↑
        incremental_indexer.py (IncrementalIndexer)
            ↑
        mcp_server.py (build_rag_mcp_server)
```

모든 의존성은 단방향 하향입니다. 순환 참조가 없습니다.

## 데이터 흐름 요약

### 인덱싱

```
프로젝트 파일
    → IncrementalIndexer.index()
    → ASTChunker.chunk(file_path, content) → list[CodeChunk]
    → BM25Scorer.fit(texts)
    → AnthropicEmbedder.embed(texts) → list[list[float]]
    → VectorStore.add(chunks, embeddings)
    → .rag_cache/ 저장
```

### 검색

```
query
    → IncrementalIndexer.search(query, top_k)
    → HybridSearcher.search(query, top_k, chunks)
        → BM25Scorer.top_k(query, k*2) → [(doc_index, score), ...]
        → AnthropicEmbedder.embed([query]) → [vector]
        → VectorStore.search(query_vector, k*2) → [(CodeChunk, similarity), ...]
        → min-max 정규화 + 가중 합산
    → list[CodeChunk]
```

## 주요 타입

```python
from src.core.domain import CodeChunk

@dataclass
class CodeChunk:
    file_path: str       # 상대 파일 경로
    content: str         # 청크 텍스트 내용
    start_line: int      # 시작 줄 번호 (1-indexed)
    end_line: int        # 끝 줄 번호 (1-indexed)
    chunk_type: str      # "function" | "class" | "method" | "module" | "block"
    name: str | None     # 함수/클래스명, 없으면 None
```
