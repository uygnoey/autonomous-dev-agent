"""RAG MCP 서버 유닛 테스트.

테스트 대상: src/rag/mcp_server.py
  — build_rag_mcp_server() 내 5개 MCP 도구, 헬퍼 함수(_format_results, _text_response, _match, _build_tree)
커버리지 목표: 100%

테스트 전략:
  build_rag_mcp_server()는 클로저(closure) 안에 5개 SdkMcpTool을 정의한다.
  각 SdkMcpTool 인스턴스는 .handler 속성으로 async 함수를 노출하므로,
  create_sdk_mcp_server()에 전달된 tools 목록에서 SdkMcpTool.handler를 추출한다.

  helper: _make_server() — mock indexer로 서버를 빌드하고 도구 핸들러 딕셔너리를 반환한다.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.domain import CodeChunk
from src.rag.incremental_indexer import IGNORED_DIRS
from src.rag.mcp_server import (
    _build_tree,
    _format_results,
    _match,
    _text_response,
    build_rag_mcp_server,
)


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------


def _make_chunk(
    file_path: str = "src/a.py",
    start_line: int = 1,
    name: str | None = "foo",
    chunk_type: str = "function",
    content: str = "def foo(): pass",
) -> CodeChunk:
    """테스트용 CodeChunk를 생성하는 헬퍼."""
    return CodeChunk(
        file_path=file_path,
        content=content,
        start_line=start_line,
        end_line=start_line + 4,
        chunk_type=chunk_type,
        name=name,
    )


def _make_server(project_path: str, mock_indexer: MagicMock) -> dict[str, object]:
    """mock indexer를 주입하여 MCP 서버를 빌드하고 도구 핸들러 딕셔너리를 반환한다.

    @tool 데코레이터는 async 함수를 SdkMcpTool(name, ..., handler=fn)으로 래핑한다.
    create_sdk_mcp_server()에 전달된 tools 목록에서 각 SdkMcpTool.handler를 추출한다.
    """
    captured_tools: list = []

    def fake_create_sdk_mcp_server(name: str, version: str = "1.0.0", tools=None):
        if tools:
            captured_tools.extend(tools)
        return MagicMock()

    with (
        patch("src.rag.mcp_server.get_indexer", return_value=mock_indexer),
        patch("src.rag.mcp_server.create_sdk_mcp_server", side_effect=fake_create_sdk_mcp_server),
    ):
        build_rag_mcp_server(project_path)

    return {sdk_tool.name: sdk_tool.handler for sdk_tool in captured_tools}


@pytest.fixture
def mock_indexer() -> MagicMock:
    """IncrementalIndexer mock 픽스처."""
    indexer = MagicMock()
    indexer.search = AsyncMock(return_value=[])
    indexer.update = MagicMock(return_value={"added": 0, "updated": 0, "removed": 0})
    indexer.all_chunks = []
    indexer._embedder = MagicMock()
    indexer._embedder.embed = AsyncMock(return_value=[])
    indexer._store = MagicMock()
    indexer._store.search.return_value = []
    return indexer


@pytest.fixture
def handlers(mock_indexer: MagicMock, tmp_path: Path) -> dict[str, object]:
    """5개 MCP 도구 핸들러 딕셔너리를 반환하는 픽스처."""
    return _make_server(str(tmp_path), mock_indexer)


# ---------------------------------------------------------------------------
# 1. search_code 도구 테스트
# ---------------------------------------------------------------------------


class TestSearchCode:
    """search_code 도구 테스트."""

    @pytest.mark.asyncio
    async def test_search_code_calls_indexer_search(
        self,
        handlers: dict,
        mock_indexer: MagicMock,
    ) -> None:
        """indexer.search()가 호출되는지 검증."""
        # Arrange
        mock_indexer.search.return_value = [_make_chunk()]
        handler = handlers["search_code"]

        # Act
        await handler({"query": "foo function", "top_k": 3})

        # Assert
        mock_indexer.search.assert_called_once_with("foo function", top_k=3)

    @pytest.mark.asyncio
    async def test_search_code_returns_mcp_format(
        self,
        handlers: dict,
        mock_indexer: MagicMock,
    ) -> None:
        """결과가 MCP 표준 응답 형식인지 검증."""
        # Arrange
        mock_indexer.search.return_value = [_make_chunk()]
        handler = handlers["search_code"]

        # Act
        result = await handler({"query": "foo", "top_k": 5})

        # Assert
        assert "content" in result
        assert isinstance(result["content"], list)
        assert result["content"][0]["type"] == "text"
        assert isinstance(result["content"][0]["text"], str)

    @pytest.mark.asyncio
    async def test_search_code_default_top_k(
        self,
        handlers: dict,
        mock_indexer: MagicMock,
    ) -> None:
        """top_k 기본값 5가 사용되는지 검증."""
        # Arrange
        mock_indexer.search.return_value = [_make_chunk()]
        handler = handlers["search_code"]

        # Act
        await handler({"query": "bar"})

        # Assert: top_k=5가 기본값
        mock_indexer.search.assert_called_once_with("bar", top_k=5)

    @pytest.mark.asyncio
    async def test_search_code_empty_results(
        self,
        handlers: dict,
        mock_indexer: MagicMock,
    ) -> None:
        """검색 결과 없을 때 빈 결과 메시지를 반환하는지 검증."""
        # Arrange — 빈 리스트 반환
        mock_indexer.search.return_value = []
        handler = handlers["search_code"]

        # Act
        result = await handler({"query": "nonexistent"})

        # Assert: 결과 없음 메시지 포함
        text = result["content"][0]["text"]
        assert "nonexistent" in text
        assert "없습니다" in text

    @pytest.mark.asyncio
    async def test_search_code_empty_query_returns_error(
        self,
        handlers: dict,
    ) -> None:
        """빈 쿼리일 때 에러 메시지를 반환하는지 검증."""
        # Arrange
        handler = handlers["search_code"]

        # Act
        result = await handler({"query": ""})

        # Assert
        text = result["content"][0]["text"]
        assert "query" in text

    @pytest.mark.asyncio
    async def test_search_code_whitespace_query_returns_error(
        self,
        handlers: dict,
    ) -> None:
        """공백만 있는 쿼리일 때 에러 메시지를 반환하는지 검증."""
        # Arrange
        handler = handlers["search_code"]

        # Act
        result = await handler({"query": "   "})

        # Assert
        text = result["content"][0]["text"]
        assert "query" in text

    @pytest.mark.asyncio
    async def test_search_code_exception_returns_error_text(
        self,
        handlers: dict,
        mock_indexer: MagicMock,
    ) -> None:
        """indexer.search() 예외 발생 시 에러 텍스트를 반환하는지 검증."""
        # Arrange
        mock_indexer.search.side_effect = RuntimeError("search failed")
        handler = handlers["search_code"]

        # Act
        result = await handler({"query": "crash"})

        # Assert: 에러 메시지 포함
        text = result["content"][0]["text"]
        assert "오류" in text


# ---------------------------------------------------------------------------
# 2. reindex_codebase 도구 테스트
# ---------------------------------------------------------------------------


class TestReindexCodebase:
    """reindex_codebase 도구 테스트."""

    @pytest.mark.asyncio
    async def test_reindex_calls_indexer_update(
        self,
        handlers: dict,
        mock_indexer: MagicMock,
    ) -> None:
        """indexer.update()가 호출되는지 검증."""
        # Arrange
        handler = handlers["reindex_codebase"]

        # Act
        await handler({})

        # Assert
        mock_indexer.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_reindex_returns_counts_text(
        self,
        handlers: dict,
        mock_indexer: MagicMock,
    ) -> None:
        """added/updated/removed 카운트가 텍스트에 포함되는지 검증."""
        # Arrange
        mock_indexer.update.return_value = {"added": 3, "updated": 2, "removed": 1}
        handler = handlers["reindex_codebase"]

        # Act
        result = await handler({})

        # Assert
        text = result["content"][0]["text"]
        assert "3" in text
        assert "2" in text
        assert "1" in text
        assert "추가" in text
        assert "수정" in text
        assert "삭제" in text

    @pytest.mark.asyncio
    async def test_reindex_no_changes_scenario(
        self,
        handlers: dict,
        mock_indexer: MagicMock,
    ) -> None:
        """변경 없음 시나리오에서 0이 포함된 텍스트를 반환하는지 검증."""
        # Arrange
        mock_indexer.update.return_value = {"added": 0, "updated": 0, "removed": 0}
        handler = handlers["reindex_codebase"]

        # Act
        result = await handler({})

        # Assert
        text = result["content"][0]["text"]
        assert "0" in text

    @pytest.mark.asyncio
    async def test_reindex_returns_mcp_format(
        self,
        handlers: dict,
    ) -> None:
        """반환값이 MCP 표준 응답 형식인지 검증."""
        # Arrange
        handler = handlers["reindex_codebase"]

        # Act
        result = await handler({})

        # Assert
        assert "content" in result
        assert result["content"][0]["type"] == "text"

    @pytest.mark.asyncio
    async def test_reindex_exception_returns_error_text(
        self,
        handlers: dict,
        mock_indexer: MagicMock,
    ) -> None:
        """update() 예외 발생 시 에러 텍스트를 반환하는지 검증."""
        # Arrange
        mock_indexer.update.side_effect = RuntimeError("update failed")
        handler = handlers["reindex_codebase"]

        # Act
        result = await handler({})

        # Assert
        text = result["content"][0]["text"]
        assert "오류" in text


# ---------------------------------------------------------------------------
# 3. search_by_symbol 도구 테스트
# ---------------------------------------------------------------------------


class TestSearchBySymbol:
    """search_by_symbol 도구 테스트."""

    @pytest.mark.asyncio
    async def test_exact_mode_matches_exactly(
        self,
        handlers: dict,
        mock_indexer: MagicMock,
    ) -> None:
        """exact 모드에서 이름이 정확히 일치하는 청크만 반환하는지 검증."""
        # Arrange — "get_user", "get_user_info" 두 청크
        chunks = [
            _make_chunk(name="get_user"),
            _make_chunk(name="get_user_info"),
        ]
        mock_indexer.all_chunks = chunks
        handler = handlers["search_by_symbol"]

        # Act
        result = await handler({"name": "get_user", "mode": "exact"})

        # Assert: "get_user"만 매칭, "get_user_info"는 미포함
        text = result["content"][0]["text"]
        assert "get_user" in text
        assert "Name: get_user_info" not in text

    @pytest.mark.asyncio
    async def test_prefix_mode_matches_prefix(
        self,
        handlers: dict,
        mock_indexer: MagicMock,
    ) -> None:
        """prefix 모드에서 접두사가 일치하는 청크만 반환하는지 검증."""
        # Arrange
        chunks = [
            _make_chunk(name="get_user"),
            _make_chunk(name="get_user_info"),
            _make_chunk(name="create_user"),  # 접두사 불일치
        ]
        mock_indexer.all_chunks = chunks
        handler = handlers["search_by_symbol"]

        # Act
        result = await handler({"name": "get_", "mode": "prefix"})

        # Assert: "get_"으로 시작하는 두 청크만 매칭
        text = result["content"][0]["text"]
        assert "get_user" in text
        assert "Name: create_user" not in text

    @pytest.mark.asyncio
    async def test_contains_mode_matches_substring(
        self,
        handlers: dict,
        mock_indexer: MagicMock,
    ) -> None:
        """contains 모드(기본값)에서 이름에 쿼리가 포함된 청크만 반환하는지 검증."""
        # Arrange
        chunks = [
            _make_chunk(name="validate_user_input"),
            _make_chunk(name="user_service"),
            _make_chunk(name="create_post"),  # "user" 미포함
        ]
        mock_indexer.all_chunks = chunks
        handler = handlers["search_by_symbol"]

        # Act — mode 기본값 = "contains"
        result = await handler({"name": "user"})

        # Assert: "user"가 포함된 두 청크만 매칭
        text = result["content"][0]["text"]
        assert "validate_user_input" in text
        assert "user_service" in text
        assert "Name: create_post" not in text

    @pytest.mark.asyncio
    async def test_no_matches_returns_empty_message(
        self,
        handlers: dict,
        mock_indexer: MagicMock,
    ) -> None:
        """매칭 없을 때 결과 없음 메시지를 반환하는지 검증."""
        # Arrange
        mock_indexer.all_chunks = [_make_chunk(name="foo")]
        handler = handlers["search_by_symbol"]

        # Act
        result = await handler({"name": "xyz_nonexistent", "mode": "exact"})

        # Assert
        text = result["content"][0]["text"]
        assert "없습니다" in text

    @pytest.mark.asyncio
    async def test_anonymous_chunk_name_none_filtered(
        self,
        handlers: dict,
        mock_indexer: MagicMock,
    ) -> None:
        """name=None인 익명 청크는 심볼 매칭에서 제외되는지 검증."""
        # Arrange — name이 None인 청크와 유효한 청크
        chunks = [
            _make_chunk(name=None),
            _make_chunk(name="foo"),
        ]
        mock_indexer.all_chunks = chunks
        handler = handlers["search_by_symbol"]

        # Act: "foo"로 contains 검색
        result = await handler({"name": "foo", "mode": "contains"})

        # Assert: 결과에 "foo" 1개만 포함 (None은 필터됨)
        text = result["content"][0]["text"]
        assert "Name: foo" in text
        # 1개 (anonymous)
        assert text.count("(anonymous)") == 0

    @pytest.mark.asyncio
    async def test_empty_name_returns_error(
        self,
        handlers: dict,
    ) -> None:
        """name이 비어 있을 때 에러 메시지를 반환하는지 검증."""
        # Arrange
        handler = handlers["search_by_symbol"]

        # Act
        result = await handler({"name": ""})

        # Assert
        text = result["content"][0]["text"]
        assert "name" in text

    @pytest.mark.asyncio
    async def test_invalid_mode_returns_error(
        self,
        handlers: dict,
    ) -> None:
        """잘못된 mode 값일 때 에러 메시지를 반환하는지 검증."""
        # Arrange
        handler = handlers["search_by_symbol"]

        # Act
        result = await handler({"name": "foo", "mode": "fuzzy"})

        # Assert
        text = result["content"][0]["text"]
        assert "fuzzy" in text
        assert "잘못된" in text


# ---------------------------------------------------------------------------
# 4. get_file_structure 도구 테스트
# ---------------------------------------------------------------------------


class TestGetFileStructure:
    """get_file_structure 도구 테스트."""

    @pytest.mark.asyncio
    async def test_returns_tree_for_project_root(
        self,
        handlers: dict,
        tmp_path: Path,
    ) -> None:
        """기본 경로(project root)에서 트리를 반환하는지 검증."""
        # Arrange — tmp_path에 파일 생성
        (tmp_path / "main.py").write_text("x=1\n", encoding="utf-8")
        handler = handlers["get_file_structure"]

        # Act — path="" → project_path 사용
        result = await handler({"path": "", "depth": 3})

        # Assert
        text = result["content"][0]["text"]
        assert tmp_path.name in text

    @pytest.mark.asyncio
    async def test_custom_depth_limits_traversal(
        self,
        handlers: dict,
        tmp_path: Path,
    ) -> None:
        """depth 파라미터가 트리 깊이를 제한하는지 검증."""
        # Arrange — 3단계 중첩 디렉토리
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "deep.py").write_text("x=1\n", encoding="utf-8")
        handler = handlers["get_file_structure"]

        # Act: depth=1 → root(0), a(1)까지이므로 b는 미표시
        result = await handler({"path": str(tmp_path), "depth": 1})

        text = result["content"][0]["text"]
        assert "a" in text
        assert "b" not in text

    @pytest.mark.asyncio
    async def test_ignored_dirs_excluded(
        self,
        handlers: dict,
        tmp_path: Path,
    ) -> None:
        """IGNORED_DIRS 내 디렉토리가 트리에서 제외되는지 검증."""
        # Arrange — __pycache__, .git 디렉토리 생성
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / ".git").mkdir()
        (tmp_path / "src").mkdir()
        handler = handlers["get_file_structure"]

        # Act
        result = await handler({"path": str(tmp_path), "depth": 3})

        text = result["content"][0]["text"]
        assert "__pycache__" not in text
        assert ".git" not in text
        assert "src" in text

    @pytest.mark.asyncio
    async def test_nonexistent_path_returns_error(
        self,
        handlers: dict,
    ) -> None:
        """존재하지 않는 경로일 때 에러 메시지를 반환하는지 검증."""
        # Arrange
        handler = handlers["get_file_structure"]

        # Act
        result = await handler({"path": "/nonexistent/path/abc123"})

        # Assert
        text = result["content"][0]["text"]
        assert "찾을 수 없습니다" in text

    @pytest.mark.asyncio
    async def test_file_path_returns_error(
        self,
        handlers: dict,
        tmp_path: Path,
    ) -> None:
        """파일 경로(디렉토리 아님)일 때 에러 메시지를 반환하는지 검증."""
        # Arrange — 파일 생성
        f = tmp_path / "file.py"
        f.write_text("x=1\n", encoding="utf-8")
        handler = handlers["get_file_structure"]

        # Act
        result = await handler({"path": str(f)})

        # Assert
        text = result["content"][0]["text"]
        assert "디렉토리" in text

    @pytest.mark.asyncio
    async def test_default_depth_is_3(
        self,
        handlers: dict,
        tmp_path: Path,
    ) -> None:
        """depth 미지정 시 기본값 3을 사용하는지 검증."""
        # Arrange — 4단계 중첩: subroot/alpha/beta/gamma/delta
        deep = tmp_path / "subroot" / "alpha" / "beta" / "gamma"
        deep.mkdir(parents=True)
        (deep / "delta.py").write_text("x=1\n", encoding="utf-8")
        handler = handlers["get_file_structure"]

        # Act — depth 미지정 (기본 3)
        result = await handler({"path": str(tmp_path)})

        text = result["content"][0]["text"]
        # depth=3: root(0), subroot(1), alpha(2), beta(3) — gamma는 depth=4라 미포함
        assert "alpha" in text
        assert "beta" in text
        assert "gamma" not in text
        assert "delta.py" not in text

    @pytest.mark.asyncio
    async def test_returns_mcp_format(
        self,
        handlers: dict,
        tmp_path: Path,
    ) -> None:
        """반환값이 MCP 표준 응답 형식인지 검증."""
        # Arrange
        handler = handlers["get_file_structure"]

        # Act
        result = await handler({"path": str(tmp_path)})

        # Assert
        assert "content" in result
        assert result["content"][0]["type"] == "text"

    @pytest.mark.asyncio
    async def test_build_tree_exception_returns_error_text(
        self,
        handlers: dict,
        tmp_path: Path,
    ) -> None:
        """_build_tree() 예외 발생 시 에러 텍스트를 반환하는지 검증 (라인 212-213 커버)."""
        # Arrange — _build_tree가 예외를 발생시키도록 mock
        handler = handlers["get_file_structure"]

        with patch("src.rag.mcp_server._build_tree", side_effect=PermissionError("access denied")):
            # Act
            result = await handler({"path": str(tmp_path)})

        # Assert
        text = result["content"][0]["text"]
        assert "오류" in text


# ---------------------------------------------------------------------------
# 5. get_similar_patterns 도구 테스트
# ---------------------------------------------------------------------------


class TestGetSimilarPatterns:
    """get_similar_patterns 도구 테스트."""

    @pytest.mark.asyncio
    async def test_calls_embedder_embed(
        self,
        handlers: dict,
        mock_indexer: MagicMock,
    ) -> None:
        """embedder.embed()가 코드 스니펫으로 호출되는지 검증."""
        # Arrange
        mock_indexer._embedder.embed = AsyncMock(return_value=[[0.1, 0.2]])
        mock_indexer._store.search.return_value = [(_make_chunk(), 0.9)]
        handler = handlers["get_similar_patterns"]

        # Act
        await handler({"code_snippet": "def foo(): pass", "top_k": 3})

        # Assert
        mock_indexer._embedder.embed.assert_called_once_with(["def foo(): pass"])

    @pytest.mark.asyncio
    async def test_calls_store_search(
        self,
        handlers: dict,
        mock_indexer: MagicMock,
    ) -> None:
        """store.search()가 임베딩과 top_k로 호출되는지 검증."""
        # Arrange
        vec = [0.1, 0.2, 0.3]
        mock_indexer._embedder.embed = AsyncMock(return_value=[vec])
        mock_indexer._store.search.return_value = [(_make_chunk(), 0.9)]
        handler = handlers["get_similar_patterns"]

        # Act
        await handler({"code_snippet": "def bar(): pass", "top_k": 4})

        # Assert
        mock_indexer._store.search.assert_called_once_with(vec, 4)

    @pytest.mark.asyncio
    async def test_empty_snippet_returns_error(
        self,
        handlers: dict,
    ) -> None:
        """빈 code_snippet일 때 에러 메시지를 반환하는지 검증."""
        # Arrange
        handler = handlers["get_similar_patterns"]

        # Act
        result = await handler({"code_snippet": ""})

        # Assert
        text = result["content"][0]["text"]
        assert "code_snippet" in text

    @pytest.mark.asyncio
    async def test_embedding_failure_returns_graceful_message(
        self,
        handlers: dict,
        mock_indexer: MagicMock,
    ) -> None:
        """임베딩이 빈 리스트일 때 graceful 메시지를 반환하는지 검증."""
        # Arrange
        mock_indexer._embedder.embed = AsyncMock(return_value=[])
        handler = handlers["get_similar_patterns"]

        # Act
        result = await handler({"code_snippet": "some code"})

        # Assert
        text = result["content"][0]["text"]
        assert "실패" in text or "API" in text or "KEY" in text

    @pytest.mark.asyncio
    async def test_no_similar_patterns_returns_empty_message(
        self,
        handlers: dict,
        mock_indexer: MagicMock,
    ) -> None:
        """벡터 검색 결과가 없을 때 빈 결과 메시지를 반환하는지 검증."""
        # Arrange
        mock_indexer._embedder.embed = AsyncMock(return_value=[[0.1, 0.2]])
        mock_indexer._store.search.return_value = []
        handler = handlers["get_similar_patterns"]

        # Act
        result = await handler({"code_snippet": "x = 1"})

        # Assert
        text = result["content"][0]["text"]
        assert "없습니다" in text

    @pytest.mark.asyncio
    async def test_returns_mcp_format(
        self,
        handlers: dict,
        mock_indexer: MagicMock,
    ) -> None:
        """반환값이 MCP 표준 응답 형식인지 검증."""
        # Arrange
        mock_indexer._embedder.embed = AsyncMock(return_value=[[0.1]])
        mock_indexer._store.search.return_value = [(_make_chunk(), 0.8)]
        handler = handlers["get_similar_patterns"]

        # Act
        result = await handler({"code_snippet": "def test(): pass"})

        # Assert
        assert "content" in result
        assert result["content"][0]["type"] == "text"

    @pytest.mark.asyncio
    async def test_embed_exception_returns_error_text(
        self,
        handlers: dict,
        mock_indexer: MagicMock,
    ) -> None:
        """embed() 예외 발생 시 에러 텍스트를 반환하는지 검증."""
        # Arrange
        mock_indexer._embedder.embed = AsyncMock(side_effect=RuntimeError("embed failed"))
        handler = handlers["get_similar_patterns"]

        # Act
        result = await handler({"code_snippet": "x = 1"})

        # Assert
        text = result["content"][0]["text"]
        assert "오류" in text

    @pytest.mark.asyncio
    async def test_default_top_k(
        self,
        handlers: dict,
        mock_indexer: MagicMock,
    ) -> None:
        """top_k 기본값 5가 store.search에 전달되는지 검증."""
        # Arrange
        mock_indexer._embedder.embed = AsyncMock(return_value=[[0.1]])
        mock_indexer._store.search.return_value = [(_make_chunk(), 0.9)]
        handler = handlers["get_similar_patterns"]

        # Act
        await handler({"code_snippet": "def foo(): pass"})

        # Assert: top_k 기본 5
        call_args = mock_indexer._store.search.call_args[0]
        assert call_args[1] == 5


# ---------------------------------------------------------------------------
# 6. 헬퍼 함수 테스트
# ---------------------------------------------------------------------------


class TestFormatResults:
    """_format_results() 헬퍼 함수 테스트."""

    def test_format_results_returns_mcp_format(self) -> None:
        """_format_results가 MCP 표준 형식을 반환하는지 검증."""
        chunks = [_make_chunk()]
        result = _format_results(chunks)

        assert "content" in result
        assert result["content"][0]["type"] == "text"

    def test_format_results_header_in_text(self) -> None:
        """header 문자열이 텍스트에 포함되는지 검증."""
        chunks = [_make_chunk()]
        result = _format_results(chunks, header="테스트 헤더")

        text = result["content"][0]["text"]
        assert "테스트 헤더" in text

    def test_format_results_chunk_count_in_text(self) -> None:
        """청크 수가 텍스트에 포함되는지 검증."""
        chunks = [_make_chunk("a.py"), _make_chunk("b.py")]
        result = _format_results(chunks, header="검색 결과")

        text = result["content"][0]["text"]
        assert "2" in text

    def test_format_results_file_path_and_line_in_text(self) -> None:
        """file_path:start_line이 텍스트에 포함되는지 검증."""
        chunk = _make_chunk("src/main.py", 42)
        result = _format_results([chunk])

        text = result["content"][0]["text"]
        assert "src/main.py" in text
        assert "42" in text

    def test_format_results_anonymous_chunk_name(self) -> None:
        """name=None 청크에서 (anonymous)가 표시되는지 검증."""
        chunk = _make_chunk(name=None)
        result = _format_results([chunk])

        text = result["content"][0]["text"]
        assert "(anonymous)" in text

    def test_format_results_content_included(self) -> None:
        """청크의 content가 텍스트에 포함되는지 검증."""
        chunk = _make_chunk(content="def unique_function(): return 42")
        result = _format_results([chunk])

        text = result["content"][0]["text"]
        assert "def unique_function(): return 42" in text

    def test_format_results_chunk_type_included(self) -> None:
        """청크의 chunk_type이 텍스트에 포함되는지 검증."""
        chunk = _make_chunk(chunk_type="class")
        result = _format_results([chunk])

        text = result["content"][0]["text"]
        assert "class" in text


class TestTextResponse:
    """_text_response() 헬퍼 함수 테스트."""

    def test_text_response_structure(self) -> None:
        """_text_response가 올바른 MCP 구조를 반환하는지 검증."""
        result = _text_response("hello")

        assert result == {"content": [{"type": "text", "text": "hello"}]}

    def test_text_response_preserves_text(self) -> None:
        """입력 텍스트가 그대로 보존되는지 검증."""
        msg = "에러 메시지\n여러 줄 포함"
        result = _text_response(msg)

        assert result["content"][0]["text"] == msg

    def test_text_response_empty_string(self) -> None:
        """빈 문자열도 처리하는지 검증."""
        result = _text_response("")

        assert result["content"][0]["text"] == ""

    def test_text_response_content_is_list(self) -> None:
        """content가 리스트인지 검증."""
        result = _text_response("x")

        assert isinstance(result["content"], list)
        assert len(result["content"]) == 1


class TestMatch:
    """_match() 헬퍼 함수 테스트."""

    def test_exact_mode_same_string(self) -> None:
        """exact 모드에서 동일 문자열이 매칭되는지 검증."""
        assert _match("get_user", "get_user", "exact") is True

    def test_exact_mode_different_string(self) -> None:
        """exact 모드에서 다른 문자열이 매칭되지 않는지 검증."""
        assert _match("get_user_info", "get_user", "exact") is False

    def test_prefix_mode_matches(self) -> None:
        """prefix 모드에서 접두사 매칭이 동작하는지 검증."""
        assert _match("get_user_info", "get_", "prefix") is True

    def test_prefix_mode_no_match(self) -> None:
        """prefix 모드에서 접두사 불일치는 False인지 검증."""
        assert _match("create_user", "get_", "prefix") is False

    def test_contains_mode_substring_match(self) -> None:
        """contains 모드에서 부분 문자열 매칭이 동작하는지 검증."""
        assert _match("validate_user_input", "user", "contains") is True

    def test_contains_mode_no_match(self) -> None:
        """contains 모드에서 포함되지 않는 문자열은 False인지 검증."""
        assert _match("create_post", "user", "contains") is False

    def test_exact_case_sensitive(self) -> None:
        """exact 모드가 대소문자를 구분하는지 검증."""
        assert _match("GetUser", "getuser", "exact") is False

    def test_contains_case_sensitive(self) -> None:
        """contains 모드가 대소문자를 구분하는지 검증."""
        assert _match("UserService", "user", "contains") is False

    def test_prefix_exact_string_also_matches(self) -> None:
        """prefix 모드에서 완전히 동일한 문자열도 매칭되는지 검증 (startswith)."""
        assert _match("foo", "foo", "prefix") is True


class TestBuildTree:
    """_build_tree() 헬퍼 함수 테스트."""

    def test_build_tree_root_in_output(self, tmp_path: Path) -> None:
        """루트 디렉토리 이름이 트리에 포함되는지 검증."""
        result = _build_tree(tmp_path, 3, IGNORED_DIRS)
        assert tmp_path.name in result

    def test_build_tree_depth_limits(self, tmp_path: Path) -> None:
        """depth 제한이 트리 깊이를 제한하는지 검증."""
        # Arrange — 3단계 중첩
        (tmp_path / "a" / "b" / "c").mkdir(parents=True)
        (tmp_path / "a" / "b" / "c" / "file.py").write_text("x\n", encoding="utf-8")

        # Act: depth=2 → root(0), a(1), b(2) 까지
        result = _build_tree(tmp_path, 2, IGNORED_DIRS)

        assert "a" in result
        assert "b" in result
        assert "c" not in result

    def test_build_tree_ignored_dirs_excluded(self, tmp_path: Path) -> None:
        """IGNORED_DIRS의 디렉토리가 트리에서 제외되는지 검증."""
        # Arrange
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "src").mkdir()

        result = _build_tree(tmp_path, 3, IGNORED_DIRS)

        assert "__pycache__" not in result
        assert "node_modules" not in result
        assert "src" in result

    def test_build_tree_empty_dir(self, tmp_path: Path) -> None:
        """빈 디렉토리에서도 루트 이름만 반환하는지 검증."""
        result = _build_tree(tmp_path, 3, IGNORED_DIRS)
        assert tmp_path.name in result

    def test_build_tree_indentation_increases_with_depth(self, tmp_path: Path) -> None:
        """계층이 깊어질수록 들여쓰기가 늘어나는지 검증."""
        # Arrange
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file.py").write_text("x\n", encoding="utf-8")

        result = _build_tree(tmp_path, 3, IGNORED_DIRS)
        lines = result.splitlines()

        # 루트(0 들여쓰기), subdir(2 들여쓰기), file.py(4 들여쓰기)
        root_line = next(l for l in lines if tmp_path.name in l)
        subdir_line = next(l for l in lines if "subdir" in l)
        file_line = next(l for l in lines if "file.py" in l)

        assert len(root_line) - len(root_line.lstrip()) == 0
        assert len(subdir_line) - len(subdir_line.lstrip()) == 2
        assert len(file_line) - len(file_line.lstrip()) == 4

    def test_build_tree_depth_zero_shows_only_root(self, tmp_path: Path) -> None:
        """depth=0이면 루트만 표시되는지 검증 (is_dir 조건: depth < max_depth)."""
        # Arrange
        (tmp_path / "src").mkdir()

        # Act: max_depth=0 → root(0)만 출력, 자식 없음
        result = _build_tree(tmp_path, 0, IGNORED_DIRS)
        lines = [l for l in result.splitlines() if l.strip()]

        assert len(lines) == 1
        assert tmp_path.name in lines[0]


# ---------------------------------------------------------------------------
# 7. MCP 응답 형식 공통 검증
# ---------------------------------------------------------------------------


class TestMcpResponseFormat:
    """모든 도구가 MCP 표준 응답 형식을 반환하는지 통합 검증."""

    def _assert_mcp_format(self, result: dict) -> None:
        """MCP 응답 형식 공통 검증."""
        assert "content" in result, "content 키 없음"
        assert isinstance(result["content"], list), "content가 리스트가 아님"
        assert len(result["content"]) >= 1, "content가 비어 있음"
        item = result["content"][0]
        assert item.get("type") == "text", f"type이 'text'가 아님: {item.get('type')}"
        assert isinstance(item.get("text"), str), "text가 문자열이 아님"

    @pytest.mark.asyncio
    async def test_all_tools_return_valid_mcp_format(
        self,
        handlers: dict,
        mock_indexer: MagicMock,
        tmp_path: Path,
    ) -> None:
        """5개 도구 모두 MCP 표준 형식을 반환하는지 통합 검증."""
        # search_code
        mock_indexer.search.return_value = []
        result = await handlers["search_code"]({"query": "foo"})
        self._assert_mcp_format(result)

        # reindex_codebase
        mock_indexer.update.return_value = {"added": 0, "updated": 0, "removed": 0}
        result = await handlers["reindex_codebase"]({})
        self._assert_mcp_format(result)

        # search_by_symbol
        mock_indexer.all_chunks = []
        result = await handlers["search_by_symbol"]({"name": "foo"})
        self._assert_mcp_format(result)

        # get_file_structure
        result = await handlers["get_file_structure"]({"path": str(tmp_path)})
        self._assert_mcp_format(result)

        # get_similar_patterns
        mock_indexer._embedder.embed = AsyncMock(return_value=[])
        result = await handlers["get_similar_patterns"]({"code_snippet": "x"})
        self._assert_mcp_format(result)


# ---------------------------------------------------------------------------
# 8. build_rag_mcp_server 통합 테스트
# ---------------------------------------------------------------------------


class TestBuildRagMcpServer:
    """build_rag_mcp_server() 함수 통합 테스트."""

    def test_build_calls_indexer_index(
        self,
        mock_indexer: MagicMock,
        tmp_path: Path,
    ) -> None:
        """build_rag_mcp_server()가 indexer.index()를 1회 호출하는지 검증."""
        with (
            patch("src.rag.mcp_server.get_indexer", return_value=mock_indexer),
            patch("src.rag.mcp_server.create_sdk_mcp_server", return_value=MagicMock()),
        ):
            build_rag_mcp_server(str(tmp_path))

        mock_indexer.index.assert_called_once()

    def test_build_returns_mcp_server_config(
        self,
        mock_indexer: MagicMock,
        tmp_path: Path,
    ) -> None:
        """build_rag_mcp_server()가 McpSdkServerConfig 형식의 딕셔너리를 반환하는지 검증.

        McpSdkServerConfig는 TypedDict이므로 isinstance 검사 대신
        필수 키(type, name, instance)의 존재를 확인한다.
        """
        with patch("src.rag.mcp_server.get_indexer", return_value=mock_indexer):
            result = build_rag_mcp_server(str(tmp_path))

        # TypedDict 키 존재 확인
        assert "type" in result
        assert "name" in result
        assert "instance" in result
        assert result["type"] == "sdk"
        assert result["name"] == "rag"

    def test_build_registers_five_tools(
        self,
        mock_indexer: MagicMock,
        tmp_path: Path,
    ) -> None:
        """5개 도구가 등록되는지 검증."""
        captured: list = []

        def capture_tools(name, version="1.0.0", tools=None):
            if tools:
                captured.extend(tools)
            return MagicMock()

        with (
            patch("src.rag.mcp_server.get_indexer", return_value=mock_indexer),
            patch("src.rag.mcp_server.create_sdk_mcp_server", side_effect=capture_tools),
        ):
            build_rag_mcp_server(str(tmp_path))

        tool_names = {t.name for t in captured}
        assert "search_code" in tool_names
        assert "reindex_codebase" in tool_names
        assert "search_by_symbol" in tool_names
        assert "get_file_structure" in tool_names
        assert "get_similar_patterns" in tool_names
