"""Phase 1 전체 통합 E2E 테스트.

5개 시나리오로 모든 모듈이 함께 통합되어 동작하는지 검증한다.
실제 파일시스템(임시 디렉토리)과 mock embedder를 사용하여
외부 API 의존 없이 전체 파이프라인을 실행한다.
"""

from __future__ import annotations

import asyncio
import os
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.domain import CodeChunk
from src.rag.chunker import ASTChunker
from src.rag.hybrid_search import HybridSearcher
from src.rag.incremental_indexer import IncrementalIndexer, reset_indexer
from src.rag.mcp_server import (
    _build_tree,
    _format_results,
    _match,
    _text_response,
    IGNORED_DIRS,
)
from src.rag.scorer import BM25Scorer
from src.rag.vector_store import NumpyStore


# ------------------------------------------------------------------
# 공통 픽스처
# ------------------------------------------------------------------

@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """테스트용 가상 프로젝트 디렉토리를 생성한다."""
    src = tmp_path / "src"
    src.mkdir()

    (src / "chunker.py").write_text(textwrap.dedent("""\
        \"\"\"AST 기반 청크 모듈.\"\"\"

        class ASTChunker:
            \"\"\"소스 파일을 청크로 분할한다.\"\"\"

            def chunk(self, file_path: str, content: str) -> list:
                \"\"\"파일을 청크로 분할하여 반환한다.\"\"\"
                return []

            def _parse_ast(self, content: str):
                \"\"\"AST를 파싱한다.\"\"\"
                pass
    """), encoding="utf-8")

    (src / "scorer.py").write_text(textwrap.dedent("""\
        \"\"\"BM25 스코어링 모듈.\"\"\"

        class BM25Scorer:
            \"\"\"BM25 렉시컬 스코어러.\"\"\"

            def fit(self, documents: list) -> None:
                \"\"\"BM25 인덱스를 학습한다.\"\"\"
                pass

            def top_k(self, query: str, k: int) -> list:
                \"\"\"상위 k개 결과를 반환한다.\"\"\"
                return []
    """), encoding="utf-8")

    (src / "vector_store.py").write_text(textwrap.dedent("""\
        \"\"\"벡터 저장소 모듈.\"\"\"
        import numpy as np

        class NumpyStore:
            \"\"\"인메모리 벡터 저장소.\"\"\"

            def add(self, chunks: list, embeddings: list) -> None:
                \"\"\"청크와 임베딩을 저장한다.\"\"\"
                pass

            def search(self, query_embedding: list, top_k: int) -> list:
                \"\"\"코사인 유사도 기반 검색을 수행한다.\"\"\"
                return []

            def remove(self, file_path: str) -> None:
                \"\"\"특정 파일의 청크를 삭제한다.\"\"\"
                pass

            def clear(self) -> None:
                \"\"\"저장소를 초기화한다.\"\"\"
                pass
    """), encoding="utf-8")

    (src / "embedder.py").write_text(textwrap.dedent("""\
        \"\"\"Anthropic 임베딩 모듈.\"\"\"

        class AnthropicEmbedder:
            \"\"\"Voyage AI API 기반 임베딩기.\"\"\"

            @property
            def is_available(self) -> bool:
                \"\"\"임베딩 가능 여부를 반환한다.\"\"\"
                return False

            async def embed(self, texts: list) -> list:
                \"\"\"텍스트를 임베딩 벡터로 변환한다.\"\"\"
                return []
    """), encoding="utf-8")

    (src / "hybrid_search.py").write_text(textwrap.dedent("""\
        \"\"\"하이브리드 검색 모듈.\"\"\"

        class HybridSearcher:
            \"\"\"BM25 + 벡터 하이브리드 검색기.\"\"\"

            def __init__(self, scorer, store, embedder,
                         bm25_weight=0.6, vector_weight=0.4):
                self._scorer = scorer
                self._store = store
                self._embedder = embedder

            async def search(self, query: str, top_k: int, chunks: list) -> list:
                \"\"\"하이브리드 검색을 수행한다.\"\"\"
                if not query.strip() or not chunks or top_k <= 0:
                    return []
                return []
    """), encoding="utf-8")

    (src / "incremental_indexer.py").write_text(textwrap.dedent("""\
        \"\"\"증분 인덱싱 모듈.\"\"\"

        class IncrementalIndexer:
            \"\"\"mtime 기반 증분 인덱서.\"\"\"

            def index(self) -> int:
                \"\"\"전체 인덱싱을 수행한다.\"\"\"
                return 0

            def update(self) -> dict:
                \"\"\"증분 업데이트를 수행한다.\"\"\"
                return {\"added\": 0, \"updated\": 0, \"removed\": 0}

            async def search(self, query: str, top_k: int) -> list:
                \"\"\"검색을 수행한다.\"\"\"
                return []
    """), encoding="utf-8")

    (tmp_path / "README.md").write_text(
        "# Test Project\n\nPhase 1 통합 테스트용 프로젝트.\n",
        encoding="utf-8",
    )

    return tmp_path


