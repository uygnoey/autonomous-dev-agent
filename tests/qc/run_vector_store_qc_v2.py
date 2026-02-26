"""NumpyStore 모듈 QC 실행기 v2.

generate_vector_store_cases.py 생성 포맷(method 필드)을 처리한다.

테스트 케이스 필드:
- method: "add" | "add_search" | "add_remove_search" | "search"
- chunks: list[dict] (직렬화된 CodeChunk)
- embeddings: list[list[float]]
- query_embedding: list[float]
- top_k: int
- remove_path: str ("" = 없음, "__clear__" = clear, 경로 = remove)
- expected.type: "no_exception" | "empty_list" | "search_result" | "exception"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.core.domain import CodeChunk
from src.rag.vector_store import NumpyStore


def _build_chunks(raw: list[dict]) -> list[CodeChunk]:
    """직렬화된 딕셔너리 목록을 CodeChunk 목록으로 변환한다."""
    return [
        CodeChunk(
            file_path=c["file_path"],
            content=c["content"],
            start_line=c["start_line"],
            end_line=c["end_line"],
            chunk_type=c.get("chunk_type", "function"),
            name=c.get("name"),
        )
        for c in raw
    ]


def _run_single_case(tc: dict) -> dict:
    """단일 테스트 케이스를 실행하고 결과를 반환한다."""
    tc_id = tc["id"]
    category = tc["category"]
    method = tc["method"]
    expected = tc["expected"]
    raw_chunks = tc.get("chunks") or []
    raw_embeddings = tc.get("embeddings") or []
    query_embedding = tc.get("query_embedding") or []
    top_k = tc.get("top_k", 0)
    remove_path = tc.get("remove_path", "")

    start = time.perf_counter()
    passed = False
    actual = None
    error_msg = None
    root_cause = None

    try:
        exp_type = expected.get("type", "no_exception")

        if exp_type == "exception":
            # 예외가 발생해야 하는 케이스
            exc_type = expected.get("exception_type", "Exception")
            try:
                chunks = _build_chunks(raw_chunks)
                store = NumpyStore()
                store.add(chunks, raw_embeddings)
                passed = False
                actual = f"{exc_type} 미발생 (예외를 기대했으나 정상 완료)"
                root_cause = actual
            except ValueError as e:
                if exc_type == "ValueError":
                    passed = True
                    actual = f"ValueError 정상 발생: {e}"
                else:
                    passed = False
                    actual = f"ValueError 발생했으나 기대 예외는 {exc_type}"
                    root_cause = actual
            except Exception as e:
                passed = False
                actual = f"예기치 않은 예외: {type(e).__name__}: {e}"
                root_cause = actual

        elif exp_type == "no_exception":
            chunks = _build_chunks(raw_chunks)
            store = NumpyStore()
            store.add(chunks, raw_embeddings)
            passed = True
            actual = f"정상 완료 (size={store.size})"

        elif exp_type == "empty_list":
            chunks = _build_chunks(raw_chunks)
            store = NumpyStore()

            if method == "search":
                result = store.search(query_embedding, top_k)
            elif method in ("add_search", "add_remove_search"):
                if raw_chunks:
                    store.add(chunks, raw_embeddings)

                if method == "add_remove_search":
                    store.remove(remove_path)
                elif remove_path == "__clear__":
                    store.clear()

                result = store.search(query_embedding, top_k)
            else:
                result = []

            if result == []:
                passed = True
                actual = "빈 리스트 반환 (정상)"
            else:
                passed = False
                actual = f"빈 리스트 아님: 길이={len(result)}"
                root_cause = actual

        elif exp_type == "search_result":
            chunks = _build_chunks(raw_chunks)
            store = NumpyStore()

            if method in ("add_search", "add_remove_search"):
                if raw_chunks:
                    store.add(chunks, raw_embeddings)

                if method == "add_remove_search":
                    store.remove(remove_path)
                elif remove_path == "__clear__":
                    store.clear()

            result = store.search(query_embedding, top_k)
            checks = []

            # 길이 정확 일치
            exp_len = expected.get("length")
            if exp_len is not None and len(result) != exp_len:
                checks.append(f"길이 불일치: 기대={exp_len}, 실제={len(result)}")

            # 최대 길이
            max_len = expected.get("max_length")
            if max_len is not None and len(result) > max_len:
                checks.append(f"최대 길이 초과: max={max_len}, 실제={len(result)}")

            # 유사도 내림차순 정렬
            if expected.get("sorted_desc") and result:
                sims = [s for _, s in result]
                if sims != sorted(sims, reverse=True):
                    checks.append("유사도 내림차순 정렬 위반")

            # 삭제된 파일 미포함
            no_path = expected.get("no_removed_path")
            if no_path:
                for chunk, _ in result:
                    if chunk.file_path == no_path:
                        checks.append(f"삭제된 파일({no_path}) 청크가 결과에 포함")
                        break

            # 타입 검증
            for chunk, sim in result:
                if not isinstance(chunk, CodeChunk):
                    checks.append(f"결과 원소가 CodeChunk 아님: {type(chunk)}")
                    break
                if not isinstance(sim, float):
                    checks.append(f"유사도가 float 아님: {type(sim)}")
                    break

            if checks:
                passed = False
                actual = "; ".join(checks)
                root_cause = checks[0]
            else:
                passed = True
                actual = f"정상: {len(result)}개 반환"

        else:
            passed = False
            actual = f"알 수 없는 expected.type: {exp_type}"
            root_cause = actual

    except Exception as e:
        passed = False
        actual = f"예외 발생: {type(e).__name__}: {e}"
        error_msg = traceback.format_exc()
        root_cause = f"{type(e).__name__} in NumpyStore.{method}()"

    return {
        "id": tc_id,
        "category": category,
        "method": method,
        "passed": passed,
        "actual": actual,
        "error": error_msg,
        "root_cause": root_cause,
        "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
    }


def run_qc(cases_path: Path, report_path: Path, batch_size: int = 1000) -> dict:
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

        def _flush(items: list[dict]) -> None:
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
                            "method": result["method"],
                            "actual": result["actual"],
                            "root_cause": result["root_cause"],
                        })

            if total % 1000 == 0:
                elapsed = time.time() - wall_start
                rate = total / elapsed if elapsed > 0 else 0
                print(f"  진행: {total:,}건 / 통과: {passed_count:,} / 실패: {failed_count:,} ({rate:.0f}건/초)")

        for line in cases_f:
            line = line.strip()
            if not line:
                continue
            batch.append(json.loads(line))
            if len(batch) >= batch_size:
                _flush(batch)
                batch = []

        if batch:
            _flush(batch)

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
        "target": "src/rag/vector_store.py",
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
    """CLI 진입점."""
    parser = argparse.ArgumentParser(description="NumpyStore 모듈 QC 실행기 v2")
    parser.add_argument("--cases", default="tests/qc/vector_store/test_cases.jsonl")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--report", default="tests/qc/vector_store/report.json")
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
