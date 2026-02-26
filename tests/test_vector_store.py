"""VectorStore 유닛 테스트.

테스트 대상: src/rag/vector_store.py — NumpyStore, LanceDBStore, create_vector_store()
커버리지 목표: 90% 이상

테스트 케이스:
1. NumpyStore add/search
2. 코사인 유사도 정확도
3. remove() 후 결과
4. 빈 스토어
5. 길이 불일치 ValueError
6. clear()
7. LanceDB mock (create_vector_store 팩토리)
"""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.core.domain import CodeChunk
from src.rag.vector_store import NumpyStore, VectorStoreProtocol, _chunk_id, create_vector_store


# ---------------------------------------------------------------------------
# 공통 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture
def numpy_store() -> NumpyStore:
    """빈 NumpyStore 픽스처."""
    return NumpyStore()


@pytest.fixture
def sample_chunks() -> list[CodeChunk]:
    """테스트용 CodeChunk 목록 픽스처."""
    return [
        CodeChunk(
            file_path="test1.py",
            content="def foo(): pass",
            start_line=1,
            end_line=1,
            chunk_type="function",
            name="foo",
        ),
        CodeChunk(
            file_path="test2.py",
            content="def bar(): pass",
            start_line=1,
            end_line=1,
            chunk_type="function",
            name="bar",
        ),
    ]


@pytest.fixture
def sample_embeddings() -> list[list[float]]:
    """테스트용 임베딩 벡터 픽스처 (직교 벡터)."""
    return [
        [1.0, 0.0, 0.0],  # x축
        [0.0, 1.0, 0.0],  # y축 (test1과 직교)
    ]


# ---------------------------------------------------------------------------
# 1. NumpyStore add/search 테스트
# ---------------------------------------------------------------------------

class TestNumpyStoreAddAndSearch:
    """NumpyStore의 add()와 search() 기본 동작 테스트."""

    def test_add_and_search_returns_matching_chunk(
        self,
        numpy_store: NumpyStore,
        sample_chunks: list[CodeChunk],
        sample_embeddings: list[list[float]],
    ) -> None:
        """add() 후 search()로 정확한 청크가 조회되는지 검증."""
        # Arrange
        numpy_store.add(sample_chunks, sample_embeddings)

        # Act — 첫 번째 청크와 동일한 임베딩으로 검색
        results = numpy_store.search(sample_embeddings[0], top_k=1)

        # Assert
        assert len(results) == 1
        chunk, score = results[0]
        assert chunk.file_path == sample_chunks[0].file_path
        assert score > 0.99  # 동일 벡터 → 코사인 유사도 ~1.0

    def test_search_returns_top_k_results(
        self,
        numpy_store: NumpyStore,
        sample_chunks: list[CodeChunk],
        sample_embeddings: list[list[float]],
    ) -> None:
        """top_k 개수만큼 결과를 반환하는지 검증."""
        # Arrange
        numpy_store.add(sample_chunks, sample_embeddings)

        # Act
        results = numpy_store.search(sample_embeddings[0], top_k=2)

        # Assert: 스토어에 2개 있으므로 2개 반환
        assert len(results) == 2

    def test_search_results_sorted_by_similarity_descending(
        self,
        numpy_store: NumpyStore,
        sample_chunks: list[CodeChunk],
        sample_embeddings: list[list[float]],
    ) -> None:
        """검색 결과가 유사도 내림차순으로 정렬되는지 검증."""
        # Arrange
        numpy_store.add(sample_chunks, sample_embeddings)

        # Act
        results = numpy_store.search(sample_embeddings[0], top_k=2)

        # Assert: 첫 번째 결과가 더 높은 유사도
        assert results[0][1] >= results[1][1]

    def test_size_increases_after_add(
        self,
        numpy_store: NumpyStore,
        sample_chunks: list[CodeChunk],
        sample_embeddings: list[list[float]],
    ) -> None:
        """add() 후 size 프로퍼티가 증가하는지 검증."""
        # Arrange
        assert numpy_store.size == 0

        # Act
        numpy_store.add(sample_chunks, sample_embeddings)

        # Assert
        assert numpy_store.size == 2

    def test_add_multiple_times_accumulates(
        self,
        numpy_store: NumpyStore,
        sample_chunks: list[CodeChunk],
        sample_embeddings: list[list[float]],
    ) -> None:
        """add()를 여러 번 호출하면 청크가 누적되는지 검증."""
        # Arrange
        numpy_store.add(sample_chunks, sample_embeddings)
        extra_chunks = [
            CodeChunk(
                file_path="test3.py",
                content="def baz(): pass",
                start_line=1,
                end_line=1,
                chunk_type="function",
                name="baz",
            )
        ]
        extra_embeddings = [[0.0, 0.0, 1.0]]

        # Act
        numpy_store.add(extra_chunks, extra_embeddings)

        # Assert: 총 3개
        assert numpy_store.size == 3

    def test_search_result_is_tuple_of_chunk_and_float(
        self,
        numpy_store: NumpyStore,
        sample_chunks: list[CodeChunk],
        sample_embeddings: list[list[float]],
    ) -> None:
        """검색 결과가 (CodeChunk, float) 튜플인지 검증."""
        # Arrange
        numpy_store.add(sample_chunks, sample_embeddings)

        # Act
        results = numpy_store.search(sample_embeddings[0], top_k=1)

        # Assert
        assert len(results) == 1
        chunk, score = results[0]
        assert isinstance(chunk, CodeChunk)
        assert isinstance(score, float)


