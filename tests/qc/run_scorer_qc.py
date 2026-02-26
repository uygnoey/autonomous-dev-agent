"""BM25Scorer 모듈 QC 실행기.

JSONL 테스트 케이스를 배치(1,000건)로 읽어서 실행하고,
결과를 report.json에 저장한다.
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

from src.rag.scorer import BM25Scorer


def _run_single_case(tc: dict) -> dict:
    """단일 테스트 케이스를 실행하고 결과를 반환한다.

    Args:
        tc: 테스트 케이스 딕셔너리

    Returns:
        실행 결과 딕셔너리
    """
    tc_id = tc["id"]
    category = tc["category"]
    method = tc["method"]
    documents = tc.get("documents")
    query = tc.get("query") or ""
    doc_index = tc.get("doc_index")
    k = tc.get("k")
    expected = tc["expected"]

    start = time.perf_counter()
    passed = False
    actual = None
    error_msg = None
    root_cause = None

    try:
        scorer = BM25Scorer()

        # fit 처리
        if method in ("fit", "fit_score", "fit_top_k"):
            scorer.fit(documents if documents is not None else [])

        # 메서드 실행
        if method in ("score", "fit_score"):
            result = scorer.score(query, doc_index if doc_index is not None else 0)
        elif method in ("top_k", "fit_top_k"):
            result = scorer.top_k(query, k if k is not None else 0)
        elif method == "fit":
            result = None  # fit만 실행
        else:
            result = scorer.score(query, 0)

        elapsed = time.perf_counter() - start

        # 결과 검증
        exp_type = expected.get("type", "list")
        checks = []

        if exp_type == "float":
            if not isinstance(result, (int, float)):
                checks.append(f"float이 아닌 타입: {type(result)}")
            else:
                result_f = float(result)
                if "exact" in expected and expected["exact"] is not None:
                    if result_f != expected["exact"]:
                        checks.append(f"기대값={expected['exact']}, 실제={result_f}")
                # BM25Okapi는 음수 점수가 가능하므로 min 조건은 exact=0.0 케이스에만 적용됨
                # (범위 초과, fit 전 호출, 빈 쿼리는 exact=0.0으로 검증)

        elif exp_type == "empty_list":
            if result != []:
                checks.append(f"빈 리스트가 아님: {result!r:.100}")

        elif exp_type == "list_of_tuples":
            if not isinstance(result, list):
                checks.append(f"list가 아닌 타입: {type(result)}")
            else:
                # 각 원소가 (int, float) 튜플인지 확인
                for item in result:
                    if not (isinstance(item, tuple) and len(item) == 2):
                        checks.append(f"튜플이 아닌 원소: {item!r}")
                        break
                    idx_val, score_val = item
                    if not isinstance(idx_val, int):
                        checks.append(f"인덱스가 int 아님: {idx_val!r}")
                        break
                    if not isinstance(score_val, float):
                        checks.append(f"점수가 float 아님: {score_val!r}")
                        break
                    if score_val < 0.0:
                        checks.append(f"음수 점수: {score_val}")
                        break

                # max_length 검증
                max_len = expected.get("max_length")
                if max_len is not None and len(result) > max_len:
                    checks.append(f"결과 수({len(result)}) > max_length({max_len})")

                # 내림차순 정렬 검증
                if expected.get("sorted_desc") and len(result) > 1:
                    scores = [s for _, s in result]
                    if scores != sorted(scores, reverse=True):
                        checks.append("내림차순 정렬 위반")

        elif exp_type in ("list", None):
            # 예외만 없으면 통과 (결과 타입 무관)
            pass

        if checks:
            passed = False
            actual = "; ".join(checks)
            root_cause = checks[0]
        else:
            passed = True
            actual = f"정상 결과: {type(result).__name__}" + (
                f"({len(result)}개)" if isinstance(result, list) else
                f"({result:.4f})" if isinstance(result, float) else ""
            )

    except Exception as e:
        elapsed = time.perf_counter() - start
        passed = False
        actual = f"예외 발생: {type(e).__name__}: {e}"
        error_msg = traceback.format_exc()
        root_cause = f"{type(e).__name__} in BM25Scorer.{method}()"

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


def run_qc(
    cases_path: Path,
    report_path: Path,
    batch_size: int = 1000,
) -> dict:
    """QC 테스트를 배치로 실행하고 리포트를 저장한다."""
    total = 0
    passed = 0
    failed = 0
    failures_by_category: dict[str, int] = {}
    top_failures: list[dict] = []
    total_elapsed_ms = 0.0

    report_path.parent.mkdir(parents=True, exist_ok=True)
    results_path = report_path.parent / "results.jsonl"

    print(f"QC 실행 시작: {cases_path}")
    print(f"배치 크기: {batch_size}")

    start_time = time.time()

    with (
        open(cases_path, "r", encoding="utf-8") as cases_f,
        open(results_path, "w", encoding="utf-8") as results_f,
    ):
        batch = []
        for line in cases_f:
            line = line.strip()
            if not line:
                continue
            tc = json.loads(line)
            batch.append(tc)

            if len(batch) >= batch_size:
                for item in batch:
                    result = _run_single_case(item)
                    results_f.write(json.dumps(result, ensure_ascii=False) + "\n")
                    total += 1
                    total_elapsed_ms += result["elapsed_ms"]
                    if result["passed"]:
                        passed += 1
                    else:
                        failed += 1
                        cat = result["category"]
                        failures_by_category[cat] = failures_by_category.get(cat, 0) + 1
                        if len(top_failures) < 50:
                            top_failures.append({
                                "id": result["id"],
                                "category": cat,
                                "method": result["method"],
                                "actual": result["actual"],
                                "root_cause": result["root_cause"],
                                "error": result["error"],
                            })
                if total % 1000 == 0:
                    elapsed = time.time() - start_time
                    rate = total / elapsed if elapsed > 0 else 0
                    print(f"  진행: {total:,}건 / 통과: {passed:,} / 실패: {failed:,} ({rate:.0f}건/초)")
                batch = []

        for item in batch:
            result = _run_single_case(item)
            results_f.write(json.dumps(result, ensure_ascii=False) + "\n")
            total += 1
            total_elapsed_ms += result["elapsed_ms"]
            if result["passed"]:
                passed += 1
            else:
                failed += 1
                cat = result["category"]
                failures_by_category[cat] = failures_by_category.get(cat, 0) + 1
                if len(top_failures) < 50:
                    top_failures.append({
                        "id": result["id"],
                        "category": cat,
                        "method": result["method"],
                        "actual": result["actual"],
                        "root_cause": result["root_cause"],
                        "error": result["error"],
                    })

    duration_seconds = time.time() - start_time
    pass_rate = (passed / total * 100) if total > 0 else 0.0

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
        "target": "src/rag/scorer.py",
        "total_cases": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(pass_rate, 4),
        "duration_seconds": round(duration_seconds, 2),
        "avg_case_ms": round(total_elapsed_ms / total, 3) if total > 0 else 0,
        "failures_by_category": failures_by_category,
        "top_failures": top_failures[:20],
        "fix_requests": fix_requests,
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\nQC 완료!")
    print(f"  총 케이스: {total:,}건")
    print(f"  통과: {passed:,}건")
    print(f"  실패: {failed:,}건")
    print(f"  통과율: {pass_rate:.2f}%")
    print(f"  소요시간: {duration_seconds:.1f}초")
    print(f"  리포트: {report_path}")

    return summary


def main() -> None:
    """CLI 진입점."""
    parser = argparse.ArgumentParser(description="BM25Scorer 모듈 QC 실행기")
    parser.add_argument("--cases", default="tests/qc/scorer/test_cases.jsonl")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--report", default="tests/qc/scorer/report.json")
    args = parser.parse_args()

    cases_path = Path(args.cases)
    report_path = Path(args.report)

    if not cases_path.exists():
        print(f"오류: 테스트 케이스 파일이 없습니다: {cases_path}")
        print("먼저 generate_scorer_cases.py를 실행하세요.")
        sys.exit(1)

    summary = run_qc(cases_path, report_path, args.batch_size)
    sys.exit(0 if summary["pass_rate"] == 100.0 else 1)


if __name__ == "__main__":
    main()
