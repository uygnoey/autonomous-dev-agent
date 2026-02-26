"""HybridSearcher 모듈 QC 실행기.

JSONL 테스트 케이스를 배치(1,000건)로 읽어서 실행하고,
결과를 report.json에 저장한다.

케이스 필드:
- query: 검색 쿼리
- top_k: 반환할 최대 결과 수
- chunks: CodeChunk 직렬화 목록 (BM25 fit 코퍼스)
- embeddings: NumpyStore에 저장할 임베딩 벡터
- bm25_weight / vector_weight: HybridSearcher 가중치
- embedder_available: AnthropicEmbedder.is_available mock 값
- query_embedding: 쿼리 임베딩 (None이면 embed()가 예외 발생)
- scorer_unfitted: True이면 BM25Scorer.fit() 호출 안 함
- expected.type: "search_result" | "empty_list" | "no_exception"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import traceback
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.core.domain import CodeChunk
from src.rag.hybrid_search import HybridSearcher
from src.rag.scorer import BM25Scorer
from src.rag.vector_store import NumpyStore


# ------------------------------------------------------------------
# 헬퍼
# ------------------------------------------------------------------

def _build_chunks(raw: list[dict]) -> list[CodeChunk]:
    """직렬화 딕셔너리 목록 → CodeChunk 목록."""
    return [
        CodeChunk(
            file_path=c["file_path"],
            content=c["content"],
            start_line=c["start_line"],
            end_line=c["end_line"],
            chunk_type=c.get("chunk_type", "block"),
            name=c.get("name"),
        )
        for c in raw
    ]


def _make_mock_embedder(
    is_available: bool,
    query_embedding: list[float] | None,
) -> MagicMock:
    """AnthropicEmbedder mock 생성.

    query_embedding이 None이면 embed() 호출 시 RuntimeError를 발생시킨다.
    """
    mock = MagicMock()
    mock.is_available = is_available

    if query_embedding is None:
        mock.embed = AsyncMock(side_effect=RuntimeError("embed() mock 예외"))
    else:
        mock.embed = AsyncMock(return_value=[query_embedding] if query_embedding else [])

    return mock


# ------------------------------------------------------------------
# 단일 케이스 실행
# ------------------------------------------------------------------

def _run_single_case(tc: dict) -> dict:
    """단일 테스트 케이스를 실행하고 결과 딕셔너리를 반환한다."""
    tc_id: str = tc["id"]
    category: str = tc["category"]
    expected: dict = tc["expected"]

    query: str = tc.get("query", "")
    top_k: int = tc.get("top_k", 0)
    raw_chunks: list[dict] = tc.get("chunks") or []
    raw_embeddings: list[list[float]] = tc.get("embeddings") or []
    bm25_weight: float = tc.get("bm25_weight", 0.6)
    vector_weight: float = tc.get("vector_weight", 0.4)
    embedder_available: bool = tc.get("embedder_available", False)
    query_embedding = tc.get("query_embedding")  # None | list[float]
    scorer_unfitted: bool = tc.get("scorer_unfitted", False)

    start = time.perf_counter()
    passed = False
    actual = None
    error_msg = None
    root_cause = None

    try:
        chunks = _build_chunks(raw_chunks)

        # BM25Scorer 준비
        scorer = BM25Scorer()
        if not scorer_unfitted and chunks:
            docs = [c.content for c in chunks]
            scorer.fit(docs)

        # NumpyStore 준비
        store = NumpyStore()
        if chunks and raw_embeddings:
            store.add(chunks, raw_embeddings)

        # Embedder mock
        mock_embedder = _make_mock_embedder(embedder_available, query_embedding)

        # HybridSearcher 인스턴스
        searcher = HybridSearcher(
            scorer=scorer,
            store=store,
            embedder=mock_embedder,
            bm25_weight=bm25_weight,
            vector_weight=vector_weight,
        )

        # 비동기 search 실행
        result = asyncio.run(searcher.search(query, top_k, chunks))

        exp_type = expected.get("type", "no_exception")

        if exp_type == "empty_list":
            if result == []:
                passed = True
                actual = "빈 리스트 반환 (정상)"
            else:
                passed = False
                actual = f"빈 리스트 아님: 길이={len(result)}"
                root_cause = actual

        elif exp_type == "no_exception":
            # 예외 없이 완료되면 통과
            passed = True
            actual = f"예외 없이 완료: {len(result)}개 반환"

        elif exp_type == "search_result":
            checks: list[str] = []

            max_len = expected.get("max_length")
            if max_len is not None and len(result) > max_len:
                checks.append(f"최대 길이 초과: max={max_len}, 실제={len(result)}")

            if expected.get("sorted_desc") and len(result) > 1:
                sims = [s for _, s in result]
                if sims != sorted(sims, reverse=True):
                    checks.append("스코어 내림차순 정렬 위반")

            for chunk, score in result:
                if not isinstance(chunk, CodeChunk):
                    checks.append(f"결과 원소가 CodeChunk 아님: {type(chunk)}")
                    break
                if not isinstance(score, float):
                    checks.append(f"스코어가 float 아님: {type(score)}")
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
        root_cause = f"{type(e).__name__} in HybridSearcher.search()"

    elapsed_ms = round((time.perf_counter() - start) * 1000, 3)

    return {
        "id": tc_id,
        "category": category,
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
        "target": "src/rag/hybrid_search.py",
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
    parser = argparse.ArgumentParser(description="HybridSearcher 모듈 QC 실행기")
    parser.add_argument(
        "--cases",
        default="tests/qc/hybrid_search/test_cases.jsonl",
        help="테스트 케이스 JSONL 파일 경로",
    )
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument(
        "--report",
        default="tests/qc/hybrid_search/report.json",
        help="결과 리포트 JSON 파일 경로",
    )
    args = parser.parse_args()

    cases_path = Path(args.cases)
    report_path = Path(args.report)

    if not cases_path.exists():
        print(f"오류: 테스트 케이스 파일이 없습니다: {cases_path}")
        print("먼저 generate_hybrid_search_cases.py를 실행하세요.")
        sys.exit(1)

    summary = run_qc(cases_path, report_path, args.batch_size)
    sys.exit(0 if summary["pass_rate"] == 100.0 else 1)


if __name__ == "__main__":
    main()