# ---------------------------------------------------------------------------
# 2. 코사인 유사도 정확도 테스트
# ---------------------------------------------------------------------------

class TestCosineSimilarityAccuracy:
    """코사인 유사도 수치 정확도 테스트."""

    def test_identical_vector_similarity_is_one(self, numpy_store: NumpyStore) -> None:
        """동일 벡터 간 코사인 유사도가 1.0인지 검증."""
        # Arrange
        chunk = CodeChunk(
            file_path="a.py",
            content="pass",
            start_line=1,
            end_line=1,
            chunk_type="function",
            name="a",
        )
        vec = [1.0, 0.0, 0.0]
        numpy_store.add([chunk], [vec])

        # Act
        results = numpy_store.search(vec, top_k=1)

        # Assert: 유사도 ~1.0
        assert len(results) == 1
        assert abs(results[0][1] - 1.0) < 1e-9

    def test_orthogonal_vectors_similarity_is_zero(self, numpy_store: NumpyStore) -> None:
        """직교 벡터 간 코사인 유사도가 0.0인지 검증."""
        # Arrange
        chunk1 = CodeChunk(
            file_path="a.py", content="pass", start_line=1, end_line=1,
            chunk_type="function", name="a",
        )
        chunk2 = CodeChunk(
            file_path="b.py", content="pass", start_line=1, end_line=1,
            chunk_type="function", name="b",
        )
        vec1 = [1.0, 0.0, 0.0]  # x축
        vec2 = [0.0, 1.0, 0.0]  # y축 (직교)

        numpy_store.add([chunk1, chunk2], [vec1, vec2])

        # Act — vec1로 검색
        results = numpy_store.search(vec1, top_k=2)

        # Assert: chunk1 유사도 ~1.0, chunk2 유사도 ~0.0
        assert abs(results[0][1] - 1.0) < 0.01
        assert abs(results[1][1] - 0.0) < 0.01

    def test_similar_vectors_ranked_correctly(self, numpy_store: NumpyStore) -> None:
        """더 유사한 벡터가 더 낮은 벡터보다 높은 순위인지 검증."""
        # Arrange — 쿼리에 가까운 벡터와 먼 벡터
        chunk_close = CodeChunk(
            file_path="close.py", content="pass", start_line=1, end_line=1,
            chunk_type="function", name="close",
        )
        chunk_far = CodeChunk(
            file_path="far.py", content="pass", start_line=1, end_line=1,
            chunk_type="function", name="far",
        )
        # 쿼리 [1, 0]에 가까운 벡터 [0.9, 0.1], 먼 벡터 [0.1, 0.9]
        vec_close = [0.9, 0.1]
        vec_far = [0.1, 0.9]
        query = [1.0, 0.0]

        numpy_store.add([chunk_close, chunk_far], [vec_close, vec_far])

        # Act
        results = numpy_store.search(query, top_k=2)

        # Assert: close가 먼저
        assert results[0][0].file_path == "close.py"
        assert results[0][1] > results[1][1]

    def test_zero_query_vector_returns_empty(self, numpy_store: NumpyStore) -> None:
        """쿼리 벡터가 영벡터일 때 빈 리스트를 반환하는지 검증."""
        # Arrange
        chunk = CodeChunk(
            file_path="a.py", content="pass", start_line=1, end_line=1,
            chunk_type="function", name="a",
        )
        numpy_store.add([chunk], [[1.0, 0.0]])

        # Act — 영벡터 쿼리
        results = numpy_store.search([0.0, 0.0], top_k=1)

        # Assert
        assert results == []

    def test_zero_stored_vector_has_zero_similarity(self, numpy_store: NumpyStore) -> None:
        """저장된 벡터가 영벡터인 경우 유사도 0.0인지 검증."""
        # Arrange
        chunk = CodeChunk(
            file_path="zero.py", content="pass", start_line=1, end_line=1,
            chunk_type="function", name="zero",
        )
        numpy_store.add([chunk], [[0.0, 0.0, 0.0]])

        # Act
        results = numpy_store.search([1.0, 0.0, 0.0], top_k=1)

        # Assert: 영벡터 → 유사도 0.0
        assert len(results) == 1
        assert results[0][1] == 0.0


