"""QC 결과 요약기.

report.json을 읽어서 사람이 읽기 쉬운 요약을 출력하고,
실패 케이스가 있으면 fix_requests를 출력한다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def summarize(report_path: Path) -> dict:
    """리포트를 읽어 요약을 출력한다.

    Args:
        report_path: report.json 파일 경로

    Returns:
        리포트 딕셔너리
    """
    if not report_path.exists():
        print(f"오류: 리포트 파일이 없습니다: {report_path}")
        sys.exit(1)

    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    # 헤더
    print("=" * 60)
    print("ASTChunker 모듈 QC 결과 요약")
    print("=" * 60)
    print(f"대상 모듈:  {report.get('target', 'unknown')}")
    print(f"총 케이스:  {report.get('total_cases', 0):,}건")
    print(f"통과:       {report.get('passed', 0):,}건")
    print(f"실패:       {report.get('failed', 0):,}건")
    print(f"통과율:     {report.get('pass_rate', 0):.2f}%")
    print(f"소요시간:   {report.get('duration_seconds', 0):.1f}초")
    print(f"평균 케이스: {report.get('avg_case_ms', 0):.3f}ms")
    print()

    # 카테고리별 실패
    failures_by_cat = report.get("failures_by_category", {})
    if failures_by_cat:
        print("카테고리별 실패:")
        for cat, cnt in sorted(failures_by_cat.items(), key=lambda x: -x[1]):
            print(f"  {cat:12s}: {cnt:,}건")
        print()

    # 상위 실패 케이스
    top_failures = report.get("top_failures", [])
    if top_failures:
        print(f"상위 실패 케이스 (최대 20건):")
        print("-" * 60)
        for f in top_failures[:20]:
            print(f"  ID:         {f.get('id', 'unknown')}")
            print(f"  카테고리:   {f.get('category', 'unknown')}")
            print(f"  파일:       {f.get('file_path', 'unknown')}")
            print(f"  실제 결과:  {f.get('actual', 'unknown')}")
            if f.get("root_cause"):
                print(f"  원인:       {f.get('root_cause')}")
            if f.get("error"):
                # 오류 메시지 첫 3줄만
                error_lines = f["error"].strip().split("\n")
                print(f"  오류:       {error_lines[-1]}")
            print()

    # fix_requests
    fix_requests = report.get("fix_requests", [])
    if fix_requests:
        print("수정 요청 (coder 에이전트 전달용):")
        print("=" * 60)
        print("[QC 테스트 실패 수정 요청]")
        print()
        print(f"대상: src/rag/chunker.py")
        print(f"테스트 타입: Module QC")
        print(f"전체: {report.get('total_cases', 0):,}건 / 통과: {report.get('passed', 0):,}건 / 실패: {report.get('failed', 0):,}건")
        print()
        print("수정이 필요한 항목:")
        print()
        for i, req in enumerate(fix_requests, 1):
            print(f"{i}. [{req.get('category', 'unknown')}] {req.get('failed_cases_count', 0):,}건 실패")
            for sample in req.get("sample_failures", [])[:2]:
                print(f"   - 케이스: {sample.get('id', 'unknown')}")
                print(f"     실제: {sample.get('actual', 'unknown')}")
                if sample.get("root_cause"):
                    print(f"     원인: {sample.get('root_cause')}")
            print()
        print()
        print("수정 후 반드시 다음을 실행하여 확인:")
        print("  pytest tests/ -v")
        print("  python tests/qc/run_module_qc.py --cases tests/qc/chunker/test_cases.jsonl")

    # 최종 판정
    print()
    print("=" * 60)
    pass_rate = report.get("pass_rate", 0)
    if pass_rate == 100.0:
        print("결과: PASS — 모든 케이스 통과 (100%)")
        print("QC 완료. 다음 모듈 작업을 진행하세요.")
    else:
        print(f"결과: FAIL — 통과율 {pass_rate:.2f}% (목표: 100%)")
        print("coder 에이전트에 수정 요청 후 재실행 필요.")
    print("=" * 60)

    return report


def main() -> None:
    """CLI 진입점."""
    parser = argparse.ArgumentParser(description="QC 결과 요약기")
    parser.add_argument(
        "report",
        nargs="?",
        default="tests/qc/chunker/report.json",
        help="리포트 JSON 파일 경로",
    )
    args = parser.parse_args()

    report = summarize(Path(args.report))

    pass_rate = report.get("pass_rate", 0)
    sys.exit(0 if pass_rate == 100.0 else 1)


if __name__ == "__main__":
    main()
