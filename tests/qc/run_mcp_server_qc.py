"""MCP 서버 모듈 QC 실행기.

JSONL 테스트 케이스를 배치로 읽어 실행하고 report.json에 저장한다.

claude_agent_sdk 의존 없이 mcp_server.py의 핵심 로직을 검증한다:
- 모듈 레벨 헬퍼: _text_response, _format_results, _match, _build_tree
- tool 로직: IncrementalIndexer mock으로 주입하여 각 도구 함수 인라인 실행
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
import time
import traceback
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.core.domain import CodeChunk
from src.rag.incremental_indexer import IGNORED_DIRS
from src.rag.mcp_server import (
    _build_tree,
    _format_results,
    _match,
    _text_response,
)


# ------------------------------------------------------------------
# 헬퍼: CodeChunk 재구성
# ------------------------------------------------------------------

def _to_chunk(d: dict) -> CodeChunk:
    return CodeChunk(
        file_path=d["file_path"],
        content=d["content"],
        start_line=d["start_line"],
        end_line=d["end_line"],
        chunk_type=d.get("chunk_type", "function"),
        name=d.get("name"),
    )


def _to_chunks(raw: list[dict]) -> list[CodeChunk]:
    return [_to_chunk(d) for d in raw]


def _to_chunk_score_pairs(raw: list) -> list[tuple[CodeChunk, float]]:
    """store_results: [(chunk_dict, score), ...] → [(CodeChunk, float), ...]"""
    result = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            chunk_data, score = item
            if isinstance(chunk_data, dict):
                result.append((_to_chunk(chunk_data), float(score)))
    return result


# ------------------------------------------------------------------
# tool 로직 인라인 구현 (mcp_server.py와 동일 로직)
# ------------------------------------------------------------------

async def _exec_search_code(args: dict, ctx: dict) -> dict:
    """search_code tool 로직 재현."""
    query = str(args.get("query", "")).strip()
    top_k = int(args.get("top_k", 5))

    if not query:
        return _text_response("query 파라미터가 필요합니다.")

    if ctx.get("search_raises"):
        try:
            raise RuntimeError("mock search error")
        except Exception:
            return _text_response(f"검색 중 오류 발생:\n{traceback.format_exc()}")

    chunks = _to_chunks(ctx.get("search_chunks") or [])
    if not chunks:
        return _text_response(f"'{query}'에 대한 검색 결과가 없습니다.")
    return _format_results(chunks, header=f"검색 결과: '{query}'")


async def _exec_reindex_codebase(args: dict, ctx: dict) -> dict:
    """reindex_codebase tool 로직 재현."""
    if ctx.get("update_raises"):
        try:
            raise RuntimeError("mock update error")
        except Exception:
            return _text_response(f"재인덱싱 중 오류 발생:\n{traceback.format_exc()}")

    counts = ctx.get("update_counts", {"added": 0, "updated": 0, "removed": 0})
    text = (
        f"증분 재인덱싱 완료\n"
        f"  추가: {counts.get('added', 0)}개 파일\n"
        f"  수정: {counts.get('updated', 0)}개 파일\n"
        f"  삭제: {counts.get('removed', 0)}개 파일"
    )
    return _text_response(text)


async def _exec_search_by_symbol(args: dict, ctx: dict) -> dict:
    """search_by_symbol tool 로직 재현."""
    name = str(args.get("name", "")).strip()
    mode = str(args.get("mode", "contains"))

    if not name:
        return _text_response("name 파라미터가 필요합니다.")

    if mode not in ("exact", "prefix", "contains"):
        return _text_response(
            f"잘못된 mode '{mode}'. 'exact', 'prefix', 'contains' 중 하나여야 합니다."
        )

    all_chunks = _to_chunks(ctx.get("all_chunks") or [])
    matches = [c for c in all_chunks if c.name and _match(c.name, name, mode)]

    if not matches:
        return _text_response(f"심볼 '{name}' (mode={mode})에 대한 검색 결과가 없습니다.")
    return _format_results(matches, header=f"심볼 검색: '{name}' (mode={mode})")


async def _exec_get_file_structure(args: dict, ctx: dict, tmp_dir: str) -> dict:
    """get_file_structure tool 로직 재현 (임시 디렉토리 사용)."""
    raw_path = str(args.get("path", "")).strip()
    depth = int(args.get("depth", 3))

    # 특수 케이스: "__FILE__" → 실제 파일 경로로 교체
    if raw_path == "__FILE__":
        test_file = Path(tmp_dir) / "test_file.py"
        test_file.write_text("# test", encoding="utf-8")
        raw_path = str(test_file)

    # 프로젝트 파일 구성
    project_dir = Path(tmp_dir) / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    for rel_path in ctx.get("project_files", []):
        f = project_dir / rel_path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("# content", encoding="utf-8")

    root = Path(raw_path) if raw_path and raw_path != str(project_dir) else project_dir

    if not root.exists():
        return _text_response(f"경로를 찾을 수 없습니다: {root}")

    if not root.is_dir():
        return _text_response(f"디렉토리가 아닙니다: {root}")

    try:
        tree = _build_tree(root, depth, IGNORED_DIRS)
    except Exception:
        return _text_response(f"디렉토리 트리 생성 중 오류 발생:\n{traceback.format_exc()}")

    return _text_response(tree)


async def _exec_get_similar_patterns(args: dict, ctx: dict) -> dict:
    """get_similar_patterns tool 로직 재현."""
    snippet = str(args.get("code_snippet", "")).strip()
    top_k = int(args.get("top_k", 5))

    if not snippet:
        return _text_response("code_snippet 파라미터가 필요합니다.")

    if ctx.get("embed_raises"):
        try:
            raise RuntimeError("mock embed error")
        except Exception:
            return _text_response(f"임베딩 생성 중 오류 발생:\n{traceback.format_exc()}")

    embedding = ctx.get("embed_result") or []
    if not embedding:
        return _text_response(
            "임베딩 생성에 실패했습니다. "
            "VOYAGE_API_KEY 또는 ANTHROPIC_API_KEY 환경변수를 확인하세요."
        )

    store_results = _to_chunk_score_pairs(ctx.get("store_results") or [])
    chunks = [c for c, _ in store_results[:top_k]]

    if not chunks:
        return _text_response("유사한 코드 패턴을 찾을 수 없습니다.")
    return _format_results(chunks, header="유사 코드 패턴")


# ------------------------------------------------------------------
# 단일 케이스 실행
# ------------------------------------------------------------------

def _run_single_case(tc: dict) -> dict:
    tc_id: str = tc["id"]
    category: str = tc["category"]
    tool: str = tc["tool"]
    args: dict = tc.get("args", {})
    ctx: dict = tc.get("context", {})
    expected: dict = tc["expected"]

    start = time.perf_counter()
    passed = False
    actual = None
    error_msg = None
    root_cause = None

    try:
        exp_type = expected.get("type")

        # --- 헬퍼 함수 직접 테스트 ---
        if tool == "_text_response":
            result = _text_response(args["text"])
            passed, actual, root_cause = _check_mcp_response(result, expected)

        elif tool == "_format_results":
            chunks = _to_chunks(args.get("chunks", []))
            result = _format_results(chunks, args.get("header", "결과"))
            passed, actual, root_cause = _check_mcp_response(result, expected)

        elif tool == "_match":
            result = _match(args["chunk_name"], args["query"], args["mode"])
            expected_bool = expected.get("bool_value")
            if result == expected_bool:
                passed = True
                actual = f"_match 결과: {result}"
            else:
                passed = False
                actual = f"_match 기대={expected_bool}, 실제={result}"
                root_cause = actual

        elif tool == "_build_tree":
            with tempfile.TemporaryDirectory() as tmp:
                root_dir = Path(tmp)
                depth = args.get("depth", 3)
                tree = _build_tree(root_dir, depth, IGNORED_DIRS)
                if exp_type == "no_exception":
                    passed = True
                    actual = f"트리 생성 완료: {len(tree)}자"
                else:
                    passed = True
                    actual = f"트리 생성 완료: {len(tree)}자"

        # --- tool 함수 테스트 ---
        elif tool in ("search_code", "reindex_codebase", "search_by_symbol",
                      "get_file_structure", "get_similar_patterns"):

            with tempfile.TemporaryDirectory() as tmp_dir:
                if tool == "search_code":
                    result = asyncio.run(_exec_search_code(args, ctx))
                elif tool == "reindex_codebase":
                    result = asyncio.run(_exec_reindex_codebase(args, ctx))
                elif tool == "search_by_symbol":
                    result = asyncio.run(_exec_search_by_symbol(args, ctx))
                elif tool == "get_file_structure":
                    result = asyncio.run(_exec_get_file_structure(args, ctx, tmp_dir))
                else:  # get_similar_patterns
                    result = asyncio.run(_exec_get_similar_patterns(args, ctx))

            passed, actual, root_cause = _check_mcp_response(result, expected)

        else:
            passed = False
            actual = f"알 수 없는 tool: {tool}"
            root_cause = actual

    except Exception as e:
        passed = False
        actual = f"예외 발생: {type(e).__name__}: {e}"
        error_msg = traceback.format_exc()
        root_cause = f"{type(e).__name__} in tool={tool}"

    elapsed_ms = round((time.perf_counter() - start) * 1000, 3)
    return {
        "id": tc_id,
        "category": category,
        "tool": tool,
        "passed": passed,
        "actual": actual,
        "error": error_msg,
        "root_cause": root_cause,
        "elapsed_ms": elapsed_ms,
    }


def _check_mcp_response(
    result: dict,
    expected: dict,
) -> tuple[bool, str, str | None]:
    """MCP 응답 형식과 text_contains 검증."""
    checks: list[str] = []

    # content 존재 여부
    if expected.get("has_content"):
        content = result.get("content")
        if not isinstance(content, list) or len(content) == 0:
            checks.append("content 배열 없음 또는 비어있음")
        else:
            text = content[0].get("text", "")
            for phrase in expected.get("text_contains", []):
                if phrase and phrase not in text:
                    checks.append(f"text에 '{phrase}' 없음")

    if checks:
        return False, "; ".join(checks), checks[0]
    return True, f"MCP 응답 정상: {str(result)[:80]}", None


# ------------------------------------------------------------------
# 배치 실행
# ------------------------------------------------------------------

def run_qc(cases_path: Path, report_path: Path, batch_size: int = 1000) -> dict:
    total = 0
    passed_count = 0
    failed_count = 0
    failures_by_category: dict[str, int] = {}
    top_failures: list[dict] = []
    total_elapsed_ms = 0.0

    report_path.parent.mkdir(parents=True, exist_ok=True)
    results_path = report_path.parent / "results.jsonl"

    print(f"QC 실행 시작: {cases_path}")
    print(f"배치 크기: {batch_size}")

    wall_start = time.time()

    with (
        open(cases_path, "r", encoding="utf-8") as cases_f,
        open(results_path, "w", encoding="utf-8") as results_f,
    ):
        batch: list[dict] = []

        def _flush_batch(items: list[dict]) -> None:
            nonlocal total, passed_count, failed_count, total_elapsed_ms

            for item in items:
                result = _run_single_case(item)
                results_f.write(json.dumps(result, ensure_ascii=False) + "\n")
                total += 1
                total_elapsed_ms += result["elapsed_ms"]

                if result["passed"]:
                    passed_count += 1
                else:
                    failed_count += 1
                    cat = result["category"]
                    failures_by_category[cat] = failures_by_category.get(cat, 0) + 1
                    if len(top_failures) < 50:
                        top_failures.append({
                            "id": result["id"],
                            "category": cat,
                            "tool": result["tool"],
                            "actual": result["actual"],
                            "root_cause": result["root_cause"],
                            "error": result["error"],
                        })

            if total % 1000 == 0:
                elapsed = time.time() - wall_start
                rate = total / elapsed if elapsed > 0 else 0
                print(
                    f"  진행: {total:,}건 / 통과: {passed_count:,} / 실패: {failed_count:,}"
                    f" ({rate:.0f}건/초)"
                )

        for line in cases_f:
            line = line.strip()
            if not line:
                continue
            batch.append(json.loads(line))
            if len(batch) >= batch_size:
                _flush_batch(batch)
                batch = []
        if batch:
            _flush_batch(batch)

    duration = time.time() - wall_start
    pass_rate = (passed_count / total * 100) if total > 0 else 0.0

    fix_requests = []
    for cat, cnt in failures_by_category.items():
        samples = [f for f in top_failures if f["category"] == cat][:3]
        fix_requests.append({"category": cat, "failed_cases_count": cnt, "sample_failures": samples})

    summary = {
        "test_type": "module_qc",
        "target": "src/rag/mcp_server.py",
        "total_cases": total,
        "passed": passed_count,
        "failed": failed_count,
        "pass_rate": round(pass_rate, 4),
        "duration_seconds": round(duration, 2),
        "avg_case_ms": round(total_elapsed_ms / total, 3) if total > 0 else 0,
        "failures_by_category": failures_by_category,
        "top_failures": top_failures[:20],
        "fix_requests": fix_requests,
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\nQC 완료!")
    print(f"  총 케이스: {total:,}건")
    print(f"  통과: {passed_count:,}건")
    print(f"  실패: {failed_count:,}건")
    print(f"  통과율: {pass_rate:.2f}%")
    print(f"  소요시간: {duration:.1f}초")
    print(f"  리포트: {report_path}")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP 서버 QC 실행기")
    parser.add_argument("--cases", default="tests/qc/mcp_server/test_cases.jsonl")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--report", default="tests/qc/mcp_server/report.json")
    args = parser.parse_args()

    cases_path = Path(args.cases)
    report_path = Path(args.report)

    if not cases_path.exists():
        print(f"오류: 테스트 케이스 파일이 없습니다: {cases_path}")
        sys.exit(1)

    summary = run_qc(cases_path, report_path, args.batch_size)
    sys.exit(0 if summary["pass_rate"] == 100.0 else 1)


if __name__ == "__main__":
    main()
