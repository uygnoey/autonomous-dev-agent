"""BM25 + 벡터 하이브리드 검색 모듈.

BM25 렉시컬 검색과 벡터 시맨틱 검색을 min-max 정규화 후 가중 합산한다.
벡터 검색 불가 시 BM25-only 모드로 자동 전환하여 graceful degradation을 보장한다.
"""

from __future__ import annotations

from src.core.domain import CodeChunk
from src.rag.embedder import AnthropicEmbedder
from src.rag.scorer import BM25Scorer
from src.rag.vector_store import VectorStoreProtocol, _chunk_id
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class HybridSearcher:
    """BM25 렉시컬 검색 + 벡터 시맨틱 검색 하이브리드 검색기.

    검색 알고리즘:
    1. BM25 over-fetch (top_k * 2)
    2. 벡터 over-fetch (embedder.is_available 시, top_k * 2)
    3. 각 결과 min-max 정규화
    4. 가중 합산: bm25_weight * bm25_norm + vector_weight * vec_norm
    5. 내림차순 정렬 → top_k 반환

    벡터 검색 불가 시 BM25 전용으로 자동 전환한다.
    """

    def __init__(
        self,
        scorer: BM25Scorer,
        store: VectorStoreProtocol,
        embedder: AnthropicEmbedder,
        bm25_weight: float = 0.6,
        vector_weight: float = 0.4,
    ) -> None:
        """
        Args:
            scorer: BM25 스코어러 (fit 완료 상태로 전달)
            store: 벡터 저장소
            embedder: 텍스트 임베딩기
            bm25_weight: BM25 결과 가중치 (기본 0.6)
            vector_weight: 벡터 결과 가중치 (기본 0.4)
        """
        self._scorer = scorer
        self._store = store
        self._embedder = embedder
        self._bm25_weight = bm25_weight
        self._vector_weight = vector_weight

    async def search(
        self,
        query: str,
        top_k: int,
        chunks: list[CodeChunk],
    ) -> list[tuple[CodeChunk, float]]:
        """하이브리드 검색을 수행한다.

        chunks는 BM25 스코어러의 fit 코퍼스와 동일한 순서여야 한다.
        엣지 케이스(빈 쿼리, 빈 청크, top_k=0)는 빈 리스트를 반환한다.

        Args:
            query: 검색 쿼리 문자열
            top_k: 반환할 최대 결과 수
            chunks: BM25 스코어러에 fit된 코퍼스와 동일 순서의 청크 목록

        Returns:
            (CodeChunk, 합산 스코어) 튜플 목록 (스코어 내림차순 정렬)
        """
        if not query.strip() or not chunks or top_k <= 0:
            return []

        over_fetch = top_k * 2

        # 1. BM25 검색
        bm25_results = self._bm25_search(query, over_fetch, chunks)

        # 2. 벡터 검색 (embedder 사용 가능 시)
        vector_results = await self._vector_search(query, over_fetch)

        # 3. min-max 정규화
        bm25_norm = _normalize_scores([s for _, s in bm25_results])
        vec_norm = _normalize_scores([s for _, s in vector_results])

        # 4. 통합 딕셔너리 구성 (chunk_id → (CodeChunk, 합산 스코어))
        combined: dict[str, tuple[CodeChunk, float]] = {}

        for (chunk, _), norm_score in zip(bm25_results, bm25_norm, strict=True):
            cid = _chunk_id(chunk)
            combined[cid] = (chunk, self._bm25_weight * norm_score)

        for (chunk, _), norm_score in zip(vector_results, vec_norm, strict=True):
            cid = _chunk_id(chunk)
            if cid in combined:
                existing_chunk, existing_score = combined[cid]
                combined[cid] = (
                    existing_chunk,
                    existing_score + self._vector_weight * norm_score,
                )
            else:
                combined[cid] = (chunk, self._vector_weight * norm_score)

        # 5. 내림차순 정렬 → top_k 반환
        sorted_results = sorted(combined.values(), key=lambda x: x[1], reverse=True)
        return sorted_results[:top_k]

    # ------------------------------------------------------------------
    # 내부 검색 메서드
    # ------------------------------------------------------------------

    def _bm25_search(
        self,
        query: str,
        k: int,
        chunks: list[CodeChunk],
    ) -> list[tuple[CodeChunk, float]]:
        """BM25 스코어러로 상위 k개 청크를 검색한다.

        scorer.top_k()가 반환하는 doc_index를 chunks 목록과 매핑한다.
        doc_index가 chunks 범위를 벗어나면 해당 항목을 건너뛴다.

        Args:
            query: 검색 쿼리
            k: over-fetch 크기
            chunks: doc_index에 대응하는 청크 목록

        Returns:
            (CodeChunk, BM25 스코어) 튜플 목록
        """
        top_indices = self._scorer.top_k(query, k)
        results: list[tuple[CodeChunk, float]] = []

        for doc_index, score in top_indices:
            if 0 <= doc_index < len(chunks):
                results.append((chunks[doc_index], score))
            else:
                logger.warning(
                    f"HybridSearcher: BM25 doc_index={doc_index}가 "
                    f"chunks 범위({len(chunks)}) 초과, 건너뜀"
                )

        return results

    async def _vector_search(
        self,
        query: str,
        k: int,
    ) -> list[tuple[CodeChunk, float]]:
        """임베딩 기반 벡터 검색을 수행한다.

        embedder.is_available이 False이면 즉시 빈 리스트를 반환한다.
        임베딩 실패 시에도 빈 리스트를 반환하여 BM25 전용 모드로 폴백한다.

        Args:
            query: 검색 쿼리
            k: over-fetch 크기

        Returns:
            (CodeChunk, 코사인 유사도) 튜플 목록. 벡터 검색 불가 시 빈 리스트.
        """
        if not self._embedder.is_available:
            return []

        try:
            query_vecs = await self._embedder.embed([query])
        except Exception as exc:
            logger.warning(f"HybridSearcher: 쿼리 임베딩 실패 ({exc}), BM25 전용 모드로 전환")
            return []

        if not query_vecs:
            return []

        return self._store.search(query_vecs[0], k)


# ------------------------------------------------------------------
# 모듈 레벨 헬퍼
# ------------------------------------------------------------------


def _normalize_scores(scores: list[float]) -> list[float]:
    """Min-max 정규화를 수행한다.

    모든 값이 동일할 때(max - min < ε)는 1.0으로 반환한다.
    빈 리스트는 빈 리스트를 반환한다.

    Args:
        scores: 정규화할 점수 목록

    Returns:
        [0.0, 1.0] 범위로 정규화된 점수 목록
    """
    if not scores:
        return []

    min_s = min(scores)
    max_s = max(scores)
    eps = 1e-9

    if max_s - min_s < eps:
        return [1.0] * len(scores)

    return [(s - min_s) / (max_s - min_s + eps) for s in scores]


