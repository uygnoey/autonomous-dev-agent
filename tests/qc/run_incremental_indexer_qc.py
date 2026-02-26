"""IncrementalIndexer 모듈 QC 실행기.

JSONL 테스트 케이스를 배치(1,000건)로 읽어서 실행하고,
결과를 report.json에 저장한다.

각 케이스는 tempfile.TemporaryDirectory()로 격리된 파일시스템에서 실행한다.
embedder는 mock으로 제어한다.
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
from src.rag.chunker import ASTChunker
from src.rag.incremental_indexer import IncrementalIndexer
from src.rag.scorer import BM25Scorer
from src.rag.vector_store import NumpyStore


# ------------------------------------------------------------------
# Mock 헬퍼
# ------------------------------------------------------------------

def _make_mock_embedder(available: bool, embed_fails: bool) -> MagicMock:
    """AnthropicEmbedder mock 생성."""
    mock = MagicMock()
    mock.is_available = available

    if embed_fails or not available:
        mock.embed = AsyncMock(return_value=[])
    else:
        # embed() 호출 시 texts 길이만큼 128차원 zero 벡터 반환
        async def _embed(texts: list[str]) -> list[list[float]]:
            return [[0.1] * 128 for _ in texts]
        mock.embed = _embed

    return mock


# ------------------------------------------------------------------
# 파일시스템 구성 헬퍼
# ------------------------------------------------------------------

def _setup_project(
    tmp_dir: str,
    files: list[dict],
    include_binary: bool = False,
    include_unsupported: bool = False,
    corrupted_cache: bool = False,
) -> Path:
    """임시 디렉토리에 가상 파일 목록을 실제 파일로 생성한다."""
    project = Path(tmp_dir) / "project"
    project.mkdir(parents=True, exist_ok=True)

    for file_info in files:
        file_path = project / file_info["path"]
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(file_info["content"], encoding="utf-8")

    if include_binary:
        binary_path = project / "src" / "compiled.pyc"
        binary_path.parent.mkdir(parents=True, exist_ok=True)
        binary_path.write_bytes(b"\x00\x01\x02\x03binary_content")

    if include_unsupported:
        csv_path = project / "data" / "records.csv"
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.write_text("id,name\n1,test\n", encoding="utf-8")

        log_path = project / "logs" / "app.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("2026-01-01 INFO: started\n", encoding="utf-8")

    if corrupted_cache:
        cache_dir = project / ".rag_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "file_index.json").write_text(
            "{corrupted json!!!", encoding="utf-8"
        )

    return project


def _apply_updates(
    project: Path,
    update_files: list[dict],
    delete_paths: list[str],
) -> None:
    """update_files를 쓰고 delete_paths를 삭제한다."""
    for file_info in update_files:
        file_path = project / file_info["path"]
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(file_info["content"], encoding="utf-8")
        # mtime 강제 갱신 (초 단위 해상도 환경 대비)
        import os
        st = file_path.stat()
        os.utime(file_path, (st.st_atime, st.st_mtime + 1.0))

    for rel_path in delete_paths:
        target = project / rel_path
        if target.exists():
            target.unlink()


# ------------------------------------------------------------------
# 단일 케이스 실행
# ------------------------------------------------------------------

def _run_single_case(tc: dict) -> dict:
    """단일 테스트 케이스를 실행하고 결과 딕셔너리를 반환한다."""
    tc_id: str = tc["id"]
    category: str = tc["category"]
    operation: str = tc["operation"]
    expected: dict = tc["expected"]

    files: list[dict] = tc.get("files") or []
    update_files: list[dict] = tc.get("update_files") or []
    delete_paths: list[str] = tc.get("delete_paths") or []
    query: str = tc.get("query", "")
    top_k: int = tc.get("top_k", 0)
    embedder_available: bool = tc.get("embedder_available", False)
    embed_fails: bool = tc.get("embed_fails", False)
    corrupted_cache: bool = tc.get("corrupted_cache", False)
    include_binary: bool = tc.get("include_binary", False)
    include_unsupported: bool = tc.get("include_unsupported", False)

    start = time.perf_counter()
    passed = False
    actual = None
    error_msg = None
    root_cause = None

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project = _setup_project(
                tmp_dir,
                files,
                include_binary=include_binary,
                include_unsupported=include_unsupported,
                corrupted_cache=corrupted_cache,
            )

            chunker = ASTChunker()
            scorer = BM25Scorer()
            store = NumpyStore()
            embedder = _make_mock_embedder(embedder_available, embed_fails)

            indexer = IncrementalIndexer(
                chunker=chunker,
                scorer=scorer,
                store=store,
                embedder=embedder,
                project_path=str(project),
                cache_dir=".rag_cache",
            )

            exp_type = expected.get("type")

            # --- index ---
            if operation == "index":
                chunk_count = indexer.index()

                if exp_type == "index_result":
                    checks = []
                    min_c = expected.get("min_chunks", 0)
                    exact_c = expected.get("exact_chunks")
                    if chunk_count < min_c:
                        checks.append(f"청크 수 부족: min={min_c}, 실제={chunk_count}")
                    if exact_c is not None and chunk_count != exact_c:
                        checks.append(f"청크 수 불일치: 기대={exact_c}, 실제={chunk_count}")
                    if checks:
                        passed = False
                        actual = "; ".join(checks)
                        root_cause = checks[0]
                    else:
                        passed = True
                        actual = f"index 완료: {chunk_count}개 청크"
                elif exp_type == "no_exception":
                    passed = True
                    actual = f"예외 없이 완료: {chunk_count}개 청크"
                else:
                    passed = False
                    actual = f"알 수 없는 expected.type: {exp_type}"
                    root_cause = actual

            # --- update ---
            elif operation == "update":
                # 먼저 index() 후 파일 변경 적용, update() 실행
                indexer.index()
                _apply_updates(project, update_files, delete_paths)
                counts = indexer.update()

                if exp_type == "update_result":
                    checks = []
                    for key in ("added", "updated", "removed"):
                        exp_val = expected.get(key, 0)
                        actual_val = counts.get(key, 0)
                        if actual_val != exp_val:
                            checks.append(
                                f"{key} 불일치: 기대={exp_val}, 실제={actual_val}"
                            )
                    if checks:
                        passed = False
                        actual = "; ".join(checks)
                        root_cause = checks[0]
                    else:
                        passed = True
                        actual = f"update 완료: {counts}"
                elif exp_type == "no_exception":
                    passed = True
                    actual = f"예외 없이 완료: {counts}"
                else:
                    passed = False
                    actual = f"알 수 없는 expected.type: {exp_type}"
                    root_cause = actual

            # --- search ---
            elif operation == "search":
                indexer.index()
                result = asyncio.run(indexer.search(query, top_k))

                if exp_type == "empty_list":
                    if result == []:
                        passed = True
                        actual = "빈 리스트 반환 (정상)"
                    else:
                        passed = False
                        actual = f"빈 리스트 아님: 길이={len(result)}"
                        root_cause = actual
                elif exp_type == "search_result":
                    checks = []
                    max_r = expected.get("max_results")
                    if max_r is not None and len(result) > max_r:
                        checks.append(f"최대 결과 초과: max={max_r}, 실제={len(result)}")
                    for chunk in result:
                        if not isinstance(chunk, CodeChunk):
                            checks.append(f"결과 원소가 CodeChunk 아님: {type(chunk)}")
                            break
                    if checks:
                        passed = False
                        actual = "; ".join(checks)
                        root_cause = checks[0]
                    else:
                        passed = True
                        actual = f"검색 완료: {len(result)}개 반환"
                elif exp_type == "no_exception":
                    passed = True
                    actual = f"예외 없이 완료: {len(result)}개 반환"
                else:
                    passed = False
                    actual = f"알 수 없는 expected.type: {exp_type}"
                    root_cause = actual

            # --- update_then_search ---
            elif operation == "update_then_search":
                indexer.index()
                _apply_updates(project, update_files, delete_paths)
                indexer.update()
                result = asyncio.run(indexer.search(query, top_k))

                if exp_type == "no_exception":
                    passed = True
                    actual = f"예외 없이 완료: {len(result)}개 반환"
                elif exp_type == "empty_list":
                    if result == []:
                        passed = True
                        actual = "빈 리스트 반환 (정상)"
                    else:
                        passed = False
                        actual = f"빈 리스트 아님: {len(result)}"
                        root_cause = actual
                else:
                    passed = False
                    actual = f"알 수 없는 expected.type: {exp_type}"
                    root_cause = actual

            else:
                passed = False
                actual = f"알 수 없는 operation: {operation}"
                root_cause = actual

    except Exception as e:
        passed = False
        actual = f"예외 발생: {type(e).__name__}: {e}"
        error_msg = traceback.format_exc()
        root_cause = f"{type(e).__name__} in IncrementalIndexer.{operation}()"

    elapsed_ms = round((time.perf_counter() - start) * 1000, 3)

    return {
        "id": tc_id,
        "category": category,
        "operation": operation,
        "passed": passed,
        "actual": actual,
        "error": error_msg,
        "root_cause": root_cause,
        "elapsed_ms": elapsed_ms,
    }


# ------------------------------------------------------------------
# 배치 실행
# ------------------------------------------------------------------

def run_qc(
    cases_path: Path,
    report_path: Path,
    batch_size: int = 1000,
) -> dict:
    """QC 테스트를 배치로 실행하고 리포트를 저장한다."""
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
                            "operation": result["operation"],
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
        fix_requests.append({
            "category": cat,
            "failed_cases_count": cnt,
            "sample_failures": samples,
        })

    summary = {
        "test_type": "module_qc",
        "target": "src/rag/incremental_indexer.py",
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


# ------------------------------------------------------------------
# CLI 진입점
# ------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="IncrementalIndexer 모듈 QC 실행기")
    parser.add_argument(
        "--cases",
        default="tests/qc/incremental_indexer/test_cases.jsonl",
    )
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument(
        "--report",
        default="tests/qc/incremental_indexer/report.json",
    )
    args = parser.parse_args()

    cases_path = Path(args.cases)
    report_path = Path(args.report)

    if not cases_path.exists():
        print(f"오류: 테스트 케이스 파일이 없습니다: {cases_path}")
        print("먼저 generate_incremental_indexer_cases.py를 실행하세요.")
        sys.exit(1)

    summary = run_qc(cases_path, report_path, args.batch_size)
    sys.exit(0 if summary["pass_rate"] == 100.0 else 1)


if __name__ == "__main__":
    main()