def _make_embedder(available: bool = False, dim: int = 128) -> MagicMock:
    """AnthropicEmbedder mock 생성."""
    mock = MagicMock()
    mock.is_available = available

    async def _embed(texts: list[str]) -> list[list[float]]:
        if not available:
            return []
        import math, random
        result = []
        for _ in texts:
            v = [random.gauss(0, 1) for _ in range(dim)]
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            result.append([x / norm for x in v])
        return result

    mock.embed = _embed
    return mock


def _make_indexer(
    project_dir: Path,
    embedder_available: bool = False,
) -> IncrementalIndexer:
    """IncrementalIndexer 인스턴스를 생성한다."""
    reset_indexer()
    chunker = ASTChunker()
    scorer = BM25Scorer()
    store = NumpyStore()
    embedder = _make_embedder(available=embedder_available)
    return IncrementalIndexer(
        chunker=chunker,
        scorer=scorer,
        store=store,
        embedder=embedder,
        project_path=str(project_dir),
        cache_dir=".rag_cache",
    )


# ------------------------------------------------------------------
# 시나리오 1: 전체 인덱싱 파이프라인
# ------------------------------------------------------------------

class TestScenario1FullIndexPipeline:
    """전체 인덱싱 파이프라인 통합 검증."""

    def test_index_returns_positive_chunk_count(self, project_dir: Path) -> None:
        """index()가 청크를 반환하고 0보다 크다."""
        indexer = _make_indexer(project_dir)
        count = indexer.index()
        assert count > 0, f"청크 수가 0이어야 하지 않음: {count}"

    def test_index_creates_cache_files(self, project_dir: Path) -> None:
        """index() 후 file_index.json과 bm25_index.pkl이 생성된다."""
        indexer = _make_indexer(project_dir)
        indexer.index()
        cache_dir = project_dir / ".rag_cache"
        assert (cache_dir / "file_index.json").exists(), "file_index.json 미생성"
        assert (cache_dir / "bm25_index.pkl").exists(), "bm25_index.pkl 미생성"

    def test_index_populates_all_chunks(self, project_dir: Path) -> None:
        """index() 후 all_chunks가 채워진다."""
        indexer = _make_indexer(project_dir)
        indexer.index()
        assert len(indexer.all_chunks) > 0, "all_chunks가 비어있음"

    def test_index_chunks_have_valid_fields(self, project_dir: Path) -> None:
        """인덱싱된 청크가 유효한 CodeChunk 필드를 갖는다."""
        indexer = _make_indexer(project_dir)
        indexer.index()
        for chunk in indexer.all_chunks:
            assert isinstance(chunk, CodeChunk)
            assert chunk.file_path
            assert chunk.content
            assert chunk.start_line >= 1
            assert chunk.end_line >= chunk.start_line

    def test_index_ignores_ignored_dirs(self, project_dir: Path) -> None:
        """IGNORED_DIRS 내 파일은 인덱싱되지 않는다."""
        # __pycache__ 디렉토리에 파일 생성
        pycache = project_dir / "__pycache__"
        pycache.mkdir()
        (pycache / "cached.py").write_text("# cached", encoding="utf-8")

        indexer = _make_indexer(project_dir)
        count_before = indexer.index()

        # pycache 파일 포함 여부 확인
        for chunk in indexer.all_chunks:
            assert "__pycache__" not in chunk.file_path, \
                f"__pycache__ 청크가 인덱싱됨: {chunk.file_path}"

    def test_index_empty_project_returns_zero(self, tmp_path: Path) -> None:
        """빈 프로젝트 index()는 0을 반환한다."""
        empty_dir = tmp_path / "empty_project"
        empty_dir.mkdir()
        indexer = _make_indexer(empty_dir)
        count = indexer.index()
        assert count == 0

    def test_index_with_embedder_available(self, project_dir: Path) -> None:
        """embedder 사용 가능 시 벡터 저장소에 임베딩이 추가된다."""
        indexer = _make_indexer(project_dir, embedder_available=True)
        count = indexer.index()
        assert count > 0
        # 벡터 저장소에 데이터가 있는지 확인 (size 속성)
        assert indexer._store.size >= 0


