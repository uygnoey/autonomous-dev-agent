"""IncrementalIndexer 모듈 QC 케이스 생성기.

10,000건의 JSONL 테스트 케이스를 생성한다.

IncrementalIndexer는 파일시스템을 직접 사용하므로,
케이스에 가상 파일 목록(경로 + 내용)을 포함한다.
QC 실행기가 임시 디렉토리를 생성하여 실제 파일로 구성한 뒤 실행한다.

케이스 포맷:
- id: TC-INDEXER-XXXXX
- category: normal / boundary / invalid / stress / random
- description: 케이스 설명
- operation: "index" | "update" | "search"
- files: [{path: str, content: str}] — 초기 파일 목록
- update_files: [{path: str, content: str}] — update() 전 변경/추가 파일
- delete_paths: [str] — update() 전 삭제할 파일 경로
- query: 검색 쿼리 (search 시)
- top_k: 검색 결과 수 (search 시)
- embedder_available: bool
- expected:
    type: "index_result" | "update_result" | "search_result" | "no_exception" | "empty_list"
    min_chunks: 최소 반환 청크 수 (index_result)
    added/updated/removed: update 결과 검증 (update_result)
    max_results: 최대 검색 결과 수 (search_result)
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
# 코드 컨텐츠 생성 헬퍼
# ------------------------------------------------------------------

_FUNC_NAMES = [
    "process_data", "load_config", "save_result", "fetch_items",
    "validate_input", "transform_output", "handle_error", "setup_logger",
    "build_index", "search_query", "update_cache", "clear_store",
    "parse_file", "write_file", "read_config", "check_health",
    "run_pipeline", "emit_event", "register_hook", "decode_token",
]

_CLASS_NAMES = [
    "DataProcessor", "ConfigManager", "ResultStore", "EventHandler",
    "QueryEngine", "CacheLayer", "FileParser", "TokenDecoder",
    "PipelineRunner", "IndexBuilder",
]

_KEYWORDS = [
    "search", "index", "embed", "chunk", "score", "query", "result",
    "fetch", "parse", "build", "run", "test", "load", "save", "delete",
    "update", "create", "get", "set", "check", "process", "validate",
]


def _rand_func_content(name: str | None = None) -> str:
    fn = name or random.choice(_FUNC_NAMES)
    body_lines = [
        f"    # {random.choice(_KEYWORDS)} implementation",
        f"    data = {random.choice(['[]', '{}', 'None', '0', '\"\"'])}",
        f"    return data",
    ]
    return f"def {fn}(self, value=None):\n" + "\n".join(body_lines)


def _rand_class_content(name: str | None = None) -> str:
    cn = name or random.choice(_CLASS_NAMES)
    methods = [_rand_func_content() for _ in range(random.randint(1, 3))]
    methods_str = "\n\n".join("    " + line for m in methods for line in m.splitlines())
    return f"class {cn}:\n{methods_str}\n"


def _rand_py_content(n_funcs: int = 2) -> str:
    lines = [f'"""Module for {random.choice(_KEYWORDS)} operations."""\n']
    for _ in range(n_funcs):
        lines.append(_rand_func_content())
        lines.append("")
    return "\n".join(lines)


def _rand_md_content() -> str:
    return f"# {random.choice(_KEYWORDS).capitalize()} Guide\n\nThis module handles {random.choice(_KEYWORDS)} operations.\n"


def _rand_ts_content() -> str:
    fn = random.choice(_FUNC_NAMES)
    return f"export function {fn}(value: string): string {{\n  return value;\n}}\n"


def _file_content(ext: str) -> str:
    if ext == ".py":
        return _rand_py_content(random.randint(1, 4))
    elif ext == ".md":
        return _rand_md_content()
    elif ext in (".ts", ".js", ".tsx", ".jsx"):
        return _rand_ts_content()
    else:
        return f"# {random.choice(_KEYWORDS)}\n"


def _make_files(n: int, base_dir: str = "src") -> list[dict]:
    """n개의 가상 파일 목록을 생성한다."""
    exts = [".py", ".py", ".py", ".md", ".ts"]  # .py 비중 높임
    files = []
    used_paths: set[str] = set()
    for i in range(n):
        ext = random.choice(exts)
        path = f"{base_dir}/module_{i:03d}{ext}"
        if path in used_paths:
            path = f"{base_dir}/module_{i:03d}_{random.randint(0, 99)}{ext}"
        used_paths.add(path)
        files.append({"path": path, "content": _file_content(ext)})
    return files


# ------------------------------------------------------------------
# 카테고리별 케이스 생성
# ------------------------------------------------------------------

def _gen_normal_index(tc_id: str) -> dict:
    """정상 전체 인덱싱."""
    n = random.randint(3, 15)
    files = _make_files(n)
    return {
        "id": tc_id,
        "category": "normal",
        "description": f"전체 인덱싱: {n}개 파일",
        "operation": "index",
        "files": files,
        "update_files": [],
        "delete_paths": [],
        "query": "",
        "top_k": 0,
        "embedder_available": False,
        "expected": {
            "type": "index_result",
            "min_chunks": 1,
        },
    }


def _gen_normal_update_add(tc_id: str) -> dict:
    """정상 증분 업데이트: 신규 파일 추가."""
    n = random.randint(2, 8)
    files = _make_files(n, "src")
    new_files = _make_files(random.randint(1, 3), "src/new")
    return {
        "id": tc_id,
        "category": "normal",
        "description": f"증분 업데이트: {n}개 기존 + {len(new_files)}개 신규",
        "operation": "update",
        "files": files,
        "update_files": new_files,
        "delete_paths": [],
        "query": "",
        "top_k": 0,
        "embedder_available": False,
        "expected": {
            "type": "update_result",
            "added": len(new_files),
            "updated": 0,
            "removed": 0,
        },
    }


def _gen_normal_update_remove(tc_id: str) -> dict:
    """정상 증분 업데이트: 파일 삭제."""
    n = random.randint(3, 8)
    files = _make_files(n, "src")
    remove_count = random.randint(1, min(2, n))
    delete_paths = [f["path"] for f in files[:remove_count]]
    return {
        "id": tc_id,
        "category": "normal",
        "description": f"증분 업데이트: {n}개 중 {remove_count}개 삭제",
        "operation": "update",
        "files": files,
        "update_files": [],
        "delete_paths": delete_paths,
        "query": "",
        "top_k": 0,
        "embedder_available": False,
        "expected": {
            "type": "update_result",
            "added": 0,
            "updated": 0,
            "removed": remove_count,
        },
    }


def _gen_normal_update_modify(tc_id: str) -> dict:
    """정상 증분 업데이트: 파일 수정."""
    n = random.randint(3, 8)
    files = _make_files(n, "src")
    mod_count = random.randint(1, min(2, n))
    # 수정: 동일 경로, 다른 내용
    update_files = [
        {"path": files[i]["path"], "content": _rand_py_content(2)}
        for i in range(mod_count)
    ]
    return {
        "id": tc_id,
        "category": "normal",
        "description": f"증분 업데이트: {n}개 중 {mod_count}개 수정",
        "operation": "update",
        "files": files,
        "update_files": update_files,
        "delete_paths": [],
        "query": "",
        "top_k": 0,
        "embedder_available": False,
        "expected": {
            "type": "update_result",
            "added": 0,
            "updated": mod_count,
            "removed": 0,
        },
    }


def _gen_normal_search(tc_id: str) -> dict:
    """정상 검색."""
    n = random.randint(3, 10)
    files = _make_files(n)
    query = random.choice(_KEYWORDS)
    top_k = random.randint(1, 5)
    return {
        "id": tc_id,
        "category": "normal",
        "description": f"검색: query={query!r}, top_k={top_k}",
        "operation": "search",
        "files": files,
        "update_files": [],
        "delete_paths": [],
        "query": query,
        "top_k": top_k,
        "embedder_available": False,
        "expected": {
            "type": "search_result",
            "max_results": top_k,
        },
    }


def _gen_boundary_empty_project(tc_id: str) -> dict:
    """경계값: 빈 프로젝트 (파일 없음)."""
    return {
        "id": tc_id,
        "category": "boundary",
        "description": "빈 프로젝트 index → 0청크",
        "operation": "index",
        "files": [],
        "update_files": [],
        "delete_paths": [],
        "query": "",
        "top_k": 0,
        "embedder_available": False,
        "expected": {
            "type": "index_result",
            "min_chunks": 0,
            "exact_chunks": 0,
        },
    }


def _gen_boundary_single_file(tc_id: str) -> dict:
    """경계값: 단일 파일."""
    files = _make_files(1)
    return {
        "id": tc_id,
        "category": "boundary",
        "description": "단일 파일 index",
        "operation": "index",
        "files": files,
        "update_files": [],
        "delete_paths": [],
        "query": "",
        "top_k": 0,
        "embedder_available": False,
        "expected": {
            "type": "index_result",
            "min_chunks": 1,
        },
    }


def _gen_boundary_update_no_change(tc_id: str) -> dict:
    """경계값: 변경 없음 update."""
    n = random.randint(2, 5)
    files = _make_files(n)
    return {
        "id": tc_id,
        "category": "boundary",
        "description": "변경 없음 update → all 0",
        "operation": "update",
        "files": files,
        "update_files": [],
        "delete_paths": [],
        "query": "",
        "top_k": 0,
        "embedder_available": False,
        "expected": {
            "type": "update_result",
            "added": 0,
            "updated": 0,
            "removed": 0,
        },
    }


def _gen_boundary_search_empty_index(tc_id: str) -> dict:
    """경계값: 빈 인덱스 search → 빈 리스트."""
    return {
        "id": tc_id,
        "category": "boundary",
        "description": "빈 인덱스 search → empty_list",
        "operation": "search",
        "files": [],
        "update_files": [],
        "delete_paths": [],
        "query": "search query",
        "top_k": 5,
        "embedder_available": False,
        "expected": {"type": "empty_list"},
    }


def _gen_boundary_search_topk_zero(tc_id: str) -> dict:
    """경계값: top_k=0 search."""
    n = random.randint(2, 5)
    files = _make_files(n)
    return {
        "id": tc_id,
        "category": "boundary",
        "description": "top_k=0 search → empty_list",
        "operation": "search",
        "files": files,
        "update_files": [],
        "delete_paths": [],
        "query": "search",
        "top_k": 0,
        "embedder_available": False,
        "expected": {"type": "empty_list"},
    }


def _gen_boundary_search_empty_query(tc_id: str) -> dict:
    """경계값: 빈 쿼리 search."""
    n = random.randint(2, 5)
    files = _make_files(n)
    return {
        "id": tc_id,
        "category": "boundary",
        "description": "빈 쿼리 search → empty_list",
        "operation": "search",
        "files": files,
        "update_files": [],
        "delete_paths": [],
        "query": "",
        "top_k": 5,
        "embedder_available": False,
        "expected": {"type": "empty_list"},
    }


def _gen_boundary_ignored_dirs(tc_id: str) -> dict:
    """경계값: IGNORED_DIRS 내 파일은 인덱싱 제외."""
    normal_files = _make_files(2, "src")
    ignored_files = [
        {"path": "__pycache__/cached.py", "content": "# cached"},
        {"path": ".git/config", "content": "# git config"},
        {"path": "node_modules/lib.js", "content": "// lib"},
        {"path": ".venv/site.py", "content": "# venv"},
    ]
    return {
        "id": tc_id,
        "category": "boundary",
        "description": "IGNORED_DIRS 파일 제외 검증",
        "operation": "index",
        "files": normal_files + ignored_files,
        "update_files": [],
        "delete_paths": [],
        "query": "",
        "top_k": 0,
        "embedder_available": False,
        "expected": {
            "type": "index_result",
            "min_chunks": 1,
        },
    }


def _gen_invalid_corrupted_cache(tc_id: str) -> dict:
    """invalid: 손상된 file_index.json → no_exception (빈 인덱스로 시작)."""
    n = random.randint(2, 5)
    files = _make_files(n)
    return {
        "id": tc_id,
        "category": "invalid",
        "description": "손상된 캐시 → no_exception",
        "operation": "update",
        "files": files,
        "update_files": [],
        "delete_paths": [],
        "query": "",
        "top_k": 0,
        "embedder_available": False,
        "corrupted_cache": True,  # QC 실행기가 손상된 JSON 파일 생성
        "expected": {"type": "no_exception"},
    }


def _gen_invalid_binary_file(tc_id: str) -> dict:
    """invalid: 바이너리 확장자 파일 → 읽기 시도 안 함."""
    normal_files = _make_files(2, "src")
    # .pyc, .so 등은 BINARY_EXTENSIONS에 해당하여 무시됨
    # .py 파일만 인덱싱됨
    return {
        "id": tc_id,
        "category": "invalid",
        "description": "바이너리 파일 포함 → no_exception",
        "operation": "index",
        "files": normal_files,
        "update_files": [],
        "delete_paths": [],
        "query": "",
        "top_k": 0,
        "embedder_available": False,
        "include_binary": True,  # QC 실행기가 .pyc 파일 추가
        "expected": {
            "type": "index_result",
            "min_chunks": 1,
        },
    }


def _gen_invalid_embedder_fail(tc_id: str) -> dict:
    """invalid: embedder 실패 → BM25-only 모드, no_exception."""
    n = random.randint(2, 6)
    files = _make_files(n)
    return {
        "id": tc_id,
        "category": "invalid",
        "description": "embedder 실패 → BM25-only no_exception",
        "operation": "index",
        "files": files,
        "update_files": [],
        "delete_paths": [],
        "query": "",
        "top_k": 0,
        "embedder_available": True,
        "embed_fails": True,  # embed()가 빈 리스트 반환
        "expected": {
            "type": "no_exception",
        },
    }


def _gen_invalid_unsupported_ext(tc_id: str) -> dict:
    """invalid: 지원하지 않는 확장자 파일 → 인덱싱 제외."""
    normal_files = _make_files(2, "src")
    return {
        "id": tc_id,
        "category": "invalid",
        "description": "미지원 확장자 파일 포함 → no_exception",
        "operation": "index",
        "files": normal_files,
        "update_files": [],
        "delete_paths": [],
        "query": "",
        "top_k": 0,
        "embedder_available": False,
        "include_unsupported": True,  # QC 실행기가 .csv, .log 파일 추가
        "expected": {
            "type": "index_result",
            "min_chunks": 1,
        },
    }


def _gen_invalid_update_then_search(tc_id: str) -> dict:
    """invalid: update 후 삭제된 파일 검색 → no_exception."""
    n = random.randint(3, 6)
    files = _make_files(n)
    delete_paths = [files[0]["path"]]
    return {
        "id": tc_id,
        "category": "invalid",
        "description": "삭제 후 검색 → no_exception",
        "operation": "update_then_search",
        "files": files,
        "update_files": [],
        "delete_paths": delete_paths,
        "query": random.choice(_KEYWORDS),
        "top_k": 3,
        "embedder_available": False,
        "expected": {"type": "no_exception"},
    }


def _gen_stress_large_project(tc_id: str) -> dict:
    """stress: 대규모 프로젝트 (50~100개 파일)."""
    n = random.randint(50, 100)
    files = _make_files(n, "src")
    return {
        "id": tc_id,
        "category": "stress",
        "description": f"대규모 프로젝트: {n}개 파일",
        "operation": "index",
        "files": files,
        "update_files": [],
        "delete_paths": [],
        "query": "",
        "top_k": 0,
        "embedder_available": False,
        "expected": {
            "type": "index_result",
            "min_chunks": n // 2,
        },
    }


def _gen_stress_frequent_update(tc_id: str) -> dict:
    """stress: index + 반복 update (add+remove+modify 혼합)."""
    n = random.randint(10, 20)
    files = _make_files(n, "src")
    add_files = _make_files(random.randint(1, 3), "src/extra")
    remove_count = random.randint(1, 2)
    delete_paths = [f["path"] for f in files[:remove_count]]
    mod_files = [
        {"path": files[remove_count]["path"], "content": _rand_py_content(2)}
    ]
    return {
        "id": tc_id,
        "category": "stress",
        "description": f"혼합 update: add={len(add_files)}, remove={remove_count}, modify=1",
        "operation": "update",
        "files": files,
        "update_files": add_files + mod_files,
        "delete_paths": delete_paths,
        "query": "",
        "top_k": 0,
        "embedder_available": False,
        "expected": {
            "type": "update_result",
            "added": len(add_files),
            "updated": 1,
            "removed": remove_count,
        },
    }


def _gen_stress_search_large(tc_id: str) -> dict:
    """stress: 대규모 인덱스에서 검색."""
    n = random.randint(30, 60)
    files = _make_files(n, "src")
    query = random.choice(_KEYWORDS)
    top_k = random.randint(5, 20)
    return {
        "id": tc_id,
        "category": "stress",
        "description": f"대규모 검색: {n}개 파일, top_k={top_k}",
        "operation": "search",
        "files": files,
        "update_files": [],
        "delete_paths": [],
        "query": query,
        "top_k": top_k,
        "embedder_available": False,
        "expected": {
            "type": "search_result",
            "max_results": top_k,
        },
    }


def _gen_random(tc_id: str) -> dict:
    """random: 무작위 파라미터 조합."""
    n = random.randint(0, 20)
    files = _make_files(n) if n > 0 else []
    op = random.choice(["index", "update", "search"])
    query = random.choice(_KEYWORDS + [""]) if op == "search" else ""
    top_k = random.randint(0, 10) if op == "search" else 0
    embedder_available = random.choice([True, False])
    embed_fails = random.choice([True, False]) if embedder_available else False

    if op == "update":
        add_count = random.randint(0, 3)
        remove_count = random.randint(0, min(2, n))
        update_files = _make_files(add_count, "src/rand") if add_count > 0 else []
        delete_paths = [f["path"] for f in files[:remove_count]]
        exp: dict = {
            "type": "update_result",
            "added": add_count,
            "updated": 0,
            "removed": remove_count,
        }
    elif op == "search":
        update_files = []
        delete_paths = []
        if not query.strip() or n == 0 or top_k <= 0:
            exp = {"type": "empty_list"}
        else:
            exp = {"type": "search_result", "max_results": top_k}
    else:
        update_files = []
        delete_paths = []
        exp = {"type": "no_exception"}

    return {
        "id": tc_id,
        "category": "random",
        "description": f"random: op={op}, n={n}, embedder={embedder_available}",
        "operation": op,
        "files": files,
        "update_files": update_files,
        "delete_paths": delete_paths,
        "query": query,
        "top_k": top_k,
        "embedder_available": embedder_available,
        "embed_fails": embed_fails,
        "expected": exp,
    }


# ------------------------------------------------------------------
# 생성 스케줄 (합계 10,000건)
# ------------------------------------------------------------------

_SCHEDULE = [
    # normal 3,000건
    (_gen_normal_index,           800),
    (_gen_normal_update_add,      600),
    (_gen_normal_update_remove,   600),
    (_gen_normal_update_modify,   600),
    (_gen_normal_search,          400),
    # boundary 2,000건
    (_gen_boundary_empty_project,      250),
    (_gen_boundary_single_file,        250),
    (_gen_boundary_update_no_change,   250),
    (_gen_boundary_search_empty_index, 250),
    (_gen_boundary_search_topk_zero,   200),
    (_gen_boundary_search_empty_query, 200),
    (_gen_boundary_ignored_dirs,       300),
    (_gen_boundary_ignored_dirs,       300),  # 두 번 포함 (300*2=600 포함됨)
    # invalid 2,000건
    (_gen_invalid_corrupted_cache,    400),
    (_gen_invalid_binary_file,         400),
    (_gen_invalid_embedder_fail,       400),
    (_gen_invalid_unsupported_ext,     400),
    (_gen_invalid_update_then_search,  400),
    # stress 1,500건
    (_gen_stress_large_project,        500),
    (_gen_stress_frequent_update,      500),
    (_gen_stress_search_large,         500),
    # random 1,500건
    (_gen_random,                     1500),
]


def generate_cases(output_dir: Path, total: int = 10000) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "test_cases.jsonl"

    schedule_total = sum(cnt for _, cnt in _SCHEDULE)
    if schedule_total != total:
        raise ValueError(
            f"스케줄 합계({schedule_total})가 total({total})과 다릅니다."
        )

    print(f"케이스 생성 중... (총 {total:,}건)")

    counter = 0
    category_counts: dict[str, int] = {}

    with open(out_path, "w", encoding="utf-8") as f:
        for gen_fn, count in _SCHEDULE:
            for _ in range(count):
                counter += 1
                tc_id = f"TC-INDEXER-{counter:05d}"
                tc = gen_fn(tc_id)
                f.write(json.dumps(tc, ensure_ascii=False) + "\n")
                cat = tc["category"]
                category_counts[cat] = category_counts.get(cat, 0) + 1

    print(f"생성 완료: {out_path} ({counter:,}건)")
    for cat, cnt in sorted(category_counts.items()):
        print(f"  {cat}: {cnt:,}건")


def main() -> None:
    parser = argparse.ArgumentParser(description="IncrementalIndexer QC 케이스 생성기")
    parser.add_argument("--module", default="src/rag/incremental_indexer.py")
    parser.add_argument("--count", type=int, default=10000)
    parser.add_argument("--output", default="tests/qc/incremental_indexer/")
    args = parser.parse_args()
    generate_cases(Path(args.output), args.count)


if __name__ == "__main__":
    main()
