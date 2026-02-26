"""RAG MCP 서버.

claude_agent_sdk의 create_sdk_mcp_server를 사용하여 인-프로세스 MCP 서버를 제공한다.
AgentExecutor가 이 서버를 mcp_servers에 추가하면, 에이전트가 아래 5종 도구를 사용할 수 있다.

도구 목록:
  - search_code          : BM25+벡터 하이브리드 검색 (기존 개선)
  - reindex_codebase     : IncrementalIndexer.update() 호출 (기존 개선)
  - search_by_symbol     : CodeChunk.name 기반 심볼 검색 (신규)
  - get_file_structure   : 프로젝트 디렉토리 트리 반환 (신규)
  - get_similar_patterns : 임베딩 기반 유사 코드 검색 (신규)

사용 예:
    rag_server = build_rag_mcp_server(project_path)
    options = ClaudeAgentOptions(
        mcp_servers={"rag": rag_server},
        ...
    )
"""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig

from src.rag.incremental_indexer import IGNORED_DIRS, get_indexer
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


def build_rag_mcp_server(project_path: str) -> McpSdkServerConfig:
    """프로젝트 경로를 기반으로 RAG MCP 서버를 생성한다.

    IncrementalIndexer 싱글톤을 공유하여 모든 도구가 동일 인덱스를 사용한다.
    최초 호출 시 전체 인덱싱을 수행한다.

    Args:
        project_path: 인덱싱할 프로젝트 루트 경로

    Returns:
        ClaudeAgentOptions.mcp_servers에 전달할 McpSdkServerConfig
    """
    indexer = get_indexer(project_path)
    indexer.index()

    # ----------------------------------------------------------------
    # 1. search_code — 하이브리드 검색 (기존 개선)
    # ----------------------------------------------------------------

    @tool(
        name="search_code",
        description=(
            "Search for existing code patterns, implementations, or examples "
            "in the codebase using BM25 + vector hybrid search. "
            "Use this before writing new code to find similar patterns and maintain consistency."
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
        """BM25+벡터 하이브리드 검색으로 관련 코드 청크를 반환한다."""
        query = str(args.get("query", "")).strip()
        top_k = int(args.get("top_k", 5))

        if not query:
            return _text_response("query 파라미터가 필요합니다.")

        try:
            chunks = await indexer.search(query, top_k=top_k)
        except Exception:
            return _text_response(
                f"검색 중 오류 발생:\n{traceback.format_exc()}"
            )

        if not chunks:
            return _text_response(f"'{query}'에 대한 검색 결과가 없습니다.")

        return _format_results(chunks, header=f"검색 결과: '{query}'")

    # ----------------------------------------------------------------
    # 2. reindex_codebase — 증분 인덱싱 (기존 개선)
    # ----------------------------------------------------------------

    @tool(
        name="reindex_codebase",
        description=(
            "Incrementally re-index the codebase after code changes. "
            "Only changed files are re-indexed for efficiency. "
            "Call this when search results seem outdated."
        ),
        input_schema={},
    )
    async def reindex_codebase(_args: dict[str, Any]) -> dict[str, Any]:
        """변경된 파일만 증분 재인덱싱한다."""
        try:
            counts = indexer.update()
        except Exception:
            return _text_response(
                f"재인덱싱 중 오류 발생:\n{traceback.format_exc()}"
            )

        text = (
            f"증분 재인덱싱 완료\n"
            f"  추가: {counts['added']}개 파일\n"
            f"  수정: {counts['updated']}개 파일\n"
            f"  삭제: {counts['removed']}개 파일"
        )
        return _text_response(text)

    # ----------------------------------------------------------------
    # 3. search_by_symbol — 심볼 검색 (신규)
    # ----------------------------------------------------------------

    @tool(
        name="search_by_symbol",
        description=(
            "Search for code symbols (functions, classes, methods) by name. "
            "Supports exact, prefix, and contains matching modes."
        ),
        input_schema={
            "name": {
                "type": "string",
                "description": "Symbol name to search for (e.g., 'get_user', 'UserService')",
            },
            "mode": {
                "type": "string",
                "description": "Match mode: 'exact', 'prefix', or 'contains' (default: 'contains')",
                "default": "contains",
            },
        },
    )
    async def search_by_symbol(args: dict[str, Any]) -> dict[str, Any]:
        """CodeChunk.name 기반으로 심볼을 검색한다."""
        name = str(args.get("name", "")).strip()
        mode = str(args.get("mode", "contains"))

        if not name:
            return _text_response("name 파라미터가 필요합니다.")

        if mode not in ("exact", "prefix", "contains"):
            return _text_response(
                f"잘못된 mode '{mode}'. 'exact', 'prefix', 'contains' 중 하나여야 합니다."
            )

        matches = [
            c for c in indexer.all_chunks
            if c.name and _match(c.name, name, mode)
        ]

        if not matches:
            return _text_response(
                f"심볼 '{name}' (mode={mode})에 대한 검색 결과가 없습니다."
            )

        return _format_results(matches, header=f"심볼 검색: '{name}' (mode={mode})")

    # ----------------------------------------------------------------
    # 4. get_file_structure — 디렉토리 트리 (신규)
    # ----------------------------------------------------------------

    @tool(
        name="get_file_structure",
        description=(
            "Get the directory tree structure of the project or a subdirectory. "
            "Useful for understanding project layout before making changes."
        ),
        input_schema={
            "path": {
                "type": "string",
                "description": "Directory path to show (default: project root)",
                "default": "",
            },
            "depth": {
                "type": "integer",
                "description": "Maximum depth to traverse (default: 3)",
                "default": 3,
            },
        },
    )
    async def get_file_structure(args: dict[str, Any]) -> dict[str, Any]:
        """프로젝트 디렉토리 트리를 텍스트로 반환한다."""
        raw_path = str(args.get("path", "")).strip()
        depth = int(args.get("depth", 3))

        root = Path(raw_path) if raw_path else Path(project_path)

        if not root.exists():
            return _text_response(f"경로를 찾을 수 없습니다: {root}")

        if not root.is_dir():
            return _text_response(f"디렉토리가 아닙니다: {root}")

        try:
            tree = _build_tree(root, depth, IGNORED_DIRS)
        except Exception:
            return _text_response(
                f"디렉토리 트리 생성 중 오류 발생:\n{traceback.format_exc()}"
            )

        return _text_response(tree)

    # ----------------------------------------------------------------
    # 5. get_similar_patterns — 유사 코드 검색 (신규)
    # ----------------------------------------------------------------

    @tool(
        name="get_similar_patterns",
        description=(
            "Find code chunks semantically similar to a given code snippet "
            "using embedding-based vector search. "
            "Useful for finding similar implementations or patterns."
        ),
        input_schema={
            "code_snippet": {
                "type": "string",
                "description": "Code snippet to find similar patterns for",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of similar patterns to return (default: 5)",
                "default": 5,
            },
        },
    )
    async def get_similar_patterns(args: dict[str, Any]) -> dict[str, Any]:
        """임베딩 기반으로 유사한 코드 패턴을 검색한다."""
        snippet = str(args.get("code_snippet", "")).strip()
        top_k = int(args.get("top_k", 5))

        if not snippet:
            return _text_response("code_snippet 파라미터가 필요합니다.")

        try:
            embedding = await indexer._embedder.embed([snippet])
        except Exception:
            return _text_response(
                f"임베딩 생성 중 오류 발생:\n{traceback.format_exc()}"
            )

        if not embedding:
            return _text_response(
                "임베딩 생성에 실패했습니다. "
                "VOYAGE_API_KEY 또는 ANTHROPIC_API_KEY 환경변수를 확인하세요."
            )

        results = indexer._store.search(embedding[0], top_k)
        chunks = [c for c, _ in results]

        if not chunks:
            return _text_response("유사한 코드 패턴을 찾을 수 없습니다.")

        return _format_results(chunks, header="유사 코드 패턴")

    return create_sdk_mcp_server(
        name="rag",
        version="2.0.0",
        tools=[
            search_code,
            reindex_codebase,
            search_by_symbol,
            get_file_structure,
            get_similar_patterns,
        ],
    )


# ------------------------------------------------------------------
# 모듈 레벨 헬퍼
# ------------------------------------------------------------------


def _format_results(
    chunks: list[Any],
    header: str = "결과",
) -> dict[str, Any]:
    """청크 리스트를 MCP 응답 형식으로 변환한다.

    Args:
        chunks: 출력할 CodeChunk 목록
        header: 결과 헤더 문자열

    Returns:
        MCP 표준 응답 딕셔너리
    """
    lines = [f"=== {header} ({len(chunks)}개) ===\n"]
    for i, c in enumerate(chunks, 1):
        lines.append(f"--- {i}. {c.file_path}:{c.start_line} ---")
        lines.append(f"Name: {c.name or '(anonymous)'}")
        lines.append(f"Type: {c.chunk_type}")
        lines.append(f"Content:\n{c.content}\n")
    return _text_response("\n".join(lines))


def _text_response(text: str) -> dict[str, Any]:
    """텍스트를 MCP 표준 응답 형식으로 래핑한다.

    Args:
        text: 응답 텍스트

    Returns:
        {"content": [{"type": "text", "text": text}]} 형식 딕셔너리
    """
    return {"content": [{"type": "text", "text": text}]}


def _match(chunk_name: str, query: str, mode: str) -> bool:
    """청크 이름이 쿼리와 매칭되는지 확인한다.

    Args:
        chunk_name: 청크의 함수/클래스 이름
        query: 검색할 이름
        mode: "exact" | "prefix" | "contains"

    Returns:
        매칭 여부
    """
    if mode == "exact":
        return chunk_name == query
    if mode == "prefix":
        return chunk_name.startswith(query)
    # contains (기본값)
    return query in chunk_name


def _build_tree(root: Path, max_depth: int, ignored: frozenset[str]) -> str:
    """디렉토리 트리를 텍스트로 생성한다.

    들여쓰기(2칸)로 계층을 표현하며, ignored 집합의 디렉토리는 건너뛴다.

    Args:
        root: 트리 루트 경로
        max_depth: 최대 탐색 깊이 (1-indexed, root는 깊이 0)
        ignored: 제외할 디렉토리 이름 집합

    Returns:
        들여쓰기로 계층을 표현한 트리 문자열
    """
    lines: list[str] = []

    def walk(path: Path, prefix: str, depth: int) -> None:
        if path.name in ignored:
            return
        lines.append(f"{prefix}{path.name}")
        if path.is_dir() and depth < max_depth:
            for child in sorted(path.iterdir()):
                walk(child, prefix + "  ", depth + 1)

    walk(root, "", 0)
    return "\n".join(lines)
