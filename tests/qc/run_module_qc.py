"""모듈 QC 실행기.

JSONL 테스트 케이스를 배치(1,000건)로 읽어서 실행하고,
결과를 report.json에 저장한다.

메모리 효율을 위해 스트리밍 읽기/쓰기를 사용한다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.rag.chunker import ASTChunker
from src.core.domain import CodeChunk


def _run_single_case(chunker: ASTChunker, tc: dict) -> dict:
    """단일 테스트 케이스를 실행하고 결과를 반환한다.

    Args:
        chunker: ASTChunker 인스턴스
        tc: 테스트 케이스 딕셔너리

    Returns:
        실행 결과 딕셔너리
    """
    tc_id = tc["id"]
    category = tc["category"]
    file_path = tc["file_path"]
    content = tc["content"]
    expected = tc["expected"]

    start = time.perf_counter()
    passed = False
    actual = None
    error_msg = None
    root_cause = None

    try:
        chunks = chunker.chunk(file_path, content)
        elapsed = time.perf_counter() - start

        # 결과 검증
        exp_type = expected.get("type", "list")

        if exp_type == "empty_list":
            if chunks == []:
                passed = True
                actual = "빈 리스트 반환"
            else:
                passed = False
                actual = f"비어있지 않은 리스트 반환 ({len(chunks)}개)"
                root_cause = "빈/공백 파일에서 청크가 반환됨"

        elif exp_type == "list":
            # 기본: 예외 없이 리스트 반환
            if not isinstance(chunks, list):
                passed = False
                actual = f"리스트가 아닌 타입 반환: {type(chunks)}"
                root_cause = "반환 타입 오류"
            else:
                # 추가 검증 조건들
                checks = []

                min_len = expected.get("min_length")
                if min_len is not None and len(chunks) < min_len:
                    checks.append(f"청크 수({len(chunks)}) < 최소({min_len})")

                # chunk_type 검증 (invalid 케이스: block 타입이어야 함)
                exp_chunk_type = expected.get("chunk_type")
                if exp_chunk_type and chunks:
                    wrong_types = [c for c in chunks if c.chunk_type != exp_chunk_type]
                    if wrong_types:
                        checks.append(f"예상 chunk_type={exp_chunk_type}, 실제={wrong_types[0].chunk_type}")

                # 특정 함수 청크 이름 있어야 함
                has_func = expected.get("has_function_chunk_named")
                if has_func:
                    func_names = {c.name for c in chunks if c.chunk_type == "function"}
                    if has_func not in func_names:
                        checks.append(f"함수 청크 '{has_func}' 없음 (실제: {func_names})")

                # 특정 함수 청크 이름 없어야 함
                no_func = expected.get("no_function_chunk_named")
                if no_func:
                    func_names = {c.name for c in chunks if c.chunk_type == "function"}
                    if no_func in func_names:
                        checks.append(f"함수 청크 '{no_func}'가 있으면 안 됨 (있음)")

                # CodeChunk 속성 유효성 검증
                for c in chunks:
                    if not isinstance(c, CodeChunk):
                        checks.append(f"CodeChunk가 아닌 타입: {type(c)}")
                        break
                    if c.start_line < 1:
                        checks.append(f"start_line < 1: {c.start_line}")
                        break
                    if c.end_line < c.start_line:
                        checks.append(f"end_line({c.end_line}) < start_line({c.start_line})")
                        break
                    if c.chunk_type not in {"function", "class", "method", "module", "block"}:
                        checks.append(f"허용되지 않는 chunk_type: {c.chunk_type}")
                        break
                    if not isinstance(c.content, str) or len(c.content) == 0:
                        checks.append(f"content가 비어있거나 문자열이 아님")
                        break
                    if not isinstance(c.file_path, str):
                        checks.append(f"file_path가 문자열이 아님")
                        break

                if checks:
                    passed = False
                    actual = "; ".join(checks)
                    root_cause = checks[0]
                else:
                    passed = True
                    actual = f"정상 리스트 반환 ({len(chunks)}개 청크)"

        else:
            passed = False
            actual = f"알 수 없는 expected.type: {exp_type}"
            root_cause = "테스트 케이스 설계 오류"

    except Exception as e:
        elapsed = time.perf_counter() - start
        passed = False
        actual = f"예외 발생: {type(e).__name__}: {e}"
        error_msg = traceback.format_exc()
        root_cause = f"{type(e).__name__} in chunker.chunk()"

    return {
        "id": tc_id,
        "category": category,
        "file_path": file_path,
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
    """QC 테스트를 배치로 실행하고 리포트를 저장한다.

    Args:
        cases_path: JSONL 테스트 케이스 파일 경로
        report_path: 결과 리포트 JSON 저장 경로
        batch_size: 배치 크기 (메모리 절약)

    Returns:
        요약 딕셔너리
    """
    chunker = ASTChunker()

    total = 0
    passed = 0
    failed = 0
    failures_by_category: dict[str, int] = {}
    top_failures: list[dict] = []
    total_elapsed_ms = 0.0

    report_path.parent.mkdir(parents=True, exist_ok=True)

    # 결과를 스트리밍으로 기록
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
                for tc in batch:
                    result = _run_single_case(chunker, tc)
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
                                "file_path": result["file_path"],
                                "actual": result["actual"],
                                "root_cause": result["root_cause"],
                                "error": result["error"],
                            })

                if total % 1000 == 0:
                    elapsed = time.time() - start_time
                    rate = total / elapsed if elapsed > 0 else 0
                    print(f"  진행: {total:,}건 / 통과: {passed:,} / 실패: {failed:,} ({rate:.0f}건/초)")

                batch = []

        # 마지막 배치
        for tc in batch:
            result = _run_single_case(chunker, tc)
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
                        "file_path": result["file_path"],
                        "actual": result["actual"],
                        "root_cause": result["root_cause"],
                        "error": result["error"],
                    })

    duration_seconds = time.time() - start_time
    pass_rate = (passed / total * 100) if total > 0 else 0.0

    # fix_requests 생성
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
        "target": "src/rag/chunker.py",
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
    parser = argparse.ArgumentParser(description="ASTChunker 모듈 QC 실행기")
    parser.add_argument(
        "--cases",
        default="tests/qc/chunker/test_cases.jsonl",
        help="JSONL 테스트 케이스 파일 경로",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="배치 크기 (메모리 절약)",
    )
    parser.add_argument(
        "--report",
        default="tests/qc/chunker/report.json",
        help="리포트 저장 경로",
    )
    args = parser.parse_args()

    cases_path = Path(args.cases)
    report_path = Path(args.report)

    if not cases_path.exists():
        print(f"오류: 테스트 케이스 파일이 없습니다: {cases_path}")
        print("먼저 generate_module_cases.py를 실행하세요.")
        sys.exit(1)

    summary = run_qc(cases_path, report_path, args.batch_size)

    # 종료 코드: 100% 통과면 0, 아니면 1
    sys.exit(0 if summary["pass_rate"] == 100.0 else 1)


if __name__ == "__main__":
    main()
