"""IncrementalIndexer 유닛 테스트.

테스트 대상: src/rag/incremental_indexer.py
  — IncrementalIndexer 클래스, get_indexer(), reset_indexer(), _build_indexer()
커버리지 목표: 100%

테스트 케이스:
1. 전체 인덱싱 (index() — 캐시 파일 생성, 청크 수 반환)
2. 증분 업데이트 (update() — 신규·수정·삭제 파일, 변경 없음)
3. mtime 기반 변경 감지 (_detect_changes() 정확도)
4. 파일 필터링 (IGNORED_DIRS, SUPPORTED_EXTENSIONS, BINARY_EXTENSIONS)
5. 캐시 관리 (file_index.json 로드/저장, bm25_index.pkl, 손상된 캐시)
6. 검색 기능 (HybridSearcher 위임, CodeChunk 목록 반환)
7. 싱글톤 패턴 (get_indexer() 동일 인스턴스, reset_indexer())
8. 엣지 케이스 (빈 프로젝트, 지원 안 되는 확장자만, 임베딩 실패, asyncio 루프 충돌)
"""

from __future__ import annotations

import asyncio
import json
import pickle
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.domain import CodeChunk
from src.rag.incremental_indexer import (
    BINARY_EXTENSIONS,
    IGNORED_DIRS,
    SUPPORTED_EXTENSIONS,
    IncrementalIndexer,
    _build_indexer,
    _build_pathspec,
    _load_gitignore_spec,
    get_indexer,
    reset_indexer,
)


# ---------------------------------------------------------------------------
# 모듈 레벨 헬퍼 클래스 (pickle 직렬화를 위해 최상위 스코프에 선언)
# ---------------------------------------------------------------------------


class _FakeScorer:
    """pickle 가능한 최소 scorer 대역 — _load_bm25_index() 테스트에 사용."""

    _bm25 = None
    _corpus_size = 0


# ---------------------------------------------------------------------------
# 공통 헬퍼 / 픽스처
# ---------------------------------------------------------------------------


def _make_chunk(file_path: str = "src/a.py", start_line: int = 1) -> CodeChunk:
    """테스트용 CodeChunk를 생성하는 헬퍼."""
    return CodeChunk(
        file_path=file_path,
        content="def foo(): pass",
        start_line=start_line,
        end_line=start_line + 4,
        chunk_type="function",
        name="foo",
    )


@pytest.fixture
def mock_chunker() -> MagicMock:
    """ChunkerProtocol mock — 기본적으로 청크 1개를 반환한다."""
    chunker = MagicMock()
    chunker.chunk.return_value = [_make_chunk()]
    return chunker


@pytest.fixture
def mock_scorer() -> MagicMock:
    """BM25Scorer mock 픽스처."""
    scorer = MagicMock()
    scorer._bm25 = MagicMock()
    scorer._corpus_size = 0
    return scorer


@pytest.fixture
def mock_store() -> MagicMock:
    """VectorStoreProtocol mock 픽스처."""
    return MagicMock()


@pytest.fixture
def mock_embedder() -> MagicMock:
    """AnthropicEmbedder mock — 기본적으로 [[0.1, 0.2]] 임베딩을 반환한다."""
    embedder = MagicMock()
    embedder.is_available = True
    embedder.embed = AsyncMock(return_value=[[0.1, 0.2]])
    return embedder


@pytest.fixture
def indexer(
    tmp_path: Path,
    mock_chunker: MagicMock,
    mock_scorer: MagicMock,
    mock_store: MagicMock,
    mock_embedder: MagicMock,
) -> IncrementalIndexer:
    """tmp_path 기반 IncrementalIndexer 픽스처."""
    return IncrementalIndexer(
        chunker=mock_chunker,
        scorer=mock_scorer,
        store=mock_store,
        embedder=mock_embedder,
        project_path=str(tmp_path),
        cache_dir=".rag_cache",
    )


@pytest.fixture(autouse=True)
def reset_singleton() -> None:
    """각 테스트 후 싱글톤을 초기화한다."""
    yield
    reset_indexer()


# ---------------------------------------------------------------------------
# 1. 전체 인덱싱 테스트
# ---------------------------------------------------------------------------