# ---------------------------------------------------------------------------
# 3. remove() 후 결과 테스트
# ---------------------------------------------------------------------------

class TestRemove:
    """remove() 동작 테스트."""

    def test_remove_filters_chunks(
        self,
        numpy_store: NumpyStore,
        sample_chunks: list[CodeChunk],
        sample_embeddings: list[list[float]],
    ) -> None:
        """remove() 후 해당 파일 청크가 검색되지 않는지 검증."""
        # Arrange
        numpy_store.add(sample_chunks, sample_embeddings)
        removed_path = sample_chunks[0].file_path

        # Act
        numpy_store.remove(removed_path)
        results = numpy_store.search(sample_embeddings[0], top_k=10)

        # Assert: 삭제된 파일 청크 없음
        assert all(r[0].file_path != removed_path for r in results)

    def test_remove_decreases_size(
        self,
        numpy_store: NumpyStore,
        sample_chunks: list[CodeChunk],
        sample_embeddings: list[list[float]],
    ) -> None:
        """remove() 후 size가 감소하는지 검증."""
        # Arrange
        numpy_store.add(sample_chunks, sample_embeddings)
        assert numpy_store.size == 2

        # Act
        numpy_store.remove(sample_chunks[0].file_path)

        # Assert
        assert numpy_store.size == 1

    def test_remove_nonexistent_path_does_nothing(self, numpy_store: NumpyStore) -> None:
        """존재하지 않는 경로 remove() 호출이 오류 없이 무시되는지 검증."""
        # Arrange
        chunk = CodeChunk(
            file_path="exist.py", content="pass", start_line=1, end_line=1,
            chunk_type="function", name="f",
        )
        numpy_store.add([chunk], [[1.0, 0.0]])

        # Act — 존재하지 않는 경로
        numpy_store.remove("nonexistent.py")  # 예외 없이 동작해야 함

        # Assert: 기존 청크 유지
        assert numpy_store.size == 1

    def test_remove_multiple_chunks_from_same_file(self, numpy_store: NumpyStore) -> None:
        """같은 파일에서 여러 청크가 모두 삭제되는지 검증."""
        # Arrange — 같은 파일에서 2개 청크
        chunks = [
            CodeChunk(
                file_path="multi.py", content="def a(): pass",
                start_line=1, end_line=1, chunk_type="function", name="a",
            ),
            CodeChunk(
                file_path="multi.py", content="def b(): pass",
                start_line=3, end_line=3, chunk_type="function", name="b",
            ),
            CodeChunk(
                file_path="other.py", content="def c(): pass",
                start_line=1, end_line=1, chunk_type="function", name="c",
            ),
        ]
        embeddings = [[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]]
        numpy_store.add(chunks, embeddings)

        # Act
        numpy_store.remove("multi.py")

        # Assert: multi.py 청크 모두 삭제, other.py만 남음
        assert numpy_store.size == 1
        results = numpy_store.search([1.0, 0.0], top_k=10)
        assert all(r[0].file_path == "other.py" for r in results)


# ---------------------------------------------------------------------------
# 4. 빈 스토어 테스트
# ---------------------------------------------------------------------------

