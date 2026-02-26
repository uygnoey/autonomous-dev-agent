"""MCP 서버 모듈 QC 케이스 생성기.

10,000건의 JSONL 테스트 케이스를 생성한다.

mcp_server.py의 5개 tool 함수와 모듈 레벨 헬퍼를 직접 검증한다.
(claude_agent_sdk 의존 없이 tool 로직을 인라인으로 재현하여 테스트)

케이스 포맷:
- id: TC-MCP-XXXXX
- category: normal / boundary / invalid / stress / random
- tool: "search_code" | "reindex_codebase" | "search_by_symbol"
        | "get_file_structure" | "get_similar_patterns"
        | "_text_response" | "_format_results" | "_match" | "_build_tree"
- args: 도구 인자 딕셔너리
- context: mock 컨텍스트 (chunks, update_counts, embed_result 등)
- expected:
    type: "mcp_response" | "text_contains" | "bool_result" | "no_exception"
    text_contains: 응답 text에 포함되어야 할 문자열 목록
    bool_value: _match 결과 기대값
    has_content: content 배열 존재 여부
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


# ------------------------------------------------------------------
# 데이터 생성 헬퍼
# ------------------------------------------------------------------

_FUNC_NAMES = [
    "get_user", "create_order", "process_payment", "validate_input",
    "load_config", "save_result", "search_index", "build_tree",
    "parse_token", "emit_event", "handle_error", "fetch_data",
    "update_cache", "clear_store", "run_pipeline", "check_health",
    "decode_jwt", "encode_message", "transform_output", "register_hook",
]

_CLASS_NAMES = [
    "UserService", "OrderManager", "PaymentProcessor", "ConfigLoader",
    "DataStore", "EventHandler", "TokenDecoder", "CacheLayer",
    "QueryEngine", "IndexBuilder", "PipelineRunner", "FileParser",
]

_QUERY_WORDS = [
    "error handling", "authentication", "database connection",
    "API endpoint", "test fixture", "configuration", "logging",
    "async function", "class definition", "import statement",
    "exception", "retry logic", "cache", "search", "index",
]

_SYMBOL_NAMES = _FUNC_NAMES + _CLASS_NAMES + ["__init__", "main", "run"]


def _rand_chunk_dict(with_name: bool = True) -> dict:
    name = random.choice(_FUNC_NAMES) if with_name else None
    sl = random.randint(1, 200)
    return {
        "file_path": f"src/{random.choice(['core', 'rag', 'utils'])}/{random.choice(['module', 'service', 'handler'])}_{random.randint(1,9)}.py",
        "content": f"def {name or 'anonymous'}():\n    # implementation\n    return None",
        "start_line": sl,
        "end_line": sl + random.randint(1, 20),
        "chunk_type": random.choice(["function", "class", "module"]),
        "name": name,
    }


def _rand_chunks(n: int, with_name_prob: float = 0.8) -> list[dict]:
    return [_rand_chunk_dict(random.random() < with_name_prob) for _ in range(n)]


# ------------------------------------------------------------------
# search_code 케이스
# ------------------------------------------------------------------

def _gen_search_code_normal(tc_id: str) -> dict:
    n = random.randint(1, 8)
    query = random.choice(_QUERY_WORDS)
    top_k = random.randint(1, 5)
    chunks = _rand_chunks(n)
    return {
        "id": tc_id, "category": "normal", "tool": "search_code",
        "args": {"query": query, "top_k": top_k},
        "context": {"search_chunks": chunks, "search_raises": False},
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": [f"검색 결과: '{query}'"],
        },
    }


def _gen_search_code_empty_result(tc_id: str) -> dict:
    query = random.choice(_QUERY_WORDS)
    return {
        "id": tc_id, "category": "boundary", "tool": "search_code",
        "args": {"query": query, "top_k": random.randint(1, 5)},
        "context": {"search_chunks": [], "search_raises": False},
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": [f"'{query}'에 대한 검색 결과가 없습니다"],
        },
    }


def _gen_search_code_empty_query(tc_id: str) -> dict:
    query = random.choice(["", "   ", "\t"])
    return {
        "id": tc_id, "category": "boundary", "tool": "search_code",
        "args": {"query": query, "top_k": 5},
        "context": {"search_chunks": [], "search_raises": False},
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": ["query 파라미터가 필요합니다"],
        },
    }


def _gen_search_code_raises(tc_id: str) -> dict:
    query = random.choice(_QUERY_WORDS)
    return {
        "id": tc_id, "category": "invalid", "tool": "search_code",
        "args": {"query": query, "top_k": 5},
        "context": {"search_chunks": [], "search_raises": True},
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": ["검색 중 오류 발생"],
        },
    }


def _gen_search_code_large(tc_id: str) -> dict:
    n = random.randint(20, 50)
    query = random.choice(_QUERY_WORDS)
    top_k = random.randint(10, 20)
    chunks = _rand_chunks(n)
    return {
        "id": tc_id, "category": "stress", "tool": "search_code",
        "args": {"query": query, "top_k": top_k},
        "context": {"search_chunks": chunks[:top_k], "search_raises": False},
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": [f"검색 결과: '{query}'"],
        },
    }


# ------------------------------------------------------------------
# reindex_codebase 케이스
# ------------------------------------------------------------------

def _gen_reindex_normal(tc_id: str) -> dict:
    added = random.randint(0, 5)
    updated = random.randint(0, 3)
    removed = random.randint(0, 2)
    return {
        "id": tc_id, "category": "normal", "tool": "reindex_codebase",
        "args": {},
        "context": {
            "update_counts": {"added": added, "updated": updated, "removed": removed},
            "update_raises": False,
        },
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": ["증분 재인덱싱 완료", f"추가: {added}개 파일", f"수정: {updated}개 파일", f"삭제: {removed}개 파일"],
        },
    }


def _gen_reindex_no_change(tc_id: str) -> dict:
    return {
        "id": tc_id, "category": "boundary", "tool": "reindex_codebase",
        "args": {},
        "context": {
            "update_counts": {"added": 0, "updated": 0, "removed": 0},
            "update_raises": False,
        },
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": ["증분 재인덱싱 완료", "추가: 0개 파일"],
        },
    }


def _gen_reindex_raises(tc_id: str) -> dict:
    return {
        "id": tc_id, "category": "invalid", "tool": "reindex_codebase",
        "args": {},
        "context": {"update_counts": {}, "update_raises": True},
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": ["재인덱싱 중 오류 발생"],
        },
    }


# ------------------------------------------------------------------
# search_by_symbol 케이스
# ------------------------------------------------------------------

def _gen_symbol_normal(tc_id: str) -> dict:
    mode = random.choice(["exact", "prefix", "contains"])
    target = random.choice(_FUNC_NAMES)
    # 모드에 맞는 쿼리 생성
    if mode == "exact":
        query = target
    elif mode == "prefix":
        query = target[:max(2, len(target) // 2)]
    else:
        query = target[1:max(3, len(target) - 2)]
    # 쿼리와 매칭되는 청크 포함
    chunks = [{"file_path": "src/core.py", "content": f"def {target}(): pass",
                "start_line": 1, "end_line": 5, "chunk_type": "function", "name": target}]
    chunks += _rand_chunks(random.randint(2, 5))
    return {
        "id": tc_id, "category": "normal", "tool": "search_by_symbol",
        "args": {"name": query, "mode": mode},
        "context": {"all_chunks": chunks},
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": [f"심볼 검색: '{query}' (mode={mode})"],
        },
    }


def _gen_symbol_no_result(tc_id: str) -> dict:
    mode = random.choice(["exact", "prefix", "contains"])
    query = "zzz_nonexistent_symbol_xyz"
    chunks = _rand_chunks(random.randint(3, 8))
    return {
        "id": tc_id, "category": "boundary", "tool": "search_by_symbol",
        "args": {"name": query, "mode": mode},
        "context": {"all_chunks": chunks},
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": [f"심볼 '{query}' (mode={mode})에 대한 검색 결과가 없습니다"],
        },
    }


def _gen_symbol_empty_name(tc_id: str) -> dict:
    return {
        "id": tc_id, "category": "boundary", "tool": "search_by_symbol",
        "args": {"name": "", "mode": "contains"},
        "context": {"all_chunks": _rand_chunks(3)},
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": ["name 파라미터가 필요합니다"],
        },
    }


def _gen_symbol_invalid_mode(tc_id: str) -> dict:
    invalid_modes = ["fuzzy", "regex", "glob", "EXACT", "PREFIX", ""]
    return {
        "id": tc_id, "category": "invalid", "tool": "search_by_symbol",
        "args": {"name": "get_user", "mode": random.choice(invalid_modes)},
        "context": {"all_chunks": _rand_chunks(3)},
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": ["잘못된 mode"],
        },
    }


def _gen_symbol_none_name_chunks(tc_id: str) -> dict:
    """name=None인 청크는 필터링됨."""
    chunks = _rand_chunks(5, with_name_prob=0.0)  # 모두 name=None
    return {
        "id": tc_id, "category": "boundary", "tool": "search_by_symbol",
        "args": {"name": "anything", "mode": "contains"},
        "context": {"all_chunks": chunks},
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": ["검색 결과가 없습니다"],
        },
    }


# ------------------------------------------------------------------
# get_file_structure 케이스
# ------------------------------------------------------------------

def _gen_file_structure_normal(tc_id: str) -> dict:
    depth = random.randint(1, 4)
    return {
        "id": tc_id, "category": "normal", "tool": "get_file_structure",
        "args": {"path": "", "depth": depth},
        "context": {"project_files": [
            "src/core.py", "src/rag/chunker.py", "src/rag/scorer.py",
            "tests/test_core.py", "README.md",
        ]},
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": [],  # 트리 내용은 동적
        },
    }


def _gen_file_structure_depth_zero(tc_id: str) -> dict:
    return {
        "id": tc_id, "category": "boundary", "tool": "get_file_structure",
        "args": {"path": "", "depth": 0},
        "context": {"project_files": ["src/core.py"]},
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": [],
        },
    }


def _gen_file_structure_not_exist(tc_id: str) -> dict:
    return {
        "id": tc_id, "category": "invalid", "tool": "get_file_structure",
        "args": {"path": "/nonexistent/path/xyz/abc", "depth": 3},
        "context": {"project_files": []},
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": ["경로를 찾을 수 없습니다"],
        },
    }


def _gen_file_structure_file_not_dir(tc_id: str) -> dict:
    """파일 경로를 path로 지정."""
    return {
        "id": tc_id, "category": "invalid", "tool": "get_file_structure",
        "args": {"path": "__FILE__", "depth": 3},  # QC 실행기가 실제 파일 경로로 교체
        "context": {"project_files": []},
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": ["디렉토리가 아닙니다"],
        },
    }


def _gen_file_structure_deep(tc_id: str) -> dict:
    depth = random.randint(5, 10)
    return {
        "id": tc_id, "category": "stress", "tool": "get_file_structure",
        "args": {"path": "", "depth": depth},
        "context": {"project_files": [
            f"src/a/b/c/d/e/f_{i}.py" for i in range(10)
        ]},
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": [],
        },
    }


# ------------------------------------------------------------------
# get_similar_patterns 케이스
# ------------------------------------------------------------------

def _gen_similar_normal(tc_id: str) -> dict:
    snippet = f"def {random.choice(_FUNC_NAMES)}():\n    return None"
    n = random.randint(1, 5)
    chunks = _rand_chunks(n)
    top_k = random.randint(1, 5)
    return {
        "id": tc_id, "category": "normal", "tool": "get_similar_patterns",
        "args": {"code_snippet": snippet, "top_k": top_k},
        "context": {
            "embed_result": [[0.1] * 128],
            "store_results": [(c, 0.9 - i * 0.1) for i, c in enumerate(chunks[:top_k])],
            "embed_raises": False,
        },
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": ["유사 코드 패턴"],
        },
    }


def _gen_similar_empty_snippet(tc_id: str) -> dict:
    return {
        "id": tc_id, "category": "boundary", "tool": "get_similar_patterns",
        "args": {"code_snippet": random.choice(["", "  ", "\n"]), "top_k": 5},
        "context": {"embed_result": [], "store_results": [], "embed_raises": False},
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": ["code_snippet 파라미터가 필요합니다"],
        },
    }


def _gen_similar_embed_fails(tc_id: str) -> dict:
    snippet = "def foo(): pass"
    return {
        "id": tc_id, "category": "invalid", "tool": "get_similar_patterns",
        "args": {"code_snippet": snippet, "top_k": 5},
        "context": {"embed_result": [], "store_results": [], "embed_raises": False},
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": ["임베딩 생성에 실패했습니다"],
        },
    }


def _gen_similar_embed_raises(tc_id: str) -> dict:
    snippet = "def foo(): pass"
    return {
        "id": tc_id, "category": "invalid", "tool": "get_similar_patterns",
        "args": {"code_snippet": snippet, "top_k": 5},
        "context": {"embed_result": None, "store_results": [], "embed_raises": True},
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": ["임베딩 생성 중 오류 발생"],
        },
    }


def _gen_similar_no_store_results(tc_id: str) -> dict:
    snippet = "def foo(): pass"
    return {
        "id": tc_id, "category": "boundary", "tool": "get_similar_patterns",
        "args": {"code_snippet": snippet, "top_k": 5},
        "context": {"embed_result": [[0.1] * 128], "store_results": [], "embed_raises": False},
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": ["유사한 코드 패턴을 찾을 수 없습니다"],
        },
    }


def _gen_similar_stress(tc_id: str) -> dict:
    snippet = "def " + random.choice(_FUNC_NAMES) + "():\n" + "\n".join(
        f"    step_{i} = True" for i in range(20)
    )
    n = random.randint(10, 30)
    chunks = _rand_chunks(n)
    top_k = random.randint(5, 15)
    return {
        "id": tc_id, "category": "stress", "tool": "get_similar_patterns",
        "args": {"code_snippet": snippet, "top_k": top_k},
        "context": {
            "embed_result": [[0.1] * 128],
            "store_results": [(c, 0.9) for c in chunks[:top_k]],
            "embed_raises": False,
        },
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": ["유사 코드 패턴"],
        },
    }


# ------------------------------------------------------------------
# 헬퍼 함수 직접 테스트
# ------------------------------------------------------------------

def _gen_match_exact(tc_id: str) -> dict:
    name = random.choice(_FUNC_NAMES)
    return {
        "id": tc_id, "category": "normal", "tool": "_match",
        "args": {"chunk_name": name, "query": name, "mode": "exact"},
        "context": {},
        "expected": {"type": "bool_result", "bool_value": True},
    }


def _gen_match_exact_fail(tc_id: str) -> dict:
    name = random.choice(_FUNC_NAMES)
    query = name + "_suffix"
    return {
        "id": tc_id, "category": "normal", "tool": "_match",
        "args": {"chunk_name": name, "query": query, "mode": "exact"},
        "context": {},
        "expected": {"type": "bool_result", "bool_value": False},
    }


def _gen_match_prefix(tc_id: str) -> dict:
    name = random.choice(_FUNC_NAMES)
    prefix = name[:max(2, len(name) // 2)]
    return {
        "id": tc_id, "category": "normal", "tool": "_match",
        "args": {"chunk_name": name, "query": prefix, "mode": "prefix"},
        "context": {},
        "expected": {"type": "bool_result", "bool_value": True},
    }


def _gen_match_contains(tc_id: str) -> dict:
    name = random.choice(_FUNC_NAMES)
    sub = name[1:max(3, len(name) - 1)]
    return {
        "id": tc_id, "category": "normal", "tool": "_match",
        "args": {"chunk_name": name, "query": sub, "mode": "contains"},
        "context": {},
        "expected": {"type": "bool_result", "bool_value": True},
    }


def _gen_text_response(tc_id: str) -> dict:
    text = random.choice(["결과 없음", "검색 완료", "오류 발생", ""])
    return {
        "id": tc_id, "category": "normal", "tool": "_text_response",
        "args": {"text": text},
        "context": {},
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": [text] if text else [],
        },
    }


def _gen_format_results(tc_id: str) -> dict:
    n = random.randint(1, 5)
    chunks = _rand_chunks(n)
    header = random.choice(["검색 결과", "심볼 검색", "유사 코드"])
    return {
        "id": tc_id, "category": "normal", "tool": "_format_results",
        "args": {"chunks": chunks, "header": header},
        "context": {},
        "expected": {
            "type": "mcp_response",
            "has_content": True,
            "text_contains": [f"=== {header} ({n}개) ==="],
        },
    }


def _gen_random(tc_id: str) -> dict:
    tools = [
        "search_code", "reindex_codebase", "search_by_symbol",
        "get_file_structure", "get_similar_patterns",
    ]
    tool = random.choice(tools)
    query = random.choice(_QUERY_WORDS + [""])
    top_k = random.randint(0, 10)
    mode = random.choice(["exact", "prefix", "contains", "invalid_mode"])
    chunks = _rand_chunks(random.randint(0, 10))
    n_sym = random.choice(_SYMBOL_NAMES + [""])
    snippet = random.choice(["def foo(): pass", "", "class Bar: pass"])
    depth = random.randint(-1, 6)

    if tool == "search_code":
        args = {"query": query, "top_k": top_k}
        ctx = {"search_chunks": chunks, "search_raises": False}
        if not query.strip():
            exp = {"type": "mcp_response", "has_content": True, "text_contains": ["query 파라미터가 필요합니다"]}
        elif not chunks:
            exp = {"type": "mcp_response", "has_content": True, "text_contains": []}
        else:
            exp = {"type": "mcp_response", "has_content": True, "text_contains": []}
    elif tool == "reindex_codebase":
        args = {}
        ctx = {"update_counts": {"added": 0, "updated": 0, "removed": 0}, "update_raises": False}
        exp = {"type": "mcp_response", "has_content": True, "text_contains": ["증분 재인덱싱 완료"]}
    elif tool == "search_by_symbol":
        args = {"name": n_sym, "mode": mode}
        ctx = {"all_chunks": chunks}
        if not n_sym.strip():
            exp = {"type": "mcp_response", "has_content": True, "text_contains": ["name 파라미터가 필요합니다"]}
        elif mode not in ("exact", "prefix", "contains"):
            exp = {"type": "mcp_response", "has_content": True, "text_contains": ["잘못된 mode"]}
        else:
            exp = {"type": "mcp_response", "has_content": True, "text_contains": []}
    elif tool == "get_file_structure":
        args = {"path": "", "depth": max(0, depth)}
        ctx = {"project_files": ["src/core.py"]}
        exp = {"type": "mcp_response", "has_content": True, "text_contains": []}
    else:  # get_similar_patterns
        args = {"code_snippet": snippet, "top_k": top_k}
        ctx = {"embed_result": [[0.1] * 128] if snippet.strip() else [], "store_results": [], "embed_raises": False}
        if not snippet.strip():
            exp = {"type": "mcp_response", "has_content": True, "text_contains": ["code_snippet 파라미터가 필요합니다"]}
        else:
            exp = {"type": "mcp_response", "has_content": True, "text_contains": []}

    return {
        "id": tc_id, "category": "random", "tool": tool,
        "args": args, "context": ctx, "expected": exp,
    }


# ------------------------------------------------------------------
# 생성 스케줄 (합계 10,000건)
# ------------------------------------------------------------------

_SCHEDULE = [
    # normal 3,000건
    (_gen_search_code_normal,         500),
    (_gen_reindex_normal,             400),
    (_gen_symbol_normal,              500),
    (_gen_file_structure_normal,      400),
    (_gen_similar_normal,             300),
    (_gen_match_exact,                150),
    (_gen_match_exact_fail,           150),
    (_gen_match_prefix,               200),
    (_gen_match_contains,             200),
    (_gen_text_response,              100),
    (_gen_format_results,             100),
    # boundary 2,000건
    (_gen_search_code_empty_result,   250),
    (_gen_search_code_empty_query,    250),
    (_gen_reindex_no_change,          200),
    (_gen_symbol_no_result,           200),
    (_gen_symbol_empty_name,          150),
    (_gen_symbol_none_name_chunks,    150),
    (_gen_file_structure_depth_zero,  200),
    (_gen_similar_empty_snippet,      200),
    (_gen_similar_no_store_results,   200),
    (_gen_similar_no_store_results,   200),  # 추가 200건
    # invalid 2,000건
    (_gen_search_code_raises,         400),
    (_gen_reindex_raises,             300),
    (_gen_symbol_invalid_mode,        400),
    (_gen_file_structure_not_exist,   350),
    (_gen_file_structure_file_not_dir,250),
    (_gen_similar_embed_fails,        150),
    (_gen_similar_embed_raises,       150),
    # stress 1,500건
    (_gen_search_code_large,          500),
    (_gen_file_structure_deep,        500),
    (_gen_similar_stress,             500),
    # random 1,500건
    (_gen_random,                    1500),
]


def generate_cases(output_dir: Path, total: int = 10000) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "test_cases.jsonl"

    schedule_total = sum(cnt for _, cnt in _SCHEDULE)
    if schedule_total != total:
        raise ValueError(f"스케줄 합계({schedule_total})가 total({total})과 다릅니다.")

    print(f"케이스 생성 중... (총 {total:,}건)")
    counter = 0
    category_counts: dict[str, int] = {}

    with open(out_path, "w", encoding="utf-8") as f:
        for gen_fn, count in _SCHEDULE:
            for _ in range(count):
                counter += 1
                tc_id = f"TC-MCP-{counter:05d}"
                tc = gen_fn(tc_id)
                f.write(json.dumps(tc, ensure_ascii=False) + "\n")
                cat = tc["category"]
                category_counts[cat] = category_counts.get(cat, 0) + 1

    print(f"생성 완료: {out_path} ({counter:,}건)")
    for cat, cnt in sorted(category_counts.items()):
        print(f"  {cat}: {cnt:,}건")


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP 서버 QC 케이스 생성기")
    parser.add_argument("--module", default="src/rag/mcp_server.py")
    parser.add_argument("--count", type=int, default=10000)
    parser.add_argument("--output", default="tests/qc/mcp_server/")
    args = parser.parse_args()
    generate_cases(Path(args.output), args.count)


if __name__ == "__main__":
    main()