class TestFullIndexing:
    """index() 전체 인덱싱 테스트."""

    def test_index_empty_project_returns_zero(
        self,
        indexer: IncrementalIndexer,
        tmp_path: Path,
    ) -> None:
        """파일이 없는 빈 프로젝트에서 index()가 0을 반환하는지 검증."""
        # Arrange — tmp_path에 파일 없음

        # Act
        count = indexer.index()

        # Assert
        assert count == 0

    def test_index_returns_chunk_count(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """지원 파일 1개가 있을 때 청크 수를 반환하는지 검증."""
        # Arrange — .py 파일 1개 생성
        (tmp_path / "main.py").write_text("def foo(): pass\n", encoding="utf-8")
        mock_chunker.chunk.return_value = [_make_chunk("main.py", 1), _make_chunk("main.py", 10)]

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )

        # Act
        with patch("asyncio.run", return_value=[[0.1, 0.2], [0.3, 0.4]]):
            count = indexer.index()

        # Assert: 청크 2개
        assert count == 2

    def test_index_creates_file_index_json(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """index() 후 file_index.json이 생성되는지 검증."""
        # Arrange
        (tmp_path / "main.py").write_text("def foo(): pass\n", encoding="utf-8")

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )

        # Act
        with patch("asyncio.run", return_value=[[0.1, 0.2]]):
            indexer.index()

        # Assert
        cache_dir = tmp_path / ".rag_cache"
        assert (cache_dir / "file_index.json").exists()

    def test_index_creates_bm25_index_pkl(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """index() 후 bm25_index.pkl이 생성되는지 검증."""
        # Arrange
        (tmp_path / "main.py").write_text("def foo(): pass\n", encoding="utf-8")

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )

        # Act
        with patch("asyncio.run", return_value=[[0.1, 0.2]]):
            indexer.index()

        # Assert
        cache_dir = tmp_path / ".rag_cache"
        assert (cache_dir / "bm25_index.pkl").exists()

    def test_index_clears_store_before_indexing(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """index() 시작 시 store.clear()를 호출하는지 검증."""
        # Arrange
        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )

        # Act
        indexer.index()

        # Assert
        mock_store.clear.assert_called_once()

    def test_index_calls_scorer_fit(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """청크가 있을 때 scorer.fit()이 호출되는지 검증."""
        # Arrange
        (tmp_path / "main.py").write_text("def foo(): pass\n", encoding="utf-8")

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )

        # Act
        with patch("asyncio.run", return_value=[[0.1, 0.2]]):
            indexer.index()

        # Assert
        mock_scorer.fit.assert_called_once()

    def test_index_all_chunks_property_updated(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """index() 후 all_chunks 속성이 갱신되는지 검증."""
        # Arrange
        (tmp_path / "main.py").write_text("def foo(): pass\n", encoding="utf-8")
        mock_chunker.chunk.return_value = [_make_chunk("main.py")]

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )

        # Act
        with patch("asyncio.run", return_value=[[0.1, 0.2]]):
            indexer.index()

        # Assert
        assert len(indexer.all_chunks) == 1

    def test_index_file_index_json_contains_correct_data(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """file_index.json에 mtime, chunk_count, last_indexed가 포함되는지 검증."""
        # Arrange
        py_file = tmp_path / "main.py"
        py_file.write_text("def foo(): pass\n", encoding="utf-8")
        mock_chunker.chunk.return_value = [_make_chunk("main.py")]

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )

        # Act
        with patch("asyncio.run", return_value=[[0.1, 0.2]]):
            indexer.index()

        # Assert
        cache_file = tmp_path / ".rag_cache" / "file_index.json"
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        entry = next(iter(data.values()))
        assert "mtime" in entry
        assert "chunk_count" in entry
        assert "last_indexed" in entry
        assert entry["chunk_count"] == 1


# ---------------------------------------------------------------------------
# 2. 증분 업데이트 테스트
# ---------------------------------------------------------------------------


class TestIncrementalUpdate:
    """update() 증분 인덱싱 테스트."""

    def test_update_no_changes_returns_zeros(self, indexer: IncrementalIndexer) -> None:
        """변경이 없을 때 {"added": 0, "updated": 0, "removed": 0}을 반환하는지 검증."""
        # Arrange — _detect_changes()가 빈 리스트들을 반환하도록 mock
        with patch.object(indexer, "_detect_changes", return_value=([], [], [])):
            # Act
            result = indexer.update()

        # Assert
        assert result == {"added": 0, "updated": 0, "removed": 0}

    def test_update_new_file_increments_added(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """신규 파일 1개가 있을 때 added=1을 반환하는지 검증."""
        # Arrange
        new_file = tmp_path / "new.py"
        new_file.write_text("def bar(): pass\n", encoding="utf-8")

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )

        with patch.object(indexer, "_detect_changes", return_value=([new_file], [], [])):
            with patch.object(indexer, "_reembed_and_add"):
                result = indexer.update()

        # Assert
        assert result["added"] == 1
        assert result["updated"] == 0
        assert result["removed"] == 0

    def test_update_modified_file_increments_updated(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """수정된 파일 1개가 있을 때 updated=1을 반환하는지 검증."""
        # Arrange
        mod_file = tmp_path / "mod.py"
        mod_file.write_text("def modified(): pass\n", encoding="utf-8")

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )

        with patch.object(indexer, "_detect_changes", return_value=([], [mod_file], [])):
            with patch.object(indexer, "_reembed_and_add"):
                result = indexer.update()

        # Assert
        assert result["updated"] == 1
        assert result["added"] == 0
        assert result["removed"] == 0

    def test_update_deleted_file_increments_removed(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """삭제된 파일 1개가 있을 때 removed=1을 반환하는지 검증."""
        # Arrange
        del_file = tmp_path / "deleted.py"

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )

        with patch.object(indexer, "_detect_changes", return_value=([], [], [del_file])):
            result = indexer.update()

        # Assert
        assert result["removed"] == 1
        assert result["added"] == 0
        assert result["updated"] == 0

    def test_update_deleted_file_calls_store_remove(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """삭제 처리 시 store.remove()가 호출되는지 검증."""
        # Arrange
        del_file = tmp_path / "deleted.py"

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )

        with patch.object(indexer, "_detect_changes", return_value=([], [], [del_file])):
            indexer.update()

        # Assert
        mock_store.remove.assert_called_once_with(str(del_file))

    def test_update_deleted_file_removed_from_all_chunks(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """삭제 파일에 속한 청크가 all_chunks에서 제거되는지 검증."""
        # Arrange
        del_file = tmp_path / "deleted.py"
        chunk_del = _make_chunk(str(del_file))
        chunk_keep = _make_chunk("other.py")

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )
        indexer._all_chunks = [chunk_del, chunk_keep]

        with patch.object(indexer, "_detect_changes", return_value=([], [], [del_file])):
            indexer.update()

        # Assert: deleted.py 청크 제거, other.py 유지
        file_paths = {c.file_path for c in indexer.all_chunks}
        assert str(del_file) not in file_paths
        assert "other.py" in file_paths

    def test_update_no_changes_does_not_call_scorer_fit(
        self,
        indexer: IncrementalIndexer,
        mock_scorer: MagicMock,
    ) -> None:
        """변경이 없을 때 scorer.fit()이 호출되지 않는지 검증."""
        # Arrange
        with patch.object(indexer, "_detect_changes", return_value=([], [], [])):
            # Act
            indexer.update()

        # Assert
        mock_scorer.fit.assert_not_called()

    def test_update_with_changes_calls_scorer_fit(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """변경이 있을 때 scorer.fit()이 호출되는지 검증."""
        # Arrange
        del_file = tmp_path / "deleted.py"

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )

        with patch.object(indexer, "_detect_changes", return_value=([], [], [del_file])):
            indexer.update()

        # Assert
        mock_scorer.fit.assert_called_once()