class TestEmptyStore:
    """빈 스토어 동작 테스트."""

    def test_empty_store_search_returns_empty(self, numpy_store: NumpyStore) -> None:
        """빈 스토어에서 search() 시 빈 리스트를 반환하는지 검증."""
        # Act
        results = numpy_store.search([1.0, 0.0], top_k=5)

        # Assert
        assert results == []

    def test_top_k_zero_returns_empty(
        self,
        numpy_store: NumpyStore,
        sample_chunks: list[CodeChunk],
        sample_embeddings: list[list[float]],
    ) -> None:
        """top_k=0 검색 시 빈 리스트를 반환하는지 검증."""
        # Arrange
        numpy_store.add(sample_chunks, sample_embeddings)

        # Act
        results = numpy_store.search([1.0, 0.0, 0.0], top_k=0)

        # Assert
        assert results == []

    def test_top_k_negative_returns_empty(
        self,
        numpy_store: NumpyStore,
        sample_chunks: list[CodeChunk],
        sample_embeddings: list[list[float]],
    ) -> None:
        """top_k 음수 검색 시 빈 리스트를 반환하는지 검증."""
        # Arrange
        numpy_store.add(sample_chunks, sample_embeddings)

        # Act
        results = numpy_store.search([1.0, 0.0, 0.0], top_k=-1)

        # Assert
        assert results == []

    def test_top_k_larger_than_store_returns_all(
        self,
        numpy_store: NumpyStore,
        sample_chunks: list[CodeChunk],
        sample_embeddings: list[list[float]],
    ) -> None:
        """top_k가 스토어 크기보다 클 때 전체 청크를 반환하는지 검증."""
        # Arrange — 2개 청크
        numpy_store.add(sample_chunks, sample_embeddings)

        # Act — top_k=100이지만 스토어에는 2개
        results = numpy_store.search([1.0, 0.0, 0.0], top_k=100)

        # Assert: 2개 반환
        assert len(results) == 2

    def test_empty_store_size_is_zero(self, numpy_store: NumpyStore) -> None:
        """초기 스토어 size가 0인지 검증."""
        assert numpy_store.size == 0


# ---------------------------------------------------------------------------
# 5. 길이 불일치 ValueError 테스트
# ---------------------------------------------------------------------------

class TestLengthMismatch:
    """chunks와 embeddings 길이 불일치 처리 테스트."""

    def test_add_more_chunks_than_embeddings_raises_value_error(
        self, numpy_store: NumpyStore
    ) -> None:
        """청크 3개, 임베딩 2개일 때 ValueError를 발생시키는지 검증."""
        # Arrange
        chunks = [
            CodeChunk(
                file_path=f"file{i}.py", content="pass",
                start_line=1, end_line=1, chunk_type="function", name=f"f{i}",
            )
            for i in range(3)
        ]
        embeddings = [[1.0], [2.0]]

        # Act & Assert
        with pytest.raises(ValueError):
            numpy_store.add(chunks, embeddings)

    def test_add_more_embeddings_than_chunks_raises_value_error(
        self, numpy_store: NumpyStore
    ) -> None:
        """청크 1개, 임베딩 3개일 때 ValueError를 발생시키는지 검증."""
        # Arrange
        chunks = [
            CodeChunk(
                file_path="file.py", content="pass",
                start_line=1, end_line=1, chunk_type="function", name="f",
            )
        ]
        embeddings = [[1.0], [2.0], [3.0]]

        # Act & Assert
        with pytest.raises(ValueError):
            numpy_store.add(chunks, embeddings)

    def test_add_empty_chunks_and_embeddings_is_ok(self, numpy_store: NumpyStore) -> None:
        """빈 청크와 빈 임베딩 add()는 정상 동작하는지 검증."""
        # Act — 예외 없이 완료되어야 함
        numpy_store.add([], [])

        # Assert
        assert numpy_store.size == 0


# ---------------------------------------------------------------------------
# 6. clear() 테스트
# ---------------------------------------------------------------------------

class TestClear:
    """clear() 동작 테스트."""

    def test_clear_removes_all_chunks(
        self,
        numpy_store: NumpyStore,
        sample_chunks: list[CodeChunk],
        sample_embeddings: list[list[float]],
    ) -> None:
        """clear() 후 빈 스토어 상태가 되는지 검증."""
        # Arrange
        numpy_store.add(sample_chunks, sample_embeddings)
        assert numpy_store.size == 2

        # Act
        numpy_store.clear()

        # Assert
        assert numpy_store.size == 0
        results = numpy_store.search([1.0, 0.0, 0.0], top_k=5)
        assert results == []

    def test_clear_allows_new_add(
        self,
        numpy_store: NumpyStore,
        sample_chunks: list[CodeChunk],
        sample_embeddings: list[list[float]],
    ) -> None:
        """clear() 후 새로운 add()가 정상 동작하는지 검증."""
        # Arrange
        numpy_store.add(sample_chunks, sample_embeddings)
        numpy_store.clear()

        # Act — clear 후 새 데이터 추가
        new_chunk = CodeChunk(
            file_path="new.py", content="pass",
            start_line=1, end_line=1, chunk_type="function", name="new",
        )
        numpy_store.add([new_chunk], [[1.0, 0.0, 0.0]])

        # Assert
        assert numpy_store.size == 1

    def test_clear_on_empty_store_does_nothing(self, numpy_store: NumpyStore) -> None:
        """빈 스토어에 clear() 호출이 오류 없이 동작하는지 검증."""
        # Act — 예외 없이 완료되어야 함
        numpy_store.clear()

        # Assert
        assert numpy_store.size == 0


