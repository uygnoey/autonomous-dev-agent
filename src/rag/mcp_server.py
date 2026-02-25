"""RAG MCP 서버.

claude_agent_sdk의 create_sdk_mcp_server를 사용하여 인-프로세스 MCP 서버를 제공한다.
AgentExecutor가 이 서버를 mcp_servers에 추가하면, 에이전트가 search_code 도구를 사용할 수 있다.

사용 예:
    rag_server = build_rag_mcp_server(project_path)
    options = ClaudeAgentOptions(
        mcp_servers={"rag": rag_server},
        ...
    )
"""

from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig

from src.rag.indexer import CodebaseIndexer
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


def _text_response(text: str) -> dict[str, Any]:
    """MCP 도구의 텍스트 응답 형식으로 감싼다."""
    return {"content": [{"type": "text", "text": text}]}


def build_rag_mcp_server(project_path: str) -> McpSdkServerConfig:
    """프로젝트 경로를 기반으로 RAG MCP 서버를 생성한다.

    Args:
        project_path: 인덱싱할 프로젝트 루트 경로

    Returns:
        ClaudeAgentOptions.mcp_servers에 전달할 McpSdkServerConfig
    """
    indexer = CodebaseIndexer(project_path)
    indexer.index()

    @tool(
        name="search_code",
        description=(
            "Search for existing code patterns, implementations, or examples "
            "in the codebase. Use this before writing new code to find similar "
            "patterns and maintain consistency."
        ),
        input_schema={
            "query": {
                "type": "string",
                "description": (
                    "What to search for (e.g., 'error handling pattern', "
                    "'API endpoint', 'test fixture')"
                ),
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results to return (default: 5)",
                "default": 5,
            },
        },
    )
    async def search_code(args: dict[str, Any]) -> dict[str, Any]:
        """기존 코드베이스에서 유사 패턴을 검색한다."""
        query = str(args.get("query", ""))
        top_k = int(args.get("top_k", 5))

        if not query:
            return _text_response("query 파라미터가 필요합니다.")

        chunks = indexer.search(query, top_k=top_k)

        if not chunks:
            return _text_response(f"'{query}'에 대한 검색 결과가 없습니다.")

        lines = [f"=== 검색 결과: '{query}' ===\n"]
        for i, chunk in enumerate(chunks, 1):
            header = (
                f"\n--- 결과 {i}: {chunk.file_path} "
                f"(L{chunk.start_line}-{chunk.end_line}) ---"
            )
            lines.append(header)
            lines.append(chunk.content)

        return _text_response("\n".join(lines))

    @tool(
        name="reindex_codebase",
        description=(
            "Re-index the codebase after significant code changes. "
            "Call this when the search results seem outdated."
        ),
        input_schema={},
    )
    async def reindex_codebase(_args: dict[str, Any]) -> dict[str, Any]:
        """코드베이스를 재인덱싱한다."""
        count = indexer.index()
        return _text_response(f"재인덱싱 완료: {count}개 청크")

    return create_sdk_mcp_server(
        name="rag",
        version="1.0.0",
        tools=[search_code, reindex_codebase],
    )