# ---------------------------------------------------------------------------
# 3. mtime 기반 변경 감지 테스트
# ---------------------------------------------------------------------------


class TestDetectChanges:
    """_detect_changes() 변경 감지 테스트."""

    def test_detect_changes_new_file_detected(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """캐시에 없는 파일을 새 파일로 감지하는지 검증."""
        # Arrange — .py 파일 1개 생성, 캐시 없음
        (tmp_path / "new.py").write_text("print('hello')\n", encoding="utf-8")

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )

        # Act
        new_files, modified_files, deleted_files = indexer._detect_changes()

        # Assert
        assert len(new_files) == 1
        assert modified_files == []
        assert deleted_files == []

    def test_detect_changes_modified_file_detected(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """mtime이 변경된 파일을 수정 파일로 감지하는지 검증."""
        # Arrange — 파일 생성 후 캐시에 오래된 mtime 등록
        py_file = tmp_path / "mod.py"
        py_file.write_text("print('original')\n", encoding="utf-8")
        current_mtime = py_file.stat().st_mtime

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )

        # 캐시에 다른 mtime 저장 (더 오래된 시간)
        old_entry = {"mtime": current_mtime - 100.0, "chunk_count": 1, "last_indexed": "2024-01-01T00:00:00+00:00"}
        cache_dir = tmp_path / ".rag_cache"
        cache_dir.mkdir()
        (cache_dir / "file_index.json").write_text(
            json.dumps({str(py_file): old_entry}),
            encoding="utf-8",
        )

        # Act
        new_files, modified_files, deleted_files = indexer._detect_changes()

        # Assert
        assert new_files == []
        assert len(modified_files) == 1
        assert deleted_files == []

    def test_detect_changes_deleted_file_detected(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """캐시에 있지만 디스크에 없는 파일을 삭제 파일로 감지하는지 검증."""
        # Arrange — 캐시에 존재하지 않는 파일 경로 등록
        ghost_path = str(tmp_path / "ghost.py")

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )

        # 캐시에 유령 파일 등록
        cache_dir = tmp_path / ".rag_cache"
        cache_dir.mkdir()
        (cache_dir / "file_index.json").write_text(
            json.dumps({ghost_path: {"mtime": 1234567890.0, "chunk_count": 1, "last_indexed": "2024-01-01T00:00:00+00:00"}}),
            encoding="utf-8",
        )

        # Act
        new_files, modified_files, deleted_files = indexer._detect_changes()

        # Assert
        assert new_files == []
        assert modified_files == []
        assert len(deleted_files) == 1
        assert str(deleted_files[0]) == ghost_path

    def test_detect_changes_unchanged_file_not_detected(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """mtime이 같은 파일은 변경 없음으로 판단하는지 검증."""
        # Arrange — 파일 생성 후 동일한 mtime으로 캐시 등록
        py_file = tmp_path / "unchanged.py"
        py_file.write_text("print('same')\n", encoding="utf-8")
        mtime = py_file.stat().st_mtime

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )

        cache_dir = tmp_path / ".rag_cache"
        cache_dir.mkdir()
        (cache_dir / "file_index.json").write_text(
            json.dumps({str(py_file): {"mtime": mtime, "chunk_count": 1, "last_indexed": "2024-01-01T00:00:00+00:00"}}),
            encoding="utf-8",
        )

        # Act
        new_files, modified_files, deleted_files = indexer._detect_changes()

        # Assert: 아무것도 감지 안 됨
        assert new_files == []
        assert modified_files == []
        assert deleted_files == []


# ---------------------------------------------------------------------------
# 4. 파일 필터링 테스트
# ---------------------------------------------------------------------------