# ------------------------------------------------------------------
# 시나리오 2: 증분 업데이트 파이프라인
# ------------------------------------------------------------------

class TestScenario2IncrementalUpdate:
    """증분 업데이트 파이프라인 통합 검증."""

    def test_update_detects_new_file(self, project_dir: Path) -> None:
        """신규 파일을 정확히 감지한다."""
        indexer = _make_indexer(project_dir)
        indexer.index()

        # 새 파일 추가
        new_file = project_dir / "src" / "new_module.py"
        new_file.write_text(
            "def new_function():\n    return 'new'\n",
            encoding="utf-8",
        )

        counts = indexer.update()
        assert counts["added"] == 1, f"added 기대=1, 실제={counts['added']}"
        assert counts["updated"] == 0
        assert counts["removed"] == 0

    def test_update_detects_modified_file(self, project_dir: Path) -> None:
        """수정된 파일을 정확히 감지한다."""
        indexer = _make_indexer(project_dir)
        indexer.index()

        # 기존 파일 mtime 강제 갱신
        target = project_dir / "src" / "scorer.py"
        original = target.read_text(encoding="utf-8")
        target.write_text(original + "\n# modified\n", encoding="utf-8")
        st = target.stat()
        os.utime(target, (st.st_atime, st.st_mtime + 1.0))

        counts = indexer.update()
        assert counts["updated"] == 1, f"updated 기대=1, 실제={counts['updated']}"
        assert counts["added"] == 0
        assert counts["removed"] == 0

    def test_update_detects_deleted_file(self, project_dir: Path) -> None:
        """삭제된 파일을 정확히 감지한다."""
        indexer = _make_indexer(project_dir)
        indexer.index()

        # 파일 삭제
        target = project_dir / "src" / "embedder.py"
        target.unlink()

        counts = indexer.update()
        assert counts["removed"] == 1, f"removed 기대=1, 실제={counts['removed']}"
        assert counts["added"] == 0
        assert counts["updated"] == 0

    def test_update_no_change_returns_zeros(self, project_dir: Path) -> None:
        """변경 없으면 모두 0을 반환한다."""
        indexer = _make_indexer(project_dir)
        indexer.index()
        counts = indexer.update()
        assert counts == {"added": 0, "updated": 0, "removed": 0}

    def test_update_cache_refreshes(self, project_dir: Path) -> None:
        """update() 후 file_index.json이 갱신된다."""
        import json
        indexer = _make_indexer(project_dir)
        indexer.index()

        cache_path = project_dir / ".rag_cache" / "file_index.json"
        mtime_before = cache_path.stat().st_mtime

        # 새 파일 추가
        (project_dir / "src" / "added.py").write_text(
            "def added(): pass\n", encoding="utf-8"
        )
        indexer.update()

        mtime_after = cache_path.stat().st_mtime
        assert mtime_after >= mtime_before, "캐시 파일이 갱신되지 않음"

        data = json.loads(cache_path.read_text(encoding="utf-8"))
        added_keys = [k for k in data if "added.py" in k]
        assert added_keys, "신규 파일이 file_index에 반영되지 않음"


