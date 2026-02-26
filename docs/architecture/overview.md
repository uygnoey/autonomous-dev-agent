# 시스템 아키텍처 개요

Autonomous Dev Agent의 전체 시스템 구조와 모듈 간 관계.

---

## Phase 1 RAG 시스템 아키텍처

### 개요

Phase 1은 Autonomous Dev Agent의 RAG(Retrieval-Augmented Generation) 시스템을 전면 재설계한 결과물입니다. 에이전트가 코드를 작성할 때 기존 코드베이스에서 관련 패턴을 검색하여 일관성을 유지하는 데 사용됩니다.

### Phase 0 대비 개선

| 항목 | Phase 0 (이전) | Phase 1 (현재) |
|------|---------------|---------------|
| 청킹 | 50줄 고정 슬라이싱 | AST 경계 기반 (함수·클래스·메서드·모듈) |
| 검색 알고리즘 | Boolean BoW (0/1 존재 여부) | BM25 TF-IDF + 벡터 코사인 유사도 하이브리드 |
| 인덱싱 전략 | 매번 전체 재인덱싱 O(n) | mtime 기반 증분 인덱싱 O(변경분) |
| MCP 도구 | 2개 | 5개 |
| 벡터 검색 | 없음 | Voyage AI 임베딩 + NumpyStore/LanceDBStore |

---

## 전체 구조도

```
┌─────────────────────────────────────────────────────────────────────┐
│  MCP Layer  (src/rag/mcp_server.py)                                 │
│                                                                     │
│  search_code          reindex_codebase      search_by_symbol        │
│  get_file_structure   get_similar_patterns                          │
└────────────────────────────┬────────────────────────────────────────┘
                             │ 위임
┌────────────────────────────▼────────────────────────────────────────┐
│  IncrementalIndexer  (src/rag/incremental_indexer.py)               │
│                                                                     │
│  index()  ·  update()  ·  search(query, top_k)  ·  all_chunks      │
│                                                                     │
│  싱글톤 패턴: get_indexer(project_path)                               │
└────────┬───────────────────┬─────────────────────────┬─────────────┘
         │                   │                         │
┌────────▼──────┐  ┌─────────▼──────────────┐   .rag_cache/
│  ASTChunker   │  │  HybridSearcher         │   ├── file_index.json
│  (chunker.py) │  │  (hybrid_search.py)     │   ├── bm25_index.pkl
│               │  │                         │   └── embeddings.json
│  .chunk()     │  │  .search(query, top_k,  │
└────────┬──────┘  │         chunks)         │
         │         └──────┬──────────┬───────┘
         │                │          │
┌────────▼──────┐  ┌──────▼───┐  ┌──▼────────────────────────────────┐
│  CodeChunk    │  │ BM25     │  │  AnthropicEmbedder                  │
│  (domain.py)  │  │ Scorer   │  │  (embedder.py)                      │
│               │  │ scorer.py│  │                                     │
│  file_path    │  │          │  │  .embed(texts) → list[list[float]]  │
│  content      │  │  .fit()  │  │  .is_available → bool               │
│  start_line   │  │  .score()│  │  SHA256 캐시                        │
│  end_line     │  │  .top_k()│  │  지수 백오프 재시도                   │
│  chunk_type   │  └──────────┘  └──────────────────┬────────────────┘
│  name         │                                   │
└───────────────┘         ┌────────────────────────▼────────────────┐
                          │  VectorStore  (vector_store.py)           │
                          │                                           │
                          │  NumpyStore   │  LanceDBStore             │
                          │  (인메모리)   │  (디스크, ANN)            │
                          │                                           │
                          │  .add(chunks, embeddings)                 │
                          │  .search(query_vec, top_k)                │
                          │  .remove(file_path)                       │
                          └──────────────────────────────────────────┘
```

---

## 모듈 구성

| 모듈 | 파일 | 역할 |
|------|------|------|
| `ASTChunker` | `src/rag/chunker.py` | Python AST 파싱 → CodeChunk 생성 |
| `BM25Scorer` | `src/rag/scorer.py` | rank-bm25 기반 IDF 스코어링 |
| `AnthropicEmbedder` | `src/rag/embedder.py` | Voyage AI 임베딩 + SHA256 캐시 |
| `VectorStore` | `src/rag/vector_store.py` | 벡터 저장 + 코사인 유사도 검색 |
| `HybridSearcher` | `src/rag/hybrid_search.py` | BM25 + 벡터 가중 결합 |
| `IncrementalIndexer` | `src/rag/incremental_indexer.py` | mtime 기반 증분 인덱싱 + 싱글톤 |
| `MCP Server` | `src/rag/mcp_server.py` | 에이전트에게 노출하는 MCP 도구 5종 |

---

## 데이터 흐름

### 최초 인덱싱