class TestFileFiltering:
    """_collect_files() 파일 수집 및 필터링 테스트."""

    def test_collect_files_supported_extension_included(
        self,
        indexer: IncrementalIndexer,
        tmp_path: Path,
    ) -> None:
        """지원 확장자 파일은 수집 대상에 포함되는지 검증."""
        # Arrange
        (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "module.ts").write_text("const x = 1;\n", encoding="utf-8")
        (tmp_path / "README.md").write_text("# Title\n", encoding="utf-8")

        # Act
        files = indexer._collect_files()

        # Assert
        suffixes = {f.suffix for f in files}
        assert ".py" in suffixes
        assert ".ts" in suffixes
        assert ".md" in suffixes

    def test_collect_files_binary_extensions_excluded(
        self,
        indexer: IncrementalIndexer,
        tmp_path: Path,
    ) -> None:
        """BINARY_EXTENSIONS 파일은 수집 대상에서 제외되는지 검증."""
        # Arrange — .pyc 바이너리 파일 생성
        (tmp_path / "compiled.pyc").write_bytes(b"\x00\x01\x02\x03")

        # Act
        files = indexer._collect_files()

        # Assert
        suffixes = {f.suffix for f in files}
        assert ".pyc" not in suffixes

    def test_collect_files_ignored_dirs_excluded(
        self,
        indexer: IncrementalIndexer,
        tmp_path: Path,
    ) -> None:
        """IGNORED_DIRS 내 파일은 수집 대상에서 제외되는지 검증."""
        # Arrange — __pycache__, .git, node_modules 아래 파일 생성
        for ignored_dir in ["__pycache__", ".git", "node_modules", ".venv"]:
            d = tmp_path / ignored_dir
            d.mkdir()
            (d / "script.py").write_text("x = 1\n", encoding="utf-8")

        # Act
        files = indexer._collect_files()

        # Assert: IGNORED_DIRS 내 파일 없음
        for f in files:
            assert not any(part in IGNORED_DIRS for part in f.parts)

    def test_collect_files_rag_cache_dir_excluded(
        self,
        indexer: IncrementalIndexer,
        tmp_path: Path,
    ) -> None:
        """.rag_cache 디렉토리 내 파일은 제외되는지 검증."""
        # Arrange — .rag_cache 내 파일 생성
        rag_dir = tmp_path / ".rag_cache"
        rag_dir.mkdir()
        (rag_dir / "cache.py").write_text("x = 1\n", encoding="utf-8")

        # Act
        files = indexer._collect_files()

        # Assert
        for f in files:
            assert ".rag_cache" not in f.parts

    def test_collect_files_unsupported_extension_excluded(
        self,
        indexer: IncrementalIndexer,
        tmp_path: Path,
    ) -> None:
        """지원하지 않는 확장자 파일은 수집 대상에서 제외되는지 검증."""
        # Arrange — .txt, .csv 등 지원 외 파일
        (tmp_path / "data.txt").write_text("hello\n", encoding="utf-8")
        (tmp_path / "data.csv").write_text("a,b,c\n", encoding="utf-8")
        (tmp_path / "data.log").write_text("2024-01-01\n", encoding="utf-8")

        # Act
        files = indexer._collect_files()

        # Assert
        suffixes = {f.suffix for f in files}
        assert ".txt" not in suffixes
        assert ".csv" not in suffixes
        assert ".log" not in suffixes

    def test_collect_files_empty_project_returns_empty(
        self,
        indexer: IncrementalIndexer,
    ) -> None:
        """빈 프로젝트에서 빈 리스트를 반환하는지 검증."""
        # Act
        files = indexer._collect_files()

        # Assert
        assert files == []

    def test_supported_extensions_constants(self) -> None:
        """SUPPORTED_EXTENSIONS 상수가 핵심 확장자를 포함하는지 검증."""
        assert ".py" in SUPPORTED_EXTENSIONS
        assert ".ts" in SUPPORTED_EXTENSIONS
        assert ".js" in SUPPORTED_EXTENSIONS
        assert ".md" in SUPPORTED_EXTENSIONS

    def test_ignored_dirs_constants(self) -> None:
        """IGNORED_DIRS 상수가 핵심 무시 디렉토리를 포함하는지 검증."""
        assert "__pycache__" in IGNORED_DIRS
        assert ".git" in IGNORED_DIRS
        assert "node_modules" in IGNORED_DIRS
        assert ".venv" in IGNORED_DIRS
        assert ".rag_cache" in IGNORED_DIRS

    def test_binary_extensions_constants(self) -> None:
        """BINARY_EXTENSIONS 상수가 핵심 바이너리 확장자를 포함하는지 검증."""
        assert ".pyc" in BINARY_EXTENSIONS
        assert ".so" in BINARY_EXTENSIONS
        assert ".pkl" in BINARY_EXTENSIONS


# ---------------------------------------------------------------------------
# 5. 캐시 관리 테스트
# ---------------------------------------------------------------------------