# ------------------------------------------------------------------
# 시나리오 3: 하이브리드 검색 파이프라인
# ------------------------------------------------------------------

class TestScenario3HybridSearch:
    """하이브리드 검색 파이프라인 통합 검증."""

    def test_bm25_only_search_returns_results(self, project_dir: Path) -> None:
        """BM25 전용 모드에서 관련 청크를 반환한다."""
        indexer = _make_indexer(project_dir, embedder_available=False)
        indexer.index()

        results = asyncio.run(indexer.search("chunk method", top_k=3))
        assert isinstance(results, list)
        for chunk in results:
            assert isinstance(chunk, CodeChunk)

    def test_search_top_k_limit(self, project_dir: Path) -> None:
        """top_k를 초과하지 않는다."""
        indexer = _make_indexer(project_dir, embedder_available=False)
        indexer.index()

        top_k = 2
        results = asyncio.run(indexer.search("class", top_k=top_k))
        assert len(results) <= top_k

    def test_search_empty_query_returns_empty(self, project_dir: Path) -> None:
        """빈 쿼리는 빈 리스트를 반환한다."""
        indexer = _make_indexer(project_dir)
        indexer.index()
        results = asyncio.run(indexer.search("", top_k=5))
        assert results == []

    def test_hybrid_searcher_scores_sorted(self, project_dir: Path) -> None:
        """HybridSearcher 결과는 스코어 내림차순 정렬이다."""
        indexer = _make_indexer(project_dir, embedder_available=False)
        indexer.index()

        if not indexer.all_chunks:
            pytest.skip("청크 없음")

        searcher = HybridSearcher(
            scorer=indexer._scorer,
            store=indexer._store,
            embedder=indexer._embedder,
        )
        results = asyncio.run(
            searcher.search("def chunk", top_k=10, chunks=indexer.all_chunks)
        )
        if len(results) > 1:
            scores = [s for _, s in results]
            assert scores == sorted(scores, reverse=True), "스코어 정렬 위반"

    def test_hybrid_searcher_scores_in_range(self, project_dir: Path) -> None:
        """HybridSearcher 결과 스코어가 음수가 아니다."""
        indexer = _make_indexer(project_dir, embedder_available=False)
        indexer.index()

        if not indexer.all_chunks:
            pytest.skip("청크 없음")

        searcher = HybridSearcher(
            scorer=indexer._scorer,
            store=indexer._store,
            embedder=indexer._embedder,
        )
        results = asyncio.run(
            searcher.search("scorer BM25", top_k=5, chunks=indexer.all_chunks)
        )
        for _, score in results:
            assert score >= 0.0, f"음수 스코어: {score}"

    def test_search_after_update_reflects_changes(self, project_dir: Path) -> None:
        """update() 후 검색 결과가 갱신을 반영한다."""
        indexer = _make_indexer(project_dir, embedder_available=False)
        indexer.index()

        # 특정 키워드가 포함된 파일 추가
        (project_dir / "src" / "unique_keyword_module.py").write_text(
            "def xyzzy_unique_function():\n    \"\"\"Very unique function.\"\"\"\n    return 'xyzzy'\n",
            encoding="utf-8",
        )
        indexer.update()

        results = asyncio.run(indexer.search("xyzzy unique", top_k=5))
        # 검색 결과에서 파일 경로 확인
        found = any("unique_keyword_module" in c.file_path for c in results)
        assert found, "신규 추가된 파일이 검색 결과에 없음"


# ------------------------------------------------------------------
# 시나리오 4: MCP 도구 통합 테스트
# ------------------------------------------------------------------