```
build_rag_mcp_server(project_path)
    → get_indexer(project_path)  [싱글톤 생성]
    → indexer.index()

index():
    store.clear()
    _collect_files()             [SUPPORTED_EXTENSIONS 파일 수집, IGNORED_DIRS 제외]
    for file in files:
        _chunk_file(file)        [ASTChunker.chunk(path, content)]
    _fit_and_embed(all_chunks):
        BM25Scorer.fit(texts)    [BM25 인덱스 학습]
        AnthropicEmbedder.embed(texts)   [Voyage AI API 배치 호출, SHA256 캐시]
        VectorStore.add(chunks, embeddings)
    _save_file_index(file_index) [.rag_cache/file_index.json 저장]
    _save_bm25_index()           [.rag_cache/bm25_index.pkl 저장]
```

### 증분 업데이트

```
indexer.update()
    _detect_changes():
        current = {path: path.stat().st_mtime for path in _collect_files()}
        cached = _load_file_index()
        new_files = [p for p in current if p not in cached]
        modified_files = [p for p in current if p in cached and mtime 변경]
        deleted_files = [p for p in cached if p not in current]

    삭제 파일: store.remove() + all_chunks 갱신
    수정 파일: store.remove() + 재청킹 + 재임베딩 + store.add()
    신규 파일: 청킹 + 임베딩 + store.add()

    변경 있으면:
        BM25Scorer.fit(all_chunk_texts)  [전체 문서로 BM25 재학습]
        _save_file_index() + _save_bm25_index()
```

### 검색

```
indexer.search(query, top_k)
    HybridSearcher.search(query, top_k, all_chunks)

        BM25 over-fetch: scorer.top_k(query, top_k * 2)
        벡터 over-fetch: embedder.embed([query]) → store.search(vec, top_k * 2)

        min-max 정규화 후 가중 합산:
            score = 0.6 * bm25_norm + 0.4 * vec_norm

        내림차순 정렬 → top_k 반환
```

---

## 모듈 간 의존성

```
core/interfaces.py (ChunkerProtocol, ScorerProtocol, EmbeddingProtocol)
    ↑ 구조적 준수 (isinstance 체크)
    │
    ├── chunker.py        → core/domain.py (CodeChunk)
    ├── scorer.py         → rank-bm25 (BM25Okapi)
    ├── embedder.py       → httpx (Voyage AI API)
    ├── vector_store.py   → numpy, [lancedb 선택], core/domain.py
    ├── hybrid_search.py  → scorer.py, vector_store.py, embedder.py
    ├── incremental_indexer.py → chunker.py, scorer.py, vector_store.py,
    │                            hybrid_search.py, embedder.py
    └── mcp_server.py     → incremental_indexer.py, claude_agent_sdk
```

모든 의존성은 단방향 하향입니다. 순환 참조가 없습니다.

---

## 오류 처리 및 Graceful Degradation

| 상황 | 처리 방식 |
|------|----------|
| Python SyntaxError | 폴백: 50줄 고정 블록 청킹 |
| Voyage AI API 실패 | 3회 재시도 후 BM25-only 모드 |
| LanceDBStore 초기화 실패 | NumpyStore로 자동 폴백 |
| 파일 읽기 실패 | 경고 로그, 해당 파일 건너뜀 |
| BM25 빈 쿼리 | 빈 리스트 반환 |
| 캐시 파일 손상 | 빈 딕셔너리로 시작, 재인덱싱 |

---

## 성능 특성

| 지표 | Phase 0 | Phase 1 |
|------|---------|---------|
| 증분 인덱싱 (변경 없음) | ~2s (전체 재스캔) | <0.1s (mtime 비교만) |
| 증분 인덱싱 (파일 1개 수정) | ~2s (전체 재인덱싱) | 해당 파일만 재처리 |
| 검색 정확도 | Boolean BoW (0/1) | BM25 IDF 가중치 + 벡터 유사도 |
| 대형 프로젝트 검색 | 인메모리 스캔 | LanceDBStore ANN 검색 (선택) |

---

## 전체 시스템 구조 (Orchestrator + RAG)

```
사용자 스펙 입력
    │
    ▼
AutonomousOrchestrator (src/orchestrator/main.py)
    │ Planner → 다음 작업 결정
    │ IssueClassifier → critical/non-critical 분류
    ▼
AgentExecutor (src/agents/executor.py)
    │ 키워드 분석 → architect/coder/tester/reviewer/documenter 라우팅
    │ Claude Agent SDK로 서브에이전트 실행
    │ MCP 서버 연결
    ▼
RAG MCP Server (src/rag/mcp_server.py)
    │ 5종 도구로 코드 검색 지원
    ▼
IncrementalIndexer → HybridSearcher
    │
    ├── BM25Scorer (렉시컬)
    └── VectorStore + AnthropicEmbedder (시맨틱)
```