class TestCacheManagement:
    """_load_file_index(), _save_file_index(), _save_bm25_index(), _load_bm25_index() 테스트."""

    def test_load_file_index_missing_file_returns_empty(
        self,
        indexer: IncrementalIndexer,
    ) -> None:
        """file_index.json이 없으면 빈 딕셔너리를 반환하는지 검증."""
        result = indexer._load_file_index()
        assert result == {}

    def test_load_file_index_valid_json(
        self,
        indexer: IncrementalIndexer,
        tmp_path: Path,
    ) -> None:
        """유효한 file_index.json을 올바르게 로드하는지 검증."""
        # Arrange
        cache_dir = tmp_path / ".rag_cache"
        cache_dir.mkdir()
        expected = {"/path/to/file.py": {"mtime": 1234.5, "chunk_count": 2, "last_indexed": "2024-01-01T00:00:00+00:00"}}
        (cache_dir / "file_index.json").write_text(
            json.dumps(expected), encoding="utf-8"
        )

        # Act
        result = indexer._load_file_index()

        # Assert
        assert result == expected

    def test_load_file_index_corrupt_json_returns_empty(
        self,
        indexer: IncrementalIndexer,
        tmp_path: Path,
    ) -> None:
        """손상된 JSON 파일이면 빈 딕셔너리를 반환하는지 검증."""
        # Arrange — 손상된 JSON
        cache_dir = tmp_path / ".rag_cache"
        cache_dir.mkdir()
        (cache_dir / "file_index.json").write_text("{ INVALID JSON }", encoding="utf-8")

        # Act
        result = indexer._load_file_index()

        # Assert
        assert result == {}

    def test_save_file_index_creates_file(
        self,
        indexer: IncrementalIndexer,
        tmp_path: Path,
    ) -> None:
        """_save_file_index() 후 file_index.json이 생성되는지 검증."""
        # Arrange
        index_data = {"/some/file.py": {"mtime": 999.9, "chunk_count": 1, "last_indexed": "2024-01-01T00:00:00+00:00"}}

        # Act
        indexer._save_file_index(index_data)

        # Assert
        assert (tmp_path / ".rag_cache" / "file_index.json").exists()

    def test_save_file_index_correct_content(
        self,
        indexer: IncrementalIndexer,
        tmp_path: Path,
    ) -> None:
        """저장된 file_index.json 내용이 올바른지 검증."""
        # Arrange
        index_data = {"/file.py": {"mtime": 1.0, "chunk_count": 3, "last_indexed": "2024-01-01T00:00:00+00:00"}}

        # Act
        indexer._save_file_index(index_data)

        # Assert
        saved = json.loads((tmp_path / ".rag_cache" / "file_index.json").read_text(encoding="utf-8"))
        assert saved == index_data

    def test_save_file_index_oserror_does_not_raise(
        self,
        indexer: IncrementalIndexer,
    ) -> None:
        """_save_file_index() 중 OSError가 발생해도 예외가 전파되지 않는지 검증."""
        # Arrange — write_text가 OSError를 발생시킴
        with patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
            # Act & Assert: 예외 없이 완료
            indexer._save_file_index({"/f.py": {"mtime": 1.0, "chunk_count": 1, "last_indexed": "x"}})

    def test_save_bm25_index_creates_pkl(
        self,
        indexer: IncrementalIndexer,
        tmp_path: Path,
    ) -> None:
        """_save_bm25_index() 후 bm25_index.pkl이 생성되는지 검증."""
        # Act
        indexer._save_bm25_index()

        # Assert
        assert (tmp_path / ".rag_cache" / "bm25_index.pkl").exists()

    def test_save_bm25_index_oserror_does_not_raise(
        self,
        indexer: IncrementalIndexer,
    ) -> None:
        """_save_bm25_index() 중 OSError가 발생해도 예외가 전파되지 않는지 검증."""
        with patch("builtins.open", side_effect=OSError("disk full")):
            indexer._save_bm25_index()

    def test_load_bm25_index_missing_file_returns_false(
        self,
        indexer: IncrementalIndexer,
    ) -> None:
        """bm25_index.pkl이 없으면 False를 반환하는지 검증."""
        result = indexer._load_bm25_index()
        assert result is False

    def test_load_bm25_index_valid_pkl_returns_true(
        self,
        indexer: IncrementalIndexer,
        tmp_path: Path,
    ) -> None:
        """유효한 bm25_index.pkl을 로드하면 True를 반환하는지 검증."""
        # Arrange — 모듈 레벨 _FakeScorer로 pickle 가능한 객체 저장
        cache_dir = tmp_path / ".rag_cache"
        cache_dir.mkdir()
        pkl_path = cache_dir / "bm25_index.pkl"
        with pkl_path.open("wb") as f:
            pickle.dump(_FakeScorer(), f)

        # Act
        result = indexer._load_bm25_index()

        # Assert
        assert result is True

    def test_load_bm25_index_corrupt_pkl_returns_false(
        self,
        indexer: IncrementalIndexer,
        tmp_path: Path,
    ) -> None:
        """손상된 bm25_index.pkl이면 False를 반환하는지 검증."""
        # Arrange — 손상된 데이터
        cache_dir = tmp_path / ".rag_cache"
        cache_dir.mkdir()
        (cache_dir / "bm25_index.pkl").write_bytes(b"INVALID PICKLE DATA")

        # Act
        result = indexer._load_bm25_index()

        # Assert
        assert result is False


# ---------------------------------------------------------------------------
# 6. 검색 기능 테스트
# ---------------------------------------------------------------------------


class TestSearchFunctionality:
    """search() — HybridSearcher 위임 테스트."""

    @pytest.mark.asyncio
    async def test_search_empty_all_chunks_returns_empty(
        self,
        indexer: IncrementalIndexer,
    ) -> None:
        """all_chunks가 비어 있을 때 빈 리스트를 반환하는지 검증."""
        # Arrange — all_chunks 비어있음 (기본 상태)
        assert indexer.all_chunks == []

        # Act
        result = await indexer.search("query", top_k=5)

        # Assert
        assert result == []

    @pytest.mark.asyncio
    async def test_search_delegates_to_hybrid_searcher(
        self,
        indexer: IncrementalIndexer,
    ) -> None:
        """search()가 HybridSearcher.search()에 위임하는지 검증."""
        # Arrange — all_chunks에 청크 등록
        chunk = _make_chunk()
        indexer._all_chunks = [chunk]

        mock_searcher = MagicMock()
        mock_searcher.search = AsyncMock(return_value=[(chunk, 0.9)])

        with patch("src.rag.incremental_indexer.HybridSearcher", return_value=mock_searcher):
            # Act
            result = await indexer.search("find foo", top_k=3)

        # Assert
        mock_searcher.search.assert_called_once_with("find foo", 3, [chunk])
        assert result == [chunk]

    @pytest.mark.asyncio
    async def test_search_returns_only_chunks_not_scores(
        self,
        indexer: IncrementalIndexer,
    ) -> None:
        """search() 결과가 (chunk, score) 튜플이 아닌 chunk만 반환하는지 검증."""
        # Arrange
        chunk_a = _make_chunk("a.py")
        chunk_b = _make_chunk("b.py")
        indexer._all_chunks = [chunk_a, chunk_b]

        mock_searcher = MagicMock()
        mock_searcher.search = AsyncMock(return_value=[(chunk_a, 0.9), (chunk_b, 0.7)])

        with patch("src.rag.incremental_indexer.HybridSearcher", return_value=mock_searcher):
            result = await indexer.search("query", top_k=2)

        # Assert: CodeChunk 인스턴스만 반환
        assert all(isinstance(r, CodeChunk) for r in result)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# 7. 싱글톤 패턴 테스트
# ---------------------------------------------------------------------------