# ---------------------------------------------------------------------------
# 7. create_vector_store() 팩토리 테스트 (LanceDB mock)
# ---------------------------------------------------------------------------

class TestCreateVectorStore:
    """create_vector_store() 팩토리 함수 테스트."""

    def test_create_vector_store_no_lancedb_returns_numpy_store(self) -> None:
        """lancedb 없을 때 NumpyStore를 반환하는지 검증."""
        # Arrange — find_spec이 None 반환 (lancedb 없음)
        with patch("importlib.util.find_spec", return_value=None):
            # Act
            store = create_vector_store()

        # Assert
        assert isinstance(store, NumpyStore)

    def test_create_vector_store_with_lancedb_available(self) -> None:
        """lancedb 감지 시 LanceDBStore 생성을 시도하는지 검증.

        LanceDBStore 초기화 실패 시 NumpyStore로 폴백하는 동작도 포함.
        """
        # Arrange — find_spec이 MagicMock 반환 (lancedb 있음)
        mock_spec = MagicMock()

        with patch("importlib.util.find_spec", return_value=mock_spec), \
             patch("src.rag.vector_store.LanceDBStore") as mock_lancedb_cls:
            mock_lancedb_instance = MagicMock()
            mock_lancedb_cls.return_value = mock_lancedb_instance

            # Act
            store = create_vector_store()

        # Assert: LanceDBStore() 호출됨
        mock_lancedb_cls.assert_called_once()
        assert store is mock_lancedb_instance

    def test_create_vector_store_lancedb_init_failure_falls_back_to_numpy(self) -> None:
        """LanceDBStore 초기화 실패 시 NumpyStore로 폴백하는지 검증."""
        # Arrange — lancedb 있지만 초기화 실패
        mock_spec = MagicMock()

        with patch("importlib.util.find_spec", return_value=mock_spec), \
             patch("src.rag.vector_store.LanceDBStore", side_effect=Exception("init failed")):
            # Act
            store = create_vector_store()

        # Assert: NumpyStore로 폴백
        assert isinstance(store, NumpyStore)


# ---------------------------------------------------------------------------
# 8. VectorStoreProtocol 준수 테스트
# ---------------------------------------------------------------------------

class TestVectorStoreProtocol:
    """NumpyStore가 VectorStoreProtocol을 준수하는지 검증."""

    def test_numpy_store_implements_protocol(self, numpy_store: NumpyStore) -> None:
        """NumpyStore가 VectorStoreProtocol을 구현하는지 검증."""
        # Assert: isinstance 체크 (runtime_checkable Protocol)
        assert isinstance(numpy_store, VectorStoreProtocol)

    def test_numpy_store_has_all_protocol_methods(self, numpy_store: NumpyStore) -> None:
        """NumpyStore에 모든 필수 메서드가 있는지 검증."""
        assert hasattr(numpy_store, "add")
        assert hasattr(numpy_store, "search")
        assert hasattr(numpy_store, "remove")
        assert hasattr(numpy_store, "clear")


# ---------------------------------------------------------------------------
# 9. 헬퍼 함수 테스트
# ---------------------------------------------------------------------------