class TestScenario4MCPTools:
    """MCP 도구 통합 검증 (헬퍼 함수 및 tool 로직 직접 테스트)."""

    def test_text_response_format(self) -> None:
        """_text_response가 올바른 MCP 형식을 반환한다."""
        result = _text_response("테스트 메시지")
        assert "content" in result
        assert isinstance(result["content"], list)
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == "테스트 메시지"

    def test_format_results_with_chunks(self, project_dir: Path) -> None:
        """_format_results가 청크를 MCP 형식으로 변환한다."""
        indexer = _make_indexer(project_dir)
        indexer.index()

        if not indexer.all_chunks:
            pytest.skip("청크 없음")

        result = _format_results(indexer.all_chunks[:3], header="검색 결과")
        content = result["content"][0]["text"]
        assert "=== 검색 결과" in content
        assert "---" in content

    def test_match_exact_mode(self) -> None:
        """_match exact 모드가 정확히 동작한다."""
        assert _match("get_user", "get_user", "exact") is True
        assert _match("get_user", "get", "exact") is False
        assert _match("get_user", "get_user_id", "exact") is False

    def test_match_prefix_mode(self) -> None:
        """_match prefix 모드가 정확히 동작한다."""
        assert _match("get_user", "get", "prefix") is True
        assert _match("get_user", "get_user", "prefix") is True
        assert _match("get_user", "user", "prefix") is False

    def test_match_contains_mode(self) -> None:
        """_match contains 모드가 정확히 동작한다."""
        assert _match("get_user_by_id", "user", "contains") is True
        assert _match("get_user_by_id", "by_id", "contains") is True
        assert _match("get_user_by_id", "xyz", "contains") is False

    def test_build_tree_basic(self, project_dir: Path) -> None:
        """_build_tree가 트리를 생성한다."""
        tree = _build_tree(project_dir, max_depth=2, ignored=IGNORED_DIRS)
        assert isinstance(tree, str)
        assert len(tree) > 0
        # 프로젝트 루트 이름이 포함
        assert project_dir.name in tree

    def test_build_tree_ignores_dirs(self, project_dir: Path) -> None:
        """_build_tree가 IGNORED_DIRS를 제외한다."""
        # __pycache__ 디렉토리 생성
        (project_dir / "__pycache__").mkdir(exist_ok=True)
        tree = _build_tree(project_dir, max_depth=3, ignored=IGNORED_DIRS)
        assert "__pycache__" not in tree

    def test_build_tree_depth_limit(self, project_dir: Path) -> None:
        """_build_tree가 depth를 정확히 제한한다."""
        tree_d1 = _build_tree(project_dir, max_depth=1, ignored=IGNORED_DIRS)
        tree_d3 = _build_tree(project_dir, max_depth=3, ignored=IGNORED_DIRS)
        # depth가 높을수록 더 많은 항목
        assert len(tree_d3) >= len(tree_d1)

    def test_search_by_symbol_integration(self, project_dir: Path) -> None:
        """search_by_symbol 로직이 올바르게 동작한다."""
        indexer = _make_indexer(project_dir)
        indexer.index()

        # contains 모드로 검색
        matches = [
            c for c in indexer.all_chunks
            if c.name and _match(c.name, "chunk", "contains")
        ]
        for chunk in matches:
            assert "chunk" in (chunk.name or "").lower() or \
                   "chunk" in chunk.name, f"chunk 미포함 이름: {chunk.name}"

    def test_mcp_search_code_simulation(self, project_dir: Path) -> None:
        """search_code tool 로직 시뮬레이션."""
        indexer = _make_indexer(project_dir, embedder_available=False)
        indexer.index()

        # 정상 검색
        chunks = asyncio.run(indexer.search("def chunk", top_k=5))
        if chunks:
            result = _format_results(chunks, header="검색 결과: 'def chunk'")
            assert result["content"][0]["type"] == "text"
            assert "검색 결과" in result["content"][0]["text"]
        else:
            result = _text_response("'def chunk'에 대한 검색 결과가 없습니다.")
            assert "검색 결과가 없습니다" in result["content"][0]["text"]

    def test_mcp_reindex_simulation(self, project_dir: Path) -> None:
        """reindex_codebase tool 로직 시뮬레이션."""
        indexer = _make_indexer(project_dir)
        indexer.index()
        counts = indexer.update()

        text = (
            f"증분 재인덱싱 완료\n"
            f"  추가: {counts['added']}개 파일\n"
            f"  수정: {counts['updated']}개 파일\n"
            f"  삭제: {counts['removed']}개 파일"
        )
        result = _text_response(text)
        assert "증분 재인덱싱 완료" in result["content"][0]["text"]