class TestSingletonPattern:
    """get_indexer(), reset_indexer(), _build_indexer() 테스트."""

    def test_get_indexer_returns_same_instance(self, tmp_path: Path) -> None:
        """get_indexer()가 동일 인스턴스를 반환하는지 검증."""
        # Arrange — _build_indexer를 mock으로 대체
        mock_instance = MagicMock(spec=IncrementalIndexer)

        with patch("src.rag.incremental_indexer._build_indexer", return_value=mock_instance):
            # Act
            instance1 = get_indexer(str(tmp_path))
            instance2 = get_indexer(str(tmp_path))

        # Assert: 동일 객체
        assert instance1 is instance2

    def test_reset_indexer_clears_singleton(self, tmp_path: Path) -> None:
        """reset_indexer() 후 get_indexer()가 새 인스턴스를 반환하는지 검증."""
        # Arrange
        mock1 = MagicMock(spec=IncrementalIndexer)
        mock2 = MagicMock(spec=IncrementalIndexer)

        call_count = [0]

        def build_side_effect(path: str) -> MagicMock:
            call_count[0] += 1
            return mock1 if call_count[0] == 1 else mock2

        with patch("src.rag.incremental_indexer._build_indexer", side_effect=build_side_effect):
            # Act
            instance1 = get_indexer(str(tmp_path))
            reset_indexer()
            instance2 = get_indexer(str(tmp_path))

        # Assert: 리셋 후 다른 인스턴스
        assert instance1 is not instance2

    def test_get_indexer_calls_build_only_once(self, tmp_path: Path) -> None:
        """get_indexer() 여러 번 호출 시 _build_indexer()가 1번만 호출되는지 검증."""
        # Arrange
        mock_instance = MagicMock(spec=IncrementalIndexer)

        with patch("src.rag.incremental_indexer._build_indexer", return_value=mock_instance) as mock_build:
            # Act
            get_indexer(str(tmp_path))
            get_indexer(str(tmp_path))
            get_indexer(str(tmp_path))

        # Assert: _build_indexer 1번만 호출
        assert mock_build.call_count == 1

    def test_build_indexer_returns_incremental_indexer(self, tmp_path: Path) -> None:
        """_build_indexer()가 IncrementalIndexer 인스턴스를 반환하는지 검증."""
        # Arrange — ASTChunker 등 실제 의존성 주입을 mock으로 대체
        mock_chunker = MagicMock()
        mock_scorer = MagicMock()
        mock_store = MagicMock()
        mock_embedder = MagicMock()
        mock_settings = MagicMock()
        mock_settings.rag.include_patterns = []
        mock_settings.rag.exclude_patterns = []

        with (
            patch("src.rag.incremental_indexer.BM25Scorer", return_value=mock_scorer),
            patch("src.rag.incremental_indexer.create_vector_store", return_value=mock_store),
            patch("src.rag.incremental_indexer.AnthropicEmbedder", return_value=mock_embedder),
            patch("src.rag.chunker.ASTChunker", return_value=mock_chunker),
            patch("src.infra.config.get_settings", return_value=mock_settings),
        ):
            # Act
            instance = _build_indexer(str(tmp_path))

        # Assert
        assert isinstance(instance, IncrementalIndexer)


