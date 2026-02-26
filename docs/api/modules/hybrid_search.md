# HybridSearcher API

**파일**: `src/rag/hybrid_search.py`

BM25 + 벡터 하이브리드 검색 모듈. BM25 렉시컬 검색과 벡터 시맨틱 검색을 min-max 정규화 후 가중 합산합니다. 벡터 검색 불가 시 BM25-only 모드로 자동 전환하여 graceful degradation을 보장합니다.

## 클래스

### `HybridSearcher`

BM25 렉시컬 검색 + 벡터 시맨틱 검색 하이브리드 검색기.

#### 생성자

```python
def __init__(
    self,
    scorer: BM25Scorer,
    store: VectorStoreProtocol,
    embedder: AnthropicEmbedder,
    bm25_weight: float = 0.6,
    vector_weight: float = 0.4,
) -> None
```

**파라미터**

| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| `scorer` | `BM25Scorer` | — | BM25 스코어러 (fit 완료 상태로 전달) |
| `store` | `VectorStoreProtocol` | — | 벡터 저장소 |
| `embedder` | `AnthropicEmbedder` | — | 텍스트 임베딩기 |
| `bm25_weight` | `float` | `0.6` | BM25 결과 가중치 |
| `vector_weight` | `float` | `0.4` | 벡터 결과 가중치 |

#### 메서드

##### `search(query, top_k, chunks) -> list[tuple[CodeChunk, float]]`

하이브리드 검색을 수행합니다.

```python
async def search(
    self,
    query: str,
    top_k: int,
    chunks: list[CodeChunk],
) -> list[tuple[CodeChunk, float]]
```

**파라미터**

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `query` | `str` | 검색 쿼리 문자열 |
| `top_k` | `int` | 반환할 최대 결과 수 |
| `chunks` | `list[CodeChunk]` | BM25 스코어러에 fit된 코퍼스와 동일 순서의 청크 목록 |

`chunks`는 `BM25Scorer.fit()` 시 전달한 문서와 동일한 순서여야 합니다.

**반환값**

`list[tuple[CodeChunk, float]]` — `(청크, 합산 스코어)` 튜플 목록 (스코어 내림차순 정렬).

**엣지 케이스**

- 빈 쿼리, 빈 청크, `top_k <= 0`: 빈 리스트 반환
- `embedder.is_available=False`: BM25-only 모드 자동 전환

## 검색 알고리즘

```
1. BM25 over-fetch:   scorer.top_k(query, top_k * 2)
2. 벡터 over-fetch:   embedder.embed([query]) → store.search(vec, top_k * 2)
                      (embedder.is_available=True 시에만)
3. min-max 정규화:    각 결과 세트를 [0.0, 1.0]으로 정규화
4. 가중 합산:
   - BM25 결과: combined[chunk_id] += bm25_weight * bm25_norm_score
   - 벡터 결과: combined[chunk_id] += vector_weight * vec_norm_score
   - 동일 청크: 두 점수를 누적 합산
5. 내림차순 정렬 → top_k 반환
```

## min-max 정규화

**모듈 레벨 함수**: `_normalize_scores(scores: list[float]) -> list[float]`

```
normalized[i] = (score[i] - min) / (max - min + ε)
```

- 모든 값이 동일할 때(`max - min < 1e-9`): 모든 값을 `1.0`으로 반환
- 빈 리스트: 빈 리스트 반환

## graceful degradation

| 상황 | 동작 |
|------|------|
| `embedder.is_available=False` | 벡터 검색 건너뜀, BM25-only 모드 |
| 쿼리 임베딩 실패 | 경고 로그, BM25-only 모드로 폴백 |
| BM25 doc_index 범위 초과 | 해당 결과 건너뜀, 경고 로그 |

## 사용 예시

```python
import asyncio
from src.rag.chunker import ASTChunker
from src.rag.scorer import BM25Scorer
from src.rag.embedder import AnthropicEmbedder
from src.rag.vector_store import create_vector_store
from src.rag.hybrid_search import HybridSearcher

async def main():
    chunker = ASTChunker()
    scorer = BM25Scorer()
    store = create_vector_store()
    embedder = AnthropicEmbedder()

    # 청킹 및 인덱싱
    with open("src/rag/scorer.py") as f:
        chunks = chunker.chunk("src/rag/scorer.py", f.read())

    texts = [c.content for c in chunks]
    scorer.fit(texts)

    if embedder.is_available:
        embeddings = await embedder.embed(texts)
        store.add(chunks, embeddings)

    # 하이브리드 검색
    searcher = HybridSearcher(scorer, store, embedder)
    results = await searcher.search("BM25 tokenize", top_k=3, chunks=chunks)

    for chunk, score in results:
        print(f"{chunk.file_path}:{chunk.start_line} [{chunk.chunk_type}] score={score:.4f}")

asyncio.run(main())
```

## 가중치 조정 가이드

| 사용 사례 | 권장 가중치 |
|---------|------------|
| 기본 (기호/키워드 중심) | `bm25=0.6, vector=0.4` |
| 의미적 유사성 중심 | `bm25=0.3, vector=0.7` |
| API 키 없는 환경 | BM25-only (자동 전환) |