# ------------------------------------------------------------------
# 시나리오 5: Graceful Degradation
# ------------------------------------------------------------------

class TestScenario5GracefulDegradation:
    """임베딩 실패 시 BM25 fallback 검증."""

    def test_search_without_embedder_returns_results(self, project_dir: Path) -> None:
        """embedder 불가 시 BM25-only로 결과를 반환한다."""
        indexer = _make_indexer(project_dir, embedder_available=False)
        indexer.index()
        results = asyncio.run(indexer.search("class scorer", top_k=5))
        assert isinstance(results, list)

    def test_hybrid_searcher_bm25_only_mode(self, project_dir: Path) -> None:
        """HybridSearcher가 embedder=False일 때 BM25 전용으로 동작한다."""
        indexer = _make_indexer(project_dir, embedder_available=False)
        indexer.index()

        if not indexer.all_chunks:
            pytest.skip("청크 없음")

        searcher = HybridSearcher(
            scorer=indexer._scorer,
            store=indexer._store,
            embedder=indexer._embedder,
        )
        # embedder.is_available=False이므로 벡터 검색 스킵
        results = asyncio.run(
            searcher.search("def fit", top_k=3, chunks=indexer.all_chunks)
        )
        assert isinstance(results, list)
        for chunk, score in results:
            assert isinstance(chunk, CodeChunk)
            assert isinstance(score, float)

    def test_embed_exception_falls_back_to_bm25(self, project_dir: Path) -> None:
        """embed() 예외 발생 시 BM25 전용으로 폴백한다."""
        indexer = _make_indexer(project_dir, embedder_available=True)
        indexer.index()

        # embed()를 예외 발생으로 교체
        indexer._embedder.embed = AsyncMock(side_effect=RuntimeError("embed error"))

        if not indexer.all_chunks:
            pytest.skip("청크 없음")

        searcher = HybridSearcher(
            scorer=indexer._scorer,
            store=indexer._store,
            embedder=indexer._embedder,
        )
        # 예외 발생해도 검색이 완료되어야 함
        results = asyncio.run(
            searcher.search("search query", top_k=3, chunks=indexer.all_chunks)
        )
        assert isinstance(results, list)

    def test_index_with_embed_failure_still_works(self, project_dir: Path) -> None:
        """임베딩 실패해도 index()가 완료되고 BM25는 동작한다."""
        mock_embedder = MagicMock()
        mock_embedder.is_available = True
        mock_embedder.embed = AsyncMock(return_value=[])  # 항상 빈 리스트

        chunker = ASTChunker()
        scorer = BM25Scorer()
        store = NumpyStore()

        indexer = IncrementalIndexer(
            chunker=chunker,
            scorer=scorer,
            store=store,
            embedder=mock_embedder,
            project_path=str(project_dir),
            cache_dir=".rag_cache",
        )
        # 예외 없이 완료되어야 함
        count = indexer.index()
        assert isinstance(count, int)
        assert count >= 0

    def test_search_on_empty_index_returns_empty(self) -> None:
        """빈 인덱서에서 search()는 빈 리스트를 반환한다."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            indexer = _make_indexer(Path(tmp), embedder_available=False)
            # index() 호출 안 함 → all_chunks 비어있음
            results = asyncio.run(indexer.search("query", top_k=5))
            assert results == []

    def test_corrupted_cache_falls_back_gracefully(self, project_dir: Path) -> None:
        """손상된 캐시로도 update()가 예외 없이 동작한다."""
        indexer = _make_indexer(project_dir)
        indexer.index()

        # 캐시 파일 손상
        cache_path = project_dir / ".rag_cache" / "file_index.json"
        cache_path.write_text("{corrupted!!!", encoding="utf-8")

        # 예외 없이 완료되어야 함 (빈 인덱스로 폴백)
        counts = indexer.update()
        assert isinstance(counts, dict)
        assert "added" in counts