# ---------------------------------------------------------------------------
# 8. 엣지 케이스 테스트
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """빈 프로젝트, 임베딩 실패, asyncio 루프 충돌 등 엣지 케이스 테스트."""

    def test_chunk_file_read_error_returns_empty(
        self,
        indexer: IncrementalIndexer,
        tmp_path: Path,
    ) -> None:
        """파일 읽기 실패(OSError) 시 빈 리스트를 반환하는지 검증."""
        # Arrange — 읽기 불가 파일
        bad_file = tmp_path / "bad.py"
        bad_file.write_text("content", encoding="utf-8")

        with patch("pathlib.Path.read_text", side_effect=OSError("permission denied")):
            # Act
            result = indexer._chunk_file(bad_file)

        # Assert
        assert result == []

    def test_chunk_file_unicode_error_returns_empty(
        self,
        indexer: IncrementalIndexer,
        tmp_path: Path,
    ) -> None:
        """UnicodeDecodeError 시 빈 리스트를 반환하는지 검증."""
        # Arrange
        bad_file = tmp_path / "binary_like.py"
        bad_file.write_bytes(b"\xff\xfe\x00\x01")  # 유효하지 않은 UTF-8

        # Act
        result = indexer._chunk_file(bad_file)

        # Assert
        assert result == []

    def test_fit_and_embed_empty_embedding_skips_store_add(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
    ) -> None:
        """임베딩이 빈 리스트일 때 store.add()가 호출되지 않는지 검증."""
        # Arrange — embedder가 빈 리스트를 반환
        mock_embedder = MagicMock()
        mock_embedder.embed = AsyncMock(return_value=[])

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )
        chunks = [_make_chunk("a.py")]

        # Act
        with patch("asyncio.run", return_value=[]):
            indexer._fit_and_embed(chunks)

        # Assert
        mock_store.add.assert_not_called()

    def test_fit_and_embed_partial_embeddings_adds_partial(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
    ) -> None:
        """임베딩이 청크보다 적을 때 가능한 만큼만 store.add()가 호출되는지 검증."""
        # Arrange — 청크 3개, 임베딩 2개 반환
        mock_embedder = MagicMock()
        mock_embedder.embed = AsyncMock(return_value=[[0.1, 0.2], [0.3, 0.4]])

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )
        chunks = [_make_chunk("a.py", 1), _make_chunk("a.py", 10), _make_chunk("a.py", 20)]

        # Act — asyncio.run이 2개 임베딩 반환
        with patch("asyncio.run", return_value=[[0.1, 0.2], [0.3, 0.4]]):
            indexer._fit_and_embed(chunks)

        # Assert: 처음 2개만 add
        call_args = mock_store.add.call_args
        added_chunks, added_embeddings = call_args[0]
        assert len(added_chunks) == 2
        assert len(added_embeddings) == 2

    def test_reembed_and_add_runtime_error_fallback(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
    ) -> None:
        """asyncio.run()이 RuntimeError를 던지면 new_event_loop()로 대체하는지 검증."""
        # Arrange — asyncio.run이 RuntimeError, 새 루프는 성공
        mock_embedder = MagicMock()
        mock_embedder.embed = AsyncMock(return_value=[[0.1, 0.2]])

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )
        chunks = [_make_chunk("a.py")]

        # asyncio.run → RuntimeError, new_event_loop().run_until_complete → 성공
        mock_loop = MagicMock()
        mock_loop.run_until_complete.return_value = [[0.1, 0.2]]

        with (
            patch("asyncio.run", side_effect=RuntimeError("no running loop")),
            patch("asyncio.new_event_loop", return_value=mock_loop),
        ):
            indexer._reembed_and_add(chunks)

        # Assert: store.add 호출됨 (새 루프 경로 실행)
        mock_store.add.assert_called_once()
        mock_loop.close.assert_called_once()

    def test_index_only_unsupported_extensions_returns_zero(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """지원하지 않는 확장자 파일만 있을 때 index()가 0을 반환하는지 검증."""
        # Arrange — .txt, .csv 파일만 있음
        (tmp_path / "data.txt").write_text("hello\n", encoding="utf-8")
        (tmp_path / "data.csv").write_text("a,b,c\n", encoding="utf-8")

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )

        # Act
        count = indexer.index()

        # Assert
        assert count == 0

    def test_update_modified_file_no_chunks_updates_count(
        self,
        tmp_path: Path,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """수정된 파일에서 청크가 없어도 updated 카운트가 증가하는지 검증."""
        # Arrange — chunker가 빈 리스트 반환
        empty_chunker = MagicMock()
        empty_chunker.chunk.return_value = []

        mod_file = tmp_path / "empty.py"
        mod_file.write_text("# empty\n", encoding="utf-8")

        indexer = IncrementalIndexer(
            chunker=empty_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )

        with patch.object(indexer, "_detect_changes", return_value=([], [mod_file], [])):
            result = indexer.update()

        # Assert: 청크가 없어도 updated 카운트 증가
        assert result["updated"] == 1

    def test_save_bm25_index_pickling_error_does_not_raise(
        self,
        indexer: IncrementalIndexer,
    ) -> None:
        """_save_bm25_index() 중 PicklingError가 발생해도 예외가 전파되지 않는지 검증."""
        with patch("pickle.dump", side_effect=pickle.PicklingError("cannot pickle")):
            indexer._save_bm25_index()

    def test_all_chunks_property_returns_copy_reference(
        self,
        indexer: IncrementalIndexer,
    ) -> None:
        """all_chunks 속성이 내부 리스트를 반환하는지 검증."""
        # Arrange
        chunk = _make_chunk()
        indexer._all_chunks = [chunk]

        # Act
        result = indexer.all_chunks

        # Assert
        assert result is indexer._all_chunks
        assert len(result) == 1

    def test_collect_files_skips_directories(
        self,
        indexer: IncrementalIndexer,
        tmp_path: Path,
    ) -> None:
        """디렉토리 항목은 is_file() 검사에서 건너뛰는지 검증 (라인 289 커버)."""
        # Arrange — 디렉토리와 파일 혼재
        sub_dir = tmp_path / "subdir"
        sub_dir.mkdir()
        # 디렉토리 자체는 is_file()=False이므로 건너뜀
        (sub_dir / "app.py").write_text("x = 1\n", encoding="utf-8")

        # Act
        files = indexer._collect_files()

        # Assert: 디렉토리가 아닌 파일만 수집
        assert all(f.is_file() for f in files)
        assert any(f.name == "app.py" for f in files)

    def test_reembed_and_add_partial_embeddings(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
    ) -> None:
        """_reembed_and_add()에서 임베딩이 청크보다 적을 때 부분 저장하는지 검증 (라인 371-373 커버)."""
        # Arrange — 청크 2개, 임베딩 1개 반환
        mock_embedder = MagicMock()
        mock_embedder.embed = AsyncMock(return_value=[[0.1, 0.2]])

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )
        chunks = [_make_chunk("a.py", 1), _make_chunk("a.py", 10)]

        # Act — asyncio.run이 1개 임베딩 반환
        with patch("asyncio.run", return_value=[[0.1, 0.2]]):
            indexer._reembed_and_add(chunks)

        # Assert: 처음 1개만 store.add에 전달
        call_args = mock_store.add.call_args[0]
        added_chunks, added_embeddings = call_args
        assert len(added_chunks) == 1
        assert len(added_embeddings) == 1

    def test_reembed_and_add_empty_embeddings_skips_store(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
    ) -> None:
        """_reembed_and_add()에서 임베딩이 빈 리스트일 때 store.add()를 호출하지 않는지 검증 (라인 374-375 커버)."""
        # Arrange — embedder가 빈 리스트 반환
        mock_embedder = MagicMock()
        mock_embedder.embed = AsyncMock(return_value=[])

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )
        chunks = [_make_chunk("a.py")]

        # Act
        with patch("asyncio.run", return_value=[]):
            indexer._reembed_and_add(chunks)

        # Assert
        mock_store.add.assert_not_called()


# ---------------------------------------------------------------------------
# 9. .gitignore 필터링 테스트
# ---------------------------------------------------------------------------


