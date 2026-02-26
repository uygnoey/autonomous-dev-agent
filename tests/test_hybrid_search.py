"""HybridSearcher 유닛 테스트.

테스트 대상: src/rag/hybrid_search.py — HybridSearcher 클래스, _normalize_scores(), _chunk_id()
커버리지 목표: 100%

테스트 케이스:
1. BM25-only 모드 (embedder.is_available = False)
2. Hybrid 모드 (BM25 + 벡터 결합)
3. Min-max 정규화 정확도
4. Graceful degradation (embedder 실패 시 BM25 fallback)
5. Edge cases (빈 쿼리, top_k=0, 빈 chunks)
6. 점수 조합 정확도 (가중치 적용, 순위 정렬)
7. Chunk deduplication (중복 제거, 최고 점수 보존)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.domain import CodeChunk
from src.rag.hybrid_search import HybridSearcher, _chunk_id, _normalize_scores


# ---------------------------------------------------------------------------
# 공통 픽스처
# ---------------------------------------------------------------------------

def _make_chunk(file_path: str, start_line: int = 1, name: str = "f") -> CodeChunk:
    """테스트용 CodeChunk를 생성하는 헬퍼."""
    return CodeChunk(
        file_path=file_path,
        content=f"def {name}(): pass",
        start_line=start_line,
        end_line=start_line,
        chunk_type="function",
        name=name,
    )


@pytest.fixture
def mock_scorer() -> MagicMock:
    """BM25Scorer mock 픽스처."""
    scorer = MagicMock()
    scorer.top_k.return_value = []
    return scorer


@pytest.fixture
def mock_store() -> MagicMock:
    """VectorStore mock 픽스처."""
    store = MagicMock()
    store.search.return_value = []
    return store


@pytest.fixture
def mock_embedder() -> MagicMock:
    """AnthropicEmbedder mock 픽스처."""
    embedder = MagicMock()
    embedder.is_available = True
    embedder.embed = AsyncMock(return_value=[[1.0, 0.0, 0.0]])
    return embedder


@pytest.fixture
def searcher(
    mock_scorer: MagicMock,
    mock_store: MagicMock,
    mock_embedder: MagicMock,
) -> HybridSearcher:
    """기본 HybridSearcher 픽스처 (bm25_weight=0.6, vector_weight=0.4)."""
    return HybridSearcher(
        scorer=mock_scorer,
        store=mock_store,
        embedder=mock_embedder,
        bm25_weight=0.6,
        vector_weight=0.4,
    )


@pytest.fixture
def sample_chunks() -> list[CodeChunk]:
    """테스트용 청크 목록 픽스처."""
    return [
        _make_chunk("a.py", 1, "func_a"),
        _make_chunk("b.py", 1, "func_b"),
        _make_chunk("c.py", 1, "func_c"),
    ]


# ---------------------------------------------------------------------------
# 1. BM25-only 모드 테스트
# ---------------------------------------------------------------------------

class TestBM25OnlyMode:
    """embedder.is_available = False 시 BM25만 사용하는 테스트."""

    @pytest.mark.asyncio
    async def test_bm25_only_when_embedder_unavailable(
        self,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        sample_chunks: list[CodeChunk],
    ) -> None:
        """embedder 비활성화 시 BM25 결과만 반환하는지 검증."""
        # Arrange
        mock_embedder = MagicMock()
        mock_embedder.is_available = False
        mock_scorer.top_k.return_value = [(0, 2.5), (1, 1.0)]

        searcher = HybridSearcher(mock_scorer, mock_store, mock_embedder)

        # Act
        results = await searcher.search("query", top_k=2, chunks=sample_chunks)

        # Assert: BM25 결과 2개 반환, store.search 미호출
        assert len(results) == 2
        mock_store.search.assert_not_called()
        mock_embedder.embed.assert_not_called() if hasattr(mock_embedder, "embed") else None

    @pytest.mark.asyncio
    async def test_bm25_only_returns_correct_chunk_order(
        self,
        mock_store: MagicMock,
        sample_chunks: list[CodeChunk],
    ) -> None:
        """BM25-only 모드에서 점수 내림차순으로 정렬되는지 검증."""
        # Arrange — chunk b(index 1)가 더 높은 BM25 점수
        mock_scorer = MagicMock()
        mock_scorer.top_k.return_value = [(1, 5.0), (0, 1.0)]

        mock_embedder = MagicMock()
        mock_embedder.is_available = False

        searcher = HybridSearcher(mock_scorer, mock_store, mock_embedder)

        # Act
        results = await searcher.search("query", top_k=2, chunks=sample_chunks)

        # Assert: b.py가 첫 번째 (더 높은 BM25 점수)
        assert len(results) == 2
        assert results[0][0].file_path == "b.py"
        assert results[1][0].file_path == "a.py"

    @pytest.mark.asyncio
    async def test_bm25_only_score_uses_bm25_weight(
        self,
        mock_store: MagicMock,
        sample_chunks: list[CodeChunk],
    ) -> None:
        """BM25-only 모드에서 단일 결과의 점수가 bm25_weight인지 검증.

        단일 점수는 min-max 정규화 시 1.0이 되므로
        최종 점수 = bm25_weight * 1.0 = bm25_weight.
        """
        # Arrange
        mock_scorer = MagicMock()
        mock_scorer.top_k.return_value = [(0, 3.0)]  # 단일 결과

        mock_embedder = MagicMock()
        mock_embedder.is_available = False

        searcher = HybridSearcher(mock_scorer, mock_store, mock_embedder, bm25_weight=0.6)

        # Act
        results = await searcher.search("query", top_k=1, chunks=sample_chunks)

        # Assert: 점수 = 0.6 * 1.0 = 0.6
        assert len(results) == 1
        assert abs(results[0][1] - 0.6) < 1e-9

    @pytest.mark.asyncio
    async def test_bm25_out_of_range_index_skipped(
        self,
        mock_store: MagicMock,
        sample_chunks: list[CodeChunk],
    ) -> None:
        """BM25 doc_index가 chunks 범위를 벗어나면 건너뛰는지 검증."""
        # Arrange
        mock_scorer = MagicMock()
        # index 99는 범위 초과, index 0은 유효
        mock_scorer.top_k.return_value = [(99, 5.0), (0, 2.0)]

        mock_embedder = MagicMock()
        mock_embedder.is_available = False

        searcher = HybridSearcher(mock_scorer, mock_store, mock_embedder)

        # Act
        results = await searcher.search("query", top_k=5, chunks=sample_chunks)

        # Assert: 유효한 index 0만 반환
        assert len(results) == 1
        assert results[0][0].file_path == "a.py"


# ---------------------------------------------------------------------------
# 2. Hybrid 모드 테스트
# ---------------------------------------------------------------------------

class TestHybridMode:
    """BM25 + 벡터 결과를 모두 활용하는 하이브리드 모드 테스트."""

    @pytest.mark.asyncio
    async def test_hybrid_combines_bm25_and_vector_results(
        self,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
        sample_chunks: list[CodeChunk],
    ) -> None:
        """BM25와 벡터 결과가 합산되는지 검증."""
        # Arrange — BM25: a.py, 벡터: b.py
        mock_scorer.top_k.return_value = [(0, 3.0)]
        mock_store.search.return_value = [(sample_chunks[1], 0.9)]

        searcher = HybridSearcher(mock_scorer, mock_store, mock_embedder)

        # Act
        results = await searcher.search("query", top_k=5, chunks=sample_chunks)

        # Assert: 두 결과 모두 포함
        file_paths = {r[0].file_path for r in results}
        assert "a.py" in file_paths
        assert "b.py" in file_paths

    @pytest.mark.asyncio
    async def test_hybrid_chunk_present_in_both_gets_combined_score(
        self,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
        sample_chunks: list[CodeChunk],
    ) -> None:
        """BM25와 벡터 결과에 모두 있는 청크가 합산 점수를 받는지 검증."""
        # Arrange — a.py가 양쪽에 모두 등장
        mock_scorer.top_k.return_value = [(0, 3.0)]
        mock_store.search.return_value = [(sample_chunks[0], 0.9)]

        searcher = HybridSearcher(
            mock_scorer, mock_store, mock_embedder,
            bm25_weight=0.6, vector_weight=0.4,
        )

        # Act
        results = await searcher.search("query", top_k=1, chunks=sample_chunks)

        # Assert: 단일 청크, 점수 = 0.6*1.0 + 0.4*1.0 = 1.0
        assert len(results) == 1
        assert results[0][0].file_path == "a.py"
        assert abs(results[0][1] - 1.0) < 1e-9

    @pytest.mark.asyncio
    async def test_hybrid_vector_only_chunk_gets_vector_weight(
        self,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
        sample_chunks: list[CodeChunk],
    ) -> None:
        """벡터 결과에만 있는 청크가 vector_weight 점수를 받는지 검증."""
        # Arrange — BM25: a.py만, 벡터: b.py만
        mock_scorer.top_k.return_value = [(0, 3.0)]
        mock_store.search.return_value = [(sample_chunks[1], 0.9)]

        searcher = HybridSearcher(
            mock_scorer, mock_store, mock_embedder,
            bm25_weight=0.6, vector_weight=0.4,
        )

        # Act
        results = await searcher.search("query", top_k=5, chunks=sample_chunks)

        # b.py는 벡터 결과만 있으므로 점수 = 0.4 * 1.0 = 0.4
        b_result = next(r for r in results if r[0].file_path == "b.py")
        assert abs(b_result[1] - 0.4) < 1e-9

    @pytest.mark.asyncio
    async def test_hybrid_calls_embed_with_query(
        self,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
        sample_chunks: list[CodeChunk],
    ) -> None:
        """hybrid 모드에서 쿼리를 임베딩하는지 검증."""
        # Arrange
        mock_scorer.top_k.return_value = []
        mock_store.search.return_value = []

        searcher = HybridSearcher(mock_scorer, mock_store, mock_embedder)

        # Act
        await searcher.search("my query", top_k=3, chunks=sample_chunks)

        # Assert: embed가 쿼리로 호출됨
        mock_embedder.embed.assert_called_once_with(["my query"])

    @pytest.mark.asyncio
    async def test_hybrid_top_k_limits_final_results(
        self,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
        sample_chunks: list[CodeChunk],
    ) -> None:
        """top_k보다 많은 결과가 있어도 top_k개만 반환하는지 검증."""
        # Arrange — BM25 3개, 벡터 3개
        mock_scorer.top_k.return_value = [(0, 3.0), (1, 2.0), (2, 1.0)]
        mock_store.search.return_value = [
            (sample_chunks[0], 0.9),
            (sample_chunks[1], 0.8),
            (sample_chunks[2], 0.7),
        ]

        searcher = HybridSearcher(mock_scorer, mock_store, mock_embedder)

        # Act
        results = await searcher.search("query", top_k=2, chunks=sample_chunks)

        # Assert: top_k=2이므로 2개만 반환
        assert len(results) == 2


# ---------------------------------------------------------------------------
# 3. Min-max 정규화 테스트
# ---------------------------------------------------------------------------

class TestNormalizeScores:
    """_normalize_scores() 헬퍼 함수 테스트."""

    def test_normalize_empty_returns_empty(self) -> None:
        """빈 리스트 정규화 시 빈 리스트를 반환하는지 검증."""
        assert _normalize_scores([]) == []

    def test_normalize_single_score_returns_one(self) -> None:
        """단일 점수는 1.0으로 정규화되는지 검증 (max == min 케이스)."""
        result = _normalize_scores([5.0])
        assert result == [1.0]

    def test_normalize_all_same_scores_returns_ones(self) -> None:
        """모든 점수가 동일할 때 1.0 리스트를 반환하는지 검증."""
        result = _normalize_scores([3.0, 3.0, 3.0])
        assert result == [1.0, 1.0, 1.0]

    def test_normalize_range_is_zero_to_one(self) -> None:
        """정규화 후 최솟값이 ~0.0, 최댓값이 ~1.0인지 검증."""
        scores = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = _normalize_scores(scores)

        assert abs(result[0] - 0.0) < 1e-6   # 최솟값 → 0
        assert abs(result[-1] - 1.0) < 1e-6  # 최댓값 → 1

    def test_normalize_preserves_order(self) -> None:
        """정규화 후에도 원래 순서가 유지되는지 검증."""
        scores = [5.0, 1.0, 3.0]
        result = _normalize_scores(scores)

        # 5.0 > 3.0 > 1.0 순서 유지
        assert result[0] > result[2] > result[1]

    def test_normalize_two_scores(self) -> None:
        """두 점수 정규화 시 [0, 1] 범위인지 검증."""
        result = _normalize_scores([0.0, 10.0])
        assert abs(result[0] - 0.0) < 1e-6
        assert abs(result[1] - 1.0) < 1e-6

    def test_normalize_negative_scores(self) -> None:
        """음수 점수도 올바르게 정규화되는지 검증."""
        scores = [-2.0, 0.0, 2.0]
        result = _normalize_scores(scores)

        assert abs(result[0] - 0.0) < 1e-6
        assert abs(result[2] - 1.0) < 1e-6
        assert 0.0 < result[1] < 1.0


# ---------------------------------------------------------------------------
# 4. Graceful degradation 테스트
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    """embedder/벡터 검색 실패 시 BM25 fallback 동작 테스트."""

    @pytest.mark.asyncio
    async def test_embed_exception_falls_back_to_bm25(
        self,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        sample_chunks: list[CodeChunk],
    ) -> None:
        """embed() 예외 시 BM25 결과만 반환하는지 검증."""
        # Arrange — embed가 예외를 발생시킴
        mock_embedder = MagicMock()
        mock_embedder.is_available = True
        mock_embedder.embed = AsyncMock(side_effect=Exception("network error"))

        mock_scorer.top_k.return_value = [(0, 3.0)]

        searcher = HybridSearcher(mock_scorer, mock_store, mock_embedder)

        # Act
        results = await searcher.search("query", top_k=2, chunks=sample_chunks)

        # Assert: BM25 결과는 반환됨, store.search 미호출
        assert len(results) == 1
        assert results[0][0].file_path == "a.py"
        mock_store.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_embed_returns_empty_vector_falls_back_to_bm25(
        self,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        sample_chunks: list[CodeChunk],
    ) -> None:
        """embed()가 빈 리스트를 반환할 때 BM25 결과만 반환하는지 검증."""
        # Arrange — embed가 빈 리스트 반환
        mock_embedder = MagicMock()
        mock_embedder.is_available = True
        mock_embedder.embed = AsyncMock(return_value=[])

        mock_scorer.top_k.return_value = [(1, 2.5)]

        searcher = HybridSearcher(mock_scorer, mock_store, mock_embedder)

        # Act
        results = await searcher.search("query", top_k=2, chunks=sample_chunks)

        # Assert: BM25 결과만 반환, store.search 미호출
        assert len(results) == 1
        assert results[0][0].file_path == "b.py"
        mock_store.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_bm25_and_vector_both_empty_returns_empty(
        self,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
        sample_chunks: list[CodeChunk],
    ) -> None:
        """BM25와 벡터 모두 결과 없을 때 빈 리스트를 반환하는지 검증."""
        # Arrange
        mock_scorer.top_k.return_value = []
        mock_store.search.return_value = []

        searcher = HybridSearcher(mock_scorer, mock_store, mock_embedder)

        # Act
        results = await searcher.search("query", top_k=5, chunks=sample_chunks)

        # Assert
        assert results == []


# ---------------------------------------------------------------------------
# 5. Edge cases 테스트
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """빈 쿼리, top_k=0, 빈 chunks 등 엣지 케이스 테스트."""

    @pytest.mark.asyncio
    async def test_empty_query_returns_empty(
        self,
        searcher: HybridSearcher,
        sample_chunks: list[CodeChunk],
    ) -> None:
        """빈 쿼리 시 빈 리스트를 반환하는지 검증."""
        results = await searcher.search("", top_k=5, chunks=sample_chunks)
        assert results == []

    @pytest.mark.asyncio
    async def test_whitespace_only_query_returns_empty(
        self,
        searcher: HybridSearcher,
        sample_chunks: list[CodeChunk],
    ) -> None:
        """공백만 있는 쿼리 시 빈 리스트를 반환하는지 검증."""
        results = await searcher.search("   \t\n  ", top_k=5, chunks=sample_chunks)
        assert results == []

    @pytest.mark.asyncio
    async def test_top_k_zero_returns_empty(
        self,
        searcher: HybridSearcher,
        sample_chunks: list[CodeChunk],
    ) -> None:
        """top_k=0 시 빈 리스트를 반환하는지 검증."""
        results = await searcher.search("query", top_k=0, chunks=sample_chunks)
        assert results == []

    @pytest.mark.asyncio
    async def test_top_k_negative_returns_empty(
        self,
        searcher: HybridSearcher,
        sample_chunks: list[CodeChunk],
    ) -> None:
        """top_k 음수 시 빈 리스트를 반환하는지 검증."""
        results = await searcher.search("query", top_k=-1, chunks=sample_chunks)
        assert results == []

    @pytest.mark.asyncio
    async def test_empty_chunks_returns_empty(
        self,
        searcher: HybridSearcher,
    ) -> None:
        """빈 chunks 리스트 시 빈 리스트를 반환하는지 검증."""
        results = await searcher.search("query", top_k=5, chunks=[])
        assert results == []

    @pytest.mark.asyncio
    async def test_top_k_larger_than_results_returns_all(
        self,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
        sample_chunks: list[CodeChunk],
    ) -> None:
        """top_k가 실제 결과보다 클 때 전체를 반환하는지 검증."""
        # Arrange — BM25 결과 1개
        mock_scorer.top_k.return_value = [(0, 3.0)]
        mock_store.search.return_value = []

        searcher = HybridSearcher(mock_scorer, mock_store, mock_embedder)

        # Act
        results = await searcher.search("query", top_k=100, chunks=sample_chunks)

        # Assert: 실제 1개만 반환
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_edge_cases_do_not_call_scorer(
        self,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
        sample_chunks: list[CodeChunk],
    ) -> None:
        """엣지 케이스 조건(빈 쿼리)에서 scorer.top_k가 호출되지 않는지 검증."""
        # Arrange
        searcher = HybridSearcher(mock_scorer, mock_store, mock_embedder)

        # Act
        await searcher.search("", top_k=5, chunks=sample_chunks)

        # Assert: 조기 반환이므로 scorer 호출 안 됨
        mock_scorer.top_k.assert_not_called()


# ---------------------------------------------------------------------------
# 6. 점수 조합 정확도 테스트
# ---------------------------------------------------------------------------

class TestScoreCombinationAccuracy:
    """가중치 적용 및 합산 점수 정확도 테스트."""

    @pytest.mark.asyncio
    async def test_custom_weights_applied_correctly(
        self,
        mock_store: MagicMock,
        sample_chunks: list[CodeChunk],
    ) -> None:
        """커스텀 가중치(bm25=0.8, vector=0.2)가 정확히 적용되는지 검증."""
        # Arrange — a.py만 BM25에 등장 (단일 → 정규화 점수 1.0)
        mock_scorer = MagicMock()
        mock_scorer.top_k.return_value = [(0, 5.0)]
        mock_store.search.return_value = []

        mock_embedder = MagicMock()
        mock_embedder.is_available = False

        searcher = HybridSearcher(
            mock_scorer, mock_store, mock_embedder,
            bm25_weight=0.8, vector_weight=0.2,
        )

        # Act
        results = await searcher.search("query", top_k=1, chunks=sample_chunks)

        # Assert: 점수 = 0.8 * 1.0 = 0.8
        assert len(results) == 1
        assert abs(results[0][1] - 0.8) < 1e-9

    @pytest.mark.asyncio
    async def test_results_sorted_by_combined_score_descending(
        self,
        mock_store: MagicMock,
        sample_chunks: list[CodeChunk],
    ) -> None:
        """최종 결과가 합산 점수 내림차순으로 정렬되는지 검증."""
        # Arrange — BM25: a(높음), b(낮음)
        mock_scorer = MagicMock()
        mock_scorer.top_k.return_value = [(0, 10.0), (1, 1.0)]
        mock_store.search.return_value = []

        mock_embedder = MagicMock()
        mock_embedder.is_available = False

        searcher = HybridSearcher(mock_scorer, mock_store, mock_embedder)

        # Act
        results = await searcher.search("query", top_k=2, chunks=sample_chunks)

        # Assert: a.py가 먼저 (높은 BM25 점수)
        assert results[0][0].file_path == "a.py"
        assert results[1][0].file_path == "b.py"
        assert results[0][1] > results[1][1]

    @pytest.mark.asyncio
    async def test_vector_weight_can_elevate_rank(
        self,
        mock_store: MagicMock,
        sample_chunks: list[CodeChunk],
    ) -> None:
        """벡터 점수가 높은 청크가 BM25 결과보다 상위로 올라갈 수 있는지 검증.

        a.py: BM25 high(1.0 normalized) → 0.6*1.0 = 0.6
        b.py: BM25 low(0.0 normalized) + vector high(1.0 normalized) → 0.6*0 + 0.4*1.0 = 0.4
        → a.py가 여전히 상위이므로, vector_weight=1.0으로 설정해야 b.py가 역전
        """
        # Arrange — vector_weight=1.0, bm25_weight=0.0 → 벡터 결과만 영향
        mock_scorer = MagicMock()
        mock_scorer.top_k.return_value = [(0, 3.0), (1, 1.0)]
        mock_store.search.return_value = [(sample_chunks[1], 0.99)]  # b.py 높은 벡터 점수

        mock_embedder = MagicMock()
        mock_embedder.is_available = True
        mock_embedder.embed = AsyncMock(return_value=[[1.0, 0.0]])

        searcher = HybridSearcher(
            mock_scorer, mock_store, mock_embedder,
            bm25_weight=0.0, vector_weight=1.0,
        )

        # Act
        results = await searcher.search("query", top_k=2, chunks=sample_chunks)

        # Assert: 벡터만 사용이므로 b.py(벡터 결과)가 상위
        assert results[0][0].file_path == "b.py"

    @pytest.mark.asyncio
    async def test_bm25_normalized_scores_affect_ranking(
        self,
        mock_store: MagicMock,
        sample_chunks: list[CodeChunk],
    ) -> None:
        """BM25 정규화 점수가 랭킹에 영향을 주는지 검증.

        두 청크: a(10.0), b(1.0)
        정규화 후: a(~1.0), b(~0.0)
        최종 점수: a(0.6*1.0=0.6) > b(0.6*0.0≈0.0)
        """
        # Arrange
        mock_scorer = MagicMock()
        mock_scorer.top_k.return_value = [(0, 10.0), (1, 1.0)]
        mock_store.search.return_value = []

        mock_embedder = MagicMock()
        mock_embedder.is_available = False

        searcher = HybridSearcher(mock_scorer, mock_store, mock_embedder, bm25_weight=0.6)

        # Act
        results = await searcher.search("query", top_k=2, chunks=sample_chunks)

        # Assert: a.py 점수 > b.py 점수
        a_score = next(r[1] for r in results if r[0].file_path == "a.py")
        b_score = next(r[1] for r in results if r[0].file_path == "b.py")
        assert a_score > b_score


# ---------------------------------------------------------------------------
# 7. Chunk deduplication 테스트
# ---------------------------------------------------------------------------

class TestChunkDeduplication:
    """중복 chunk_id 제거 및 점수 합산 테스트."""

    @pytest.mark.asyncio
    async def test_same_chunk_in_both_results_not_duplicated(
        self,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
        sample_chunks: list[CodeChunk],
    ) -> None:
        """BM25와 벡터에 동일 청크가 있을 때 결과에 1개만 나오는지 검증."""
        # Arrange — a.py가 BM25와 벡터 양쪽에 등장
        mock_scorer.top_k.return_value = [(0, 3.0)]
        mock_store.search.return_value = [(sample_chunks[0], 0.9)]

        searcher = HybridSearcher(mock_scorer, mock_store, mock_embedder)

        # Act
        results = await searcher.search("query", top_k=5, chunks=sample_chunks)

        # Assert: a.py가 1번만 등장
        a_results = [r for r in results if r[0].file_path == "a.py"]
        assert len(a_results) == 1

    @pytest.mark.asyncio
    async def test_duplicate_chunk_score_is_sum_of_both(
        self,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
        sample_chunks: list[CodeChunk],
    ) -> None:
        """중복 청크의 점수가 BM25 + 벡터 점수의 합인지 검증."""
        # Arrange — a.py가 양쪽에 단일 결과로 등장
        mock_scorer.top_k.return_value = [(0, 5.0)]       # BM25: a.py
        mock_store.search.return_value = [(sample_chunks[0], 0.8)]  # 벡터: a.py

        searcher = HybridSearcher(
            mock_scorer, mock_store, mock_embedder,
            bm25_weight=0.6, vector_weight=0.4,
        )

        # Act
        results = await searcher.search("query", top_k=1, chunks=sample_chunks)

        # Assert: 단일 청크, 점수 = 0.6*1.0 + 0.4*1.0 = 1.0
        assert len(results) == 1
        assert results[0][0].file_path == "a.py"
        assert abs(results[0][1] - 1.0) < 1e-9

    @pytest.mark.asyncio
    async def test_chunk_id_based_on_file_path_and_start_line(
        self,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """같은 파일 다른 start_line은 별개 청크로 처리되는지 검증."""
        # Arrange — 같은 파일 다른 라인 청크 2개
        chunk_line1 = _make_chunk("same.py", 1, "func1")
        chunk_line10 = _make_chunk("same.py", 10, "func2")
        chunks = [chunk_line1, chunk_line10]

        mock_scorer.top_k.return_value = [(0, 3.0), (1, 2.0)]
        mock_store.search.return_value = []

        mock_embedder.is_available = False

        searcher = HybridSearcher(mock_scorer, mock_store, mock_embedder)

        # Act
        results = await searcher.search("query", top_k=5, chunks=chunks)

        # Assert: 2개 별개 청크 (start_line이 다름)
        assert len(results) == 2
        start_lines = {r[0].start_line for r in results}
        assert 1 in start_lines
        assert 10 in start_lines


# ---------------------------------------------------------------------------
# 8. _chunk_id 헬퍼 함수 테스트
# ---------------------------------------------------------------------------

class TestChunkId:
    """_chunk_id() 헬퍼 함수 테스트."""

    def test_chunk_id_format(self) -> None:
        """_chunk_id가 "file_path:start_line" 형식인지 검증."""
        chunk = _make_chunk("src/main.py", 42)
        assert _chunk_id(chunk) == "src/main.py:42"

    def test_chunk_id_unique_for_different_files(self) -> None:
        """다른 파일의 청크는 다른 ID를 가지는지 검증."""
        chunk_a = _make_chunk("a.py", 1)
        chunk_b = _make_chunk("b.py", 1)
        assert _chunk_id(chunk_a) != _chunk_id(chunk_b)

    def test_chunk_id_unique_for_different_start_lines(self) -> None:
        """같은 파일 다른 start_line은 다른 ID를 가지는지 검증."""
        chunk1 = _make_chunk("file.py", 1)
        chunk10 = _make_chunk("file.py", 10)
        assert _chunk_id(chunk1) != _chunk_id(chunk10)

    def test_chunk_id_same_for_identical_chunk(self) -> None:
        """동일한 속성의 청크는 같은 ID를 가지는지 검증."""
        chunk1 = _make_chunk("file.py", 5)
        chunk2 = _make_chunk("file.py", 5)
        assert _chunk_id(chunk1) == _chunk_id(chunk2)
