"""RAG MCP 서버 테스트."""

import asyncio
from unittest.mock import MagicMock, patch

from src.rag.indexer import CodeChunk
from src.rag.mcp_server import _text_response, build_rag_mcp_server


def capture_tools_decorator():
    """@tool 데코레이터를 캡처하는 팩토리."""
    captured: dict = {}

    def fake_tool(**kwargs):
        def decorator(fn):
            captured[kwargs["name"]] = fn
            return fn
        return decorator

    return fake_tool, captured


class TestTextResponse:
    def test_returns_mcp_content_format(self):
        result = _text_response("hello world")
        assert result == {"content": [{"type": "text", "text": "hello world"}]}

    def test_wraps_empty_string(self):
        result = _text_response("")
        assert result["content"][0]["text"] == ""


class TestBuildRagMcpServer:
    def test_indexes_codebase_on_creation(self):
        fake_tool, _ = capture_tools_decorator()
        with (
            patch("src.rag.mcp_server.CodebaseIndexer") as mock_cls,
            patch("src.rag.mcp_server.create_sdk_mcp_server"),
            patch("src.rag.mcp_server.tool", new=fake_tool),
        ):
            mock_indexer = MagicMock()
            mock_cls.return_value = mock_indexer
            mock_indexer.index.return_value = 10
            build_rag_mcp_server("/tmp/project")

        mock_cls.assert_called_once_with("/tmp/project")
        mock_indexer.index.assert_called_once()

    def test_returns_mcp_server_config(self):
        fake_tool, _ = capture_tools_decorator()
        mock_config = MagicMock()
        with (
            patch("src.rag.mcp_server.CodebaseIndexer") as mock_cls,
            patch("src.rag.mcp_server.create_sdk_mcp_server", return_value=mock_config),
            patch("src.rag.mcp_server.tool", new=fake_tool),
        ):
            mock_cls.return_value = MagicMock(index=MagicMock(return_value=0))
            result = build_rag_mcp_server("/tmp/project")

        assert result is mock_config

    def test_registers_two_tools(self):
        fake_tool, captured = capture_tools_decorator()
        with (
            patch("src.rag.mcp_server.CodebaseIndexer") as mock_cls,
            patch("src.rag.mcp_server.create_sdk_mcp_server"),
            patch("src.rag.mcp_server.tool", new=fake_tool),
        ):
            mock_cls.return_value = MagicMock(index=MagicMock(return_value=0))
            build_rag_mcp_server("/tmp/project")

        assert "search_code" in captured
        assert "reindex_codebase" in captured

    def test_search_code_returns_chunk_results(self):
        fake_tool, captured = capture_tools_decorator()
        chunks = [
            CodeChunk(
                file_path="src/main.py",
                content="def main(): pass",
                start_line=1,
                end_line=1,
            ),
        ]
        with (
            patch("src.rag.mcp_server.CodebaseIndexer") as mock_cls,
            patch("src.rag.mcp_server.create_sdk_mcp_server"),
            patch("src.rag.mcp_server.tool", new=fake_tool),
        ):
            mock_indexer = MagicMock()
            mock_cls.return_value = mock_indexer
            mock_indexer.index.return_value = 1
            mock_indexer.search.return_value = chunks
            build_rag_mcp_server("/tmp/project")

        search_code = captured["search_code"]
        result = asyncio.run(search_code({"query": "main function", "top_k": 5}))

        assert result["content"][0]["type"] == "text"
        text = result["content"][0]["text"]
        assert "src/main.py" in text
        assert "def main(): pass" in text
        mock_indexer.search.assert_called_once_with("main function", top_k=5)

    def test_search_code_empty_query_returns_error(self):
        fake_tool, captured = capture_tools_decorator()
        with (
            patch("src.rag.mcp_server.CodebaseIndexer") as mock_cls,
            patch("src.rag.mcp_server.create_sdk_mcp_server"),
            patch("src.rag.mcp_server.tool", new=fake_tool),
        ):
            mock_cls.return_value = MagicMock(index=MagicMock(return_value=0))
            build_rag_mcp_server("/tmp/project")

        search_code = captured["search_code"]
        result = asyncio.run(search_code({"query": ""}))

        assert "query" in result["content"][0]["text"].lower()

    def test_search_code_no_results(self):
        fake_tool, captured = capture_tools_decorator()
        with (
            patch("src.rag.mcp_server.CodebaseIndexer") as mock_cls,
            patch("src.rag.mcp_server.create_sdk_mcp_server"),
            patch("src.rag.mcp_server.tool", new=fake_tool),
        ):
            mock_indexer = MagicMock()
            mock_cls.return_value = mock_indexer
            mock_indexer.index.return_value = 0
            mock_indexer.search.return_value = []
            build_rag_mcp_server("/tmp/project")

        search_code = captured["search_code"]
        result = asyncio.run(search_code({"query": "nonexistent"}))

        assert "없습니다" in result["content"][0]["text"]

    def test_reindex_codebase_returns_count(self):
        fake_tool, captured = capture_tools_decorator()
        with (
            patch("src.rag.mcp_server.CodebaseIndexer") as mock_cls,
            patch("src.rag.mcp_server.create_sdk_mcp_server"),
            patch("src.rag.mcp_server.tool", new=fake_tool),
        ):
            mock_indexer = MagicMock()
            mock_cls.return_value = mock_indexer
            mock_indexer.index.return_value = 42
            build_rag_mcp_server("/tmp/project")

        # reindex 시 index() 재호출
        mock_indexer.index.return_value = 50
        reindex = captured["reindex_codebase"]
        result = asyncio.run(reindex({}))

        assert "50" in result["content"][0]["text"]
        assert "완료" in result["content"][0]["text"]