class TestGitignoreFiltering:
    """.gitignore 패턴 필터링 테스트."""

    def test_gitignore_log_files_excluded(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """.gitignore에 *.log 패턴이 있을 때 .log 파일이 인덱싱에서 제외되는지 검증."""
        # Arrange — .gitignore에 *.log 추가
        (tmp_path / ".gitignore").write_text("*.log\n", encoding="utf-8")
        (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
        # .log는 SUPPORTED_EXTENSIONS에 없으므로 실제 테스트를 위해 지원 목록을 패치
        # 대신 .gitignore 필터가 먼저 동작하는 것을 테스트
        (tmp_path / "debug.log").write_text("log data\n", encoding="utf-8")

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )

        # Act — SUPPORTED_EXTENSIONS에 .log를 추가한 상태에서 테스트
        with patch("src.rag.incremental_indexer.SUPPORTED_EXTENSIONS", frozenset({".py", ".log"})):
            files = indexer._collect_files()

        # Assert: .log 파일 제외, .py 파일 포함
        suffixes = {f.suffix for f in files}
        assert ".log" not in suffixes
        assert ".py" in suffixes

    def test_no_gitignore_collects_all_supported(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """.gitignore가 없을 때 기존 동작(지원 확장자 수집)을 유지하는지 검증."""
        # Arrange — .gitignore 없음
        (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "module.ts").write_text("const x = 1;\n", encoding="utf-8")

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )

        # Act
        files = indexer._collect_files()

        # Assert: gitignore 없으면 지원 파일 모두 수집
        suffixes = {f.suffix for f in files}
        assert ".py" in suffixes
        assert ".ts" in suffixes

    def test_gitignore_with_directory_pattern_excluded(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """.gitignore에 디렉토리 패턴(temp/)이 있을 때 해당 디렉토리 내 파일이 제외되는지 검증."""
        # Arrange — .gitignore에 temp/ 추가
        (tmp_path / ".gitignore").write_text("temp/\n", encoding="utf-8")
        (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        (temp_dir / "helper.py").write_text("def h(): pass\n", encoding="utf-8")

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
        )

        # Act
        files = indexer._collect_files()

        # Assert: temp/ 아래 파일 제외, main.py 포함
        file_names = {f.name for f in files}
        assert "helper.py" not in file_names
        assert "main.py" in file_names

    def test_exclude_patterns_applied(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """exclude_patterns 설정이 적용되어 해당 파일이 제외되는지 검증."""
        # Arrange — exclude_patterns에 *_test.py 패턴 설정
        (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "app_test.py").write_text("def test_x(): pass\n", encoding="utf-8")

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
            exclude_patterns=["*_test.py"],
        )

        # Act
        files = indexer._collect_files()

        # Assert: *_test.py 제외, app.py 포함
        file_names = {f.name for f in files}
        assert "app_test.py" not in file_names
        assert "app.py" in file_names

    def test_include_patterns_does_not_override_supported_extensions(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """include_patterns가 비어있을 때 SUPPORTED_EXTENSIONS 기본 동작이 유지되는지 검증."""
        # Arrange
        (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "data.csv").write_text("a,b\n", encoding="utf-8")

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
            include_patterns=[],
        )

        # Act
        files = indexer._collect_files()

        # Assert: .py 포함, .csv 제외
        suffixes = {f.suffix for f in files}
        assert ".py" in suffixes
        assert ".csv" not in suffixes

    def test_load_gitignore_spec_missing_returns_none(
        self,
        tmp_path: Path,
    ) -> None:
        """.gitignore가 없으면 _load_gitignore_spec()이 None을 반환하는지 검증."""
        result = _load_gitignore_spec(tmp_path)
        assert result is None

    def test_load_gitignore_spec_valid_file(
        self,
        tmp_path: Path,
    ) -> None:
        """유효한 .gitignore가 있으면 PathSpec 인스턴스를 반환하는지 검증."""
        (tmp_path / ".gitignore").write_text("*.log\n__pycache__/\n", encoding="utf-8")
        result = _load_gitignore_spec(tmp_path)
        assert result is not None

    def test_build_pathspec_empty_patterns_returns_none(self) -> None:
        """빈 패턴 목록으로 _build_pathspec()을 호출하면 None을 반환하는지 검증."""
        result = _build_pathspec([])
        assert result is None

    def test_build_pathspec_valid_patterns(self) -> None:
        """유효한 패턴 목록으로 PathSpec 인스턴스가 생성되는지 검증."""
        result = _build_pathspec(["*.log", "temp/"])
        assert result is not None

    def test_gitignore_corrupt_file_returns_none_and_no_crash(
        self,
        tmp_path: Path,
    ) -> None:
        """손상된 .gitignore 파일(읽기 실패)이 있어도 None을 반환하고 크래시 없는지 검증."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.log\n", encoding="utf-8")

        with patch("pathlib.Path.read_text", side_effect=OSError("permission denied")):
            result = _load_gitignore_spec(tmp_path)

        assert result is None

    def test_exclude_patterns_with_gitignore_both_applied(
        self,
        tmp_path: Path,
        mock_chunker: MagicMock,
        mock_scorer: MagicMock,
        mock_store: MagicMock,
        mock_embedder: MagicMock,
    ) -> None:
        """.gitignore와 exclude_patterns가 함께 적용되는지 검증."""
        # Arrange
        (tmp_path / ".gitignore").write_text("ignored_dir/\n", encoding="utf-8")
        (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "excluded.py").write_text("y = 2\n", encoding="utf-8")
        ignored_dir = tmp_path / "ignored_dir"
        ignored_dir.mkdir()
        (ignored_dir / "helper.py").write_text("def h(): pass\n", encoding="utf-8")

        indexer = IncrementalIndexer(
            chunker=mock_chunker,
            scorer=mock_scorer,
            store=mock_store,
            embedder=mock_embedder,
            project_path=str(tmp_path),
            exclude_patterns=["excluded.py"],
        )

        # Act
        files = indexer._collect_files()

        # Assert: gitignore 제외 + exclude_patterns 제외 모두 적용
        file_names = {f.name for f in files}
        assert "helper.py" not in file_names    # .gitignore로 제외
        assert "excluded.py" not in file_names  # exclude_patterns로 제외
        assert "app.py" in file_names           # 포함