class TestLanceDBStore:
    """LanceDBStore 메서드 테스트 (lancedb를 sys.modules mock으로 주입)."""

    def _make_lancedb_mock(self) -> MagicMock:
        """lancedb 모듈 mock을 생성한다."""
        mock_lancedb = MagicMock()
        mock_db = MagicMock()
        mock_table = MagicMock()

        mock_lancedb.connect.return_value = mock_db
        mock_db.table_names.return_value = []  # 기존 테이블 없음
        mock_db.create_table.return_value = mock_table
        mock_db.open_table.return_value = mock_table

        return mock_lancedb, mock_db, mock_table

    def _make_store_with_mock(self) -> tuple[Any, MagicMock, MagicMock]:
        """mock lancedb가 주입된 LanceDBStore를 생성한다."""
        from src.rag.vector_store import LanceDBStore

        mock_lancedb, mock_db, mock_table = self._make_lancedb_mock()
        with patch.dict(sys.modules, {"lancedb": mock_lancedb}):
            store = LanceDBStore(cache_dir="/tmp/test_lancedb")
        return store, mock_db, mock_table

    def test_lancedb_store_init_without_existing_table(self) -> None:
        """기존 테이블이 없을 때 LanceDBStore 초기화가 정상 동작하는지 검증."""
        # Arrange & Act
        from src.rag.vector_store import LanceDBStore

        mock_lancedb, mock_db, _ = self._make_lancedb_mock()
        mock_db.table_names.return_value = []

        with patch.dict(sys.modules, {"lancedb": mock_lancedb}):
            store = LanceDBStore(cache_dir="/tmp/test_lancedb")

        # Assert: 테이블 없음 상태로 초기화
        assert store._table is None
        assert store._chunk_map == {}

    def test_lancedb_store_init_with_existing_table(self) -> None:
        """기존 테이블이 있을 때 LanceDBStore 초기화 시 테이블을 로드하는지 검증."""
        # Arrange
        from src.rag.vector_store import LanceDBStore

        mock_lancedb, mock_db, mock_table = self._make_lancedb_mock()
        mock_db.table_names.return_value = ["chunks"]  # 기존 테이블 있음

        with patch.dict(sys.modules, {"lancedb": mock_lancedb}):
            store = LanceDBStore(cache_dir="/tmp/test_lancedb")

        # Assert: 기존 테이블 로드됨
        mock_db.open_table.assert_called_once_with("chunks")
        assert store._table is mock_table

    def test_lancedb_store_add_creates_table_first_time(self) -> None:
        """최초 add() 호출 시 새 테이블이 생성되는지 검증."""
        # Arrange
        from src.rag.vector_store import LanceDBStore

        mock_lancedb, mock_db, mock_table = self._make_lancedb_mock()

        with patch.dict(sys.modules, {"lancedb": mock_lancedb}):
            store = LanceDBStore(cache_dir="/tmp/test_lancedb")

        chunk = CodeChunk(
            file_path="a.py", content="pass",
            start_line=1, end_line=1, chunk_type="function", name="a",
        )

        # Act
        with patch.dict(sys.modules, {"lancedb": mock_lancedb}):
            store.add([chunk], [[1.0, 0.0]])

        # Assert: create_table 호출됨
        mock_db.create_table.assert_called_once()
        assert "a.py:1" in store._chunk_map

    def test_lancedb_store_add_appends_to_existing_table(self) -> None:
        """두 번째 add() 호출 시 기존 테이블에 append하는지 검증."""
        # Arrange
        from src.rag.vector_store import LanceDBStore

        mock_lancedb, mock_db, mock_table = self._make_lancedb_mock()

        with patch.dict(sys.modules, {"lancedb": mock_lancedb}):
            store = LanceDBStore(cache_dir="/tmp/test_lancedb")

        chunk1 = CodeChunk(
            file_path="a.py", content="pass",
            start_line=1, end_line=1, chunk_type="function", name="a",
        )
        chunk2 = CodeChunk(
            file_path="b.py", content="pass",
            start_line=1, end_line=1, chunk_type="function", name="b",
        )

        # Act — 두 번 add()
        with patch.dict(sys.modules, {"lancedb": mock_lancedb}):
            store.add([chunk1], [[1.0, 0.0]])
            store.add([chunk2], [[0.0, 1.0]])

        # Assert: 두 번째는 table.add() 호출
        mock_table.add.assert_called_once()

    def test_lancedb_store_add_empty_chunks_does_nothing(self) -> None:
        """빈 청크 add() 시 create_table이 호출되지 않는지 검증."""
        # Arrange
        from src.rag.vector_store import LanceDBStore

        mock_lancedb, mock_db, _ = self._make_lancedb_mock()

        with patch.dict(sys.modules, {"lancedb": mock_lancedb}):
            store = LanceDBStore(cache_dir="/tmp/test_lancedb")

        # Act
        with patch.dict(sys.modules, {"lancedb": mock_lancedb}):
            store.add([], [])

        # Assert: create_table 호출 안 됨
        mock_db.create_table.assert_not_called()

    def test_lancedb_store_search_when_table_is_none_returns_empty(self) -> None:
        """테이블이 없을 때 search()가 빈 리스트를 반환하는지 검증."""
        # Arrange
        from src.rag.vector_store import LanceDBStore

        mock_lancedb, _, _ = self._make_lancedb_mock()

        with patch.dict(sys.modules, {"lancedb": mock_lancedb}):
            store = LanceDBStore(cache_dir="/tmp/test_lancedb")

        # Assert: 테이블 없음 → 빈 리스트
        result = store.search([1.0, 0.0], top_k=5)
        assert result == []

    def test_lancedb_store_search_returns_chunks_from_chunk_map(self) -> None:
        """search() 결과가 chunk_map에서 CodeChunk를 복원하는지 검증."""
        # Arrange — pandas 없이 DataFrame 동작을 mock으로 모사
        from src.rag.vector_store import LanceDBStore

        mock_lancedb, mock_db, mock_table = self._make_lancedb_mock()

        with patch.dict(sys.modules, {"lancedb": mock_lancedb}):
            store = LanceDBStore(cache_dir="/tmp/test_lancedb")

        chunk = CodeChunk(
            file_path="a.py", content="pass",
            start_line=1, end_line=1, chunk_type="function", name="a",
        )
        store._chunk_map["a.py:1"] = chunk
        store._table = mock_table

        # iterrows()가 (인덱스, dict-like row)를 반환하도록 mock
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, key: "a.py:1" if key == "id" else 0.1
        mock_row.get = lambda key, default=None: 0.1 if key == "_distance" else default

        mock_df = MagicMock()
        mock_df.iterrows.return_value = iter([(0, mock_row)])
        mock_table.search.return_value.limit.return_value.to_pandas.return_value = mock_df

        # Act
        result = store.search([1.0, 0.0], top_k=1)

        # Assert: (chunk, 0.9) 반환 (1.0 - 0.1 = 0.9)
        assert len(result) == 1
        assert result[0][0] is chunk
        assert abs(result[0][1] - 0.9) < 1e-9

    def test_lancedb_store_search_skips_unknown_chunk_ids(self) -> None:
        """chunk_map에 없는 id는 결과에서 제외되는지 검증."""
        # Arrange — pandas 없이 DataFrame 동작을 mock으로 모사
        from src.rag.vector_store import LanceDBStore

        mock_lancedb, _, mock_table = self._make_lancedb_mock()

        with patch.dict(sys.modules, {"lancedb": mock_lancedb}):
            store = LanceDBStore(cache_dir="/tmp/test_lancedb")

        store._table = mock_table

        # chunk_map에 없는 id를 반환
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, key: "unknown:99" if key == "id" else 0.1
        mock_row.get = lambda key, default=None: 0.1 if key == "_distance" else default

        mock_df = MagicMock()
        mock_df.iterrows.return_value = iter([(0, mock_row)])
        mock_table.search.return_value.limit.return_value.to_pandas.return_value = mock_df

        # Act
        result = store.search([1.0, 0.0], top_k=1)

        # Assert: 빈 리스트 (chunk_map에 없음)
        assert result == []

    def test_lancedb_store_remove_when_table_is_none_does_nothing(self) -> None:
        """테이블이 없을 때 remove()가 오류 없이 동작하는지 검증."""
        # Arrange
        from src.rag.vector_store import LanceDBStore

        mock_lancedb, _, _ = self._make_lancedb_mock()

        with patch.dict(sys.modules, {"lancedb": mock_lancedb}):
            store = LanceDBStore(cache_dir="/tmp/test_lancedb")

        # Act — 예외 없이 동작해야 함
        store.remove("nonexistent.py")

    def test_lancedb_store_remove_deletes_matching_chunks(self) -> None:
        """remove()가 해당 파일 경로의 청크를 chunk_map과 테이블에서 삭제하는지 검증."""
        # Arrange
        from src.rag.vector_store import LanceDBStore

        mock_lancedb, _, mock_table = self._make_lancedb_mock()

        with patch.dict(sys.modules, {"lancedb": mock_lancedb}):
            store = LanceDBStore(cache_dir="/tmp/test_lancedb")

        chunk = CodeChunk(
            file_path="delete_me.py", content="pass",
            start_line=1, end_line=1, chunk_type="function", name="f",
        )
        store._chunk_map["delete_me.py:1"] = chunk
        store._table = mock_table

        # Act
        store.remove("delete_me.py")

        # Assert: chunk_map에서 삭제, table.delete 호출
        assert "delete_me.py:1" not in store._chunk_map
        mock_table.delete.assert_called_once()

    def test_lancedb_store_remove_nonexistent_file_does_nothing(self) -> None:
        """chunk_map에 없는 파일 경로 remove()가 table.delete를 호출하지 않는지 검증."""
        # Arrange
        from src.rag.vector_store import LanceDBStore

        mock_lancedb, _, mock_table = self._make_lancedb_mock()

        with patch.dict(sys.modules, {"lancedb": mock_lancedb}):
            store = LanceDBStore(cache_dir="/tmp/test_lancedb")

        store._table = mock_table  # 테이블은 있음

        # Act
        store.remove("not_in_chunk_map.py")

        # Assert: delete 호출 안 됨
        mock_table.delete.assert_not_called()

    def test_lancedb_store_clear_drops_table(self) -> None:
        """clear()가 lancedb 테이블을 삭제하는지 검증."""
        # Arrange
        from src.rag.vector_store import LanceDBStore

        mock_lancedb, mock_db, mock_table = self._make_lancedb_mock()
        mock_db.table_names.return_value = ["chunks"]

        with patch.dict(sys.modules, {"lancedb": mock_lancedb}):
            store = LanceDBStore(cache_dir="/tmp/test_lancedb")

        store._table = mock_table
        store._chunk_map["a.py:1"] = MagicMock()

        # Act
        store.clear()

        # Assert: drop_table 호출, chunk_map 비워짐
        mock_db.drop_table.assert_called_once_with("chunks")
        assert store._table is None
        assert store._chunk_map == {}

    def test_lancedb_store_clear_when_table_is_none(self) -> None:
        """테이블이 없을 때 clear()가 오류 없이 동작하는지 검증."""
        # Arrange
        from src.rag.vector_store import LanceDBStore

        mock_lancedb, mock_db, _ = self._make_lancedb_mock()

        with patch.dict(sys.modules, {"lancedb": mock_lancedb}):
            store = LanceDBStore(cache_dir="/tmp/test_lancedb")

        # _table이 None인 상태 (초기 상태)
        assert store._table is None

        # Act — 예외 없이 동작해야 함
        store.clear()

        # Assert: drop_table 호출 안 됨
        mock_db.drop_table.assert_not_called()

    def test_lancedb_store_add_length_mismatch_raises_value_error(self) -> None:
        """chunks와 embeddings 길이 불일치 시 ValueError 발생 검증."""
        # Arrange
        from src.rag.vector_store import LanceDBStore

        mock_lancedb, _, _ = self._make_lancedb_mock()

        with patch.dict(sys.modules, {"lancedb": mock_lancedb}):
            store = LanceDBStore(cache_dir="/tmp/test_lancedb")

        chunks = [
            CodeChunk(
                file_path=f"f{i}.py", content="pass",
                start_line=1, end_line=1, chunk_type="function", name=f"f{i}",
            )
            for i in range(2)
        ]

        # Act & Assert
        with patch.dict(sys.modules, {"lancedb": mock_lancedb}):
            with pytest.raises(ValueError):
                store.add(chunks, [[1.0]])

    def test_lancedb_store_search_top_k_zero_returns_empty(self) -> None:
        """top_k=0 search()가 빈 리스트를 반환하는지 검증."""
        # Arrange
        from src.rag.vector_store import LanceDBStore

        mock_lancedb, _, mock_table = self._make_lancedb_mock()

        with patch.dict(sys.modules, {"lancedb": mock_lancedb}):
            store = LanceDBStore(cache_dir="/tmp/test_lancedb")

        store._table = mock_table

        # Act
        result = store.search([1.0, 0.0], top_k=0)

        # Assert
        assert result == []


class TestHelperFunctions:
    """_chunk_id 헬퍼 함수 테스트."""

    def test_chunk_id_uses_file_path_and_start_line(self) -> None:
        """_chunk_id가 file_path:start_line 형식인지 검증."""
        # Arrange
        chunk = CodeChunk(
            file_path="src/main.py",
            content="def func(): pass",
            start_line=10,
            end_line=15,
            chunk_type="function",
            name="func",
        )

        # Act
        chunk_id = _chunk_id(chunk)

        # Assert
        assert chunk_id == "src/main.py:10"

    def test_chunk_id_is_unique_for_different_lines(self) -> None:
        """다른 start_line을 가진 청크의 ID가 다른지 검증."""
        # Arrange
        chunk1 = CodeChunk(
            file_path="file.py", content="pass",
            start_line=1, end_line=5, chunk_type="function", name="a",
        )
        chunk2 = CodeChunk(
            file_path="file.py", content="pass",
            start_line=10, end_line=15, chunk_type="function", name="b",
        )

        # Assert
        assert _chunk_id(chunk1) != _chunk_id(chunk2)
