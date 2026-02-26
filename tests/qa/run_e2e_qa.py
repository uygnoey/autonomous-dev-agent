"""E2E QA 실행기.

generate_e2e_cases.py로 생성된 100,000건의 E2E 시나리오를 실행하고
결과를 report.json에 저장한다.

지원 시나리오:
- full_pipeline: 파일 → chunker → embedder(mock) → vector_store → search
- integration_search: BM25 검색 / 벡터 검색 통합
- data_consistency: 재청킹 일관성 / remove 후 검색 / clear 후 검색
- performance: 대량 파일 / 고차원 임베딩 / 대량 쿼리
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import traceback
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.core.domain import CodeChunk
from src.rag.chunker import ASTChunker
from src.rag.scorer import BM25Scorer
from src.rag.vector_store import NumpyStore


# ---------------------------------------------------------------------------
# 헬퍼 함수
# ---------------------------------------------------------------------------

def _make_mock_embeddings(chunks: list[CodeChunk], dim: int) -> list[list[float]]:
    """청크별 결정적(deterministic) mock 임베딩을 생성한다.

    실제 API 호출 없이 청크 내용 해시 기반으로 재현 가능한 단위 벡터를 만든다.
    """
    import hashlib

    result = []
    for chunk in chunks:
        h = hashlib.md5(chunk.content.encode()).hexdigest()
        # 해시 값을 seed로 사용하여 결정적 벡터 생성
        seed = int(h[:8], 16)
        vec = []
        state = seed
        for _ in range(dim):
            # LCG 난수 생성
            state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
            val = (state / 0xFFFFFFFF) * 2.0 - 1.0
            vec.append(val)
        # 정규화
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        result.append([x / norm for x in vec])
    return result


# ---------------------------------------------------------------------------
# 시나리오별 실행 함수
# ---------------------------------------------------------------------------

def _run_full_pipeline(tc: dict) -> dict:
    """전체 파이프라인 시나리오를 실행한다."""
    chunker = ASTChunker()
    store = NumpyStore()

    file_path = tc["file_path"]
    content = tc["content"]
    dim = tc["embedding_dim"]
    top_k = tc["top_k"]
    query_vec = tc["query_vec"]
    expected = tc["expected"]

    # 1단계: 청킹
    chunks = chunker.chunk(file_path, content)

    # 빈 파일 케이스 검증
    if expected.get("max_chunks") == 0:
        if len(chunks) == 0:
            return {"status": "pass", "detail": "빈 파일 → 빈 청크 (정상)"}
        else:
            return {
                "status": "fail",
                "detail": f"빈 파일에서 청크 생성됨: {len(chunks)}개",
            }

    # 최소 청크 수 검증
    min_chunks = expected.get("min_chunks", 1)
    if len(chunks) < min_chunks:
        return {
            "status": "fail",
            "detail": f"청크 수 부족: 기대 최소 {min_chunks}, 실제 {len(chunks)}",
        }

    # 2단계: mock 임베딩 생성
    embeddings = _make_mock_embeddings(chunks, dim)

    # 3단계: 벡터 스토어에 추가
    store.add(chunks, embeddings)

    # 4단계: 검색
    results = store.search(query_vec, top_k)

    # 결과 검증
    if expected.get("search_result_type") == "empty_list":
        if results:
            return {
                "status": "fail",
                "detail": f"빈 결과 기대했으나 {len(results)}개 반환",
            }
        return {"status": "pass", "detail": "전체 파이프라인 완료 (빈 결과 정상)"}

    # 일반 검색 결과 검증
    top_k_limit = expected.get("top_k_limit", top_k)
    if len(results) > top_k_limit:
        return {
            "status": "fail",
            "detail": f"top_k 초과: 기대 최대 {top_k_limit}, 실제 {len(results)}",
        }

    # 유사도 내림차순 정렬 검증
    if results:
        sims = [s for _, s in results]
        if sims != sorted(sims, reverse=True):
            return {"status": "fail", "detail": "유사도 내림차순 정렬 위반"}

    return {
        "status": "pass",
        "detail": f"파이프라인 완료: 청크={len(chunks)}, 검색결과={len(results)}",
    }


def _run_integration_search(tc: dict) -> dict:
    """통합 검색 시나리오를 실행한다."""
    sub_type = tc["sub_type"]
    expected = tc["expected"]

    if sub_type == "bm25_search":
        # BM25 검색
        scorer = BM25Scorer()
        documents = tc["documents"]
        query = tc["query"]
        top_k = tc["top_k"]

        if not documents:
            results = []
        else:
            scorer.fit(documents)
            results = scorer.top_k(query, min(top_k, len(documents)))

        if expected.get("result_type") == "empty_list":
            if results:
                return {"status": "fail", "detail": f"빈 결과 기대, {len(results)}개 반환"}
            return {"status": "pass", "detail": "BM25 빈 코퍼스 검색 정상"}

        max_len = expected.get("max_length", top_k)
        if len(results) > max_len:
            return {
                "status": "fail",
                "detail": f"BM25 결과 수 초과: 기대 최대 {max_len}, 실제 {len(results)}",
            }

        return {
            "status": "pass",
            "detail": f"BM25 검색 완료: {len(results)}개 결과",
        }

    elif sub_type == "vector_search":
        # 벡터 검색
        chunker = ASTChunker()
        store = NumpyStore()

        file_path = tc["file_path"]
        content = tc["content"]
        dim = tc["embedding_dim"]
        top_k = tc["top_k"]
        query_vec = tc["query_vec"]

        chunks = chunker.chunk(file_path, content)
        if not chunks:
            return {"status": "pass", "detail": "청크 없음 → 검색 결과 없음"}

        embeddings = _make_mock_embeddings(chunks, dim)
        store.add(chunks, embeddings)
        results = store.search(query_vec, top_k)

        if expected.get("result_type") == "empty_list" and results:
            return {"status": "fail", "detail": f"빈 결과 기대, {len(results)}개 반환"}

        max_len = expected.get("max_length", top_k)
        if len(results) > max_len:
            return {
                "status": "fail",
                "detail": f"결과 수 초과: 기대 최대 {max_len}, 실제 {len(results)}",
            }

        if expected.get("sorted_desc") and results:
            sims = [s for _, s in results]
            if sims != sorted(sims, reverse=True):
                return {"status": "fail", "detail": "유사도 내림차순 정렬 위반"}

        return {
            "status": "pass",
            "detail": f"벡터 검색 완료: {len(results)}개 결과",
        }

    elif sub_type == "empty_corpus_search":
        # 빈 코퍼스 검색
        store = NumpyStore()
        dim = tc.get("embedding_dim", 256)
        query_vec = tc.get("query_vec", [0.1] * dim)
        top_k = tc.get("top_k", 5)
        results = store.search(query_vec, top_k)

        if results:
            return {"status": "fail", "detail": f"빈 스토어 검색 결과 {len(results)}개"}
        return {"status": "pass", "detail": "빈 코퍼스 검색 정상"}

    return {"status": "fail", "detail": f"알 수 없는 sub_type: {sub_type}"}


def _run_data_consistency(tc: dict) -> dict:
    """데이터 일관성 시나리오를 실행한다."""
    sub_type = tc["sub_type"]
    expected = tc["expected"]

    if sub_type == "rechunk_consistency":
        # 동일 파일 두 번 청킹 → 동일 결과
        chunker = ASTChunker()
        file_path = tc["file_path"]
        content = tc["content"]

        chunks1 = chunker.chunk(file_path, content)
        chunks2 = chunker.chunk(file_path, content)

        if expected.get("same_chunk_count"):
            if len(chunks1) != len(chunks2):
                return {
                    "status": "fail",
                    "detail": f"재청킹 결과 불일치: 1차={len(chunks1)}, 2차={len(chunks2)}",
                }

        if expected.get("same_content"):
            for i, (c1, c2) in enumerate(zip(chunks1, chunks2)):
                if c1.content != c2.content:
                    return {
                        "status": "fail",
                        "detail": f"청크 {i} 내용 불일치",
                    }

        return {
            "status": "pass",
            "detail": f"재청킹 일관성 확인: {len(chunks1)}개 청크",
        }

    elif sub_type == "remove_search":
        # 파일 추가 후 제거, 검색 결과에 미포함 확인
        chunker = ASTChunker()
        store = NumpyStore()

        files = tc["files"]
        remove_path = tc["remove_path"]
        dim = tc["embedding_dim"]
        top_k = tc["top_k"]
        query_vec = tc["query_vec"]

        # 모든 파일 청킹 및 추가
        all_chunks: list[CodeChunk] = []
        for f in files:
            chunks = chunker.chunk(f["path"], f["content"])
            all_chunks.extend(chunks)

        if all_chunks:
            embeddings = _make_mock_embeddings(all_chunks, dim)
            store.add(all_chunks, embeddings)

        # 파일 제거
        store.remove(remove_path)

        # 검색
        results = store.search(query_vec, top_k)

        # 삭제된 파일 청크 미포함 검증
        for chunk, _ in results:
            if chunk.file_path == remove_path:
                return {
                    "status": "fail",
                    "detail": f"삭제된 파일({remove_path}) 청크가 검색 결과에 포함",
                }

        return {
            "status": "pass",
            "detail": f"remove 후 검색 정상: {len(results)}개 결과, 삭제 파일 미포함",
        }

    elif sub_type == "clear_search":
        # 모든 청크 추가 후 clear, 검색 결과 빈 리스트
        chunker = ASTChunker()
        store = NumpyStore()

        files = tc["files"]
        dim = tc["embedding_dim"]
        query_vec = tc["query_vec"]
        top_k = tc["top_k"]

        all_chunks: list[CodeChunk] = []
        for f in files:
            chunks = chunker.chunk(f["path"], f["content"])
            all_chunks.extend(chunks)

        if all_chunks:
            embeddings = _make_mock_embeddings(all_chunks, dim)
            store.add(all_chunks, embeddings)

        # clear 후 검색
        store.clear()
        results = store.search(query_vec, top_k)

        if results:
            return {
                "status": "fail",
                "detail": f"clear 후 검색 결과 {len(results)}개 (빈 리스트 기대)",
            }

        return {"status": "pass", "detail": "clear 후 검색 결과 없음 (정상)"}

    return {"status": "fail", "detail": f"알 수 없는 sub_type: {sub_type}"}


def _run_performance(tc: dict) -> dict:
    """성능 시나리오를 실행한다."""
    sub_type = tc["sub_type"]
    expected = tc["expected"]

    if sub_type in ("bulk_files", "high_dim_embedding"):
        chunker = ASTChunker()
        store = NumpyStore()

        # 단일 파일 또는 다중 파일 처리
        if "files" in tc:
            files = tc["files"]
        else:
            files = [{"path": tc["file_path"], "content": tc["content"]}]

        dim = tc["embedding_dim"]
        top_k = tc["top_k"]
        query_vec = tc["query_vec"]

        all_chunks: list[CodeChunk] = []
        for f in files:
            chunks = chunker.chunk(f["path"], f["content"])
            all_chunks.extend(chunks)

        if not all_chunks:
            return {"status": "pass", "detail": "청크 없음 → 검색 결과 없음"}

        embeddings = _make_mock_embeddings(all_chunks, dim)
        store.add(all_chunks, embeddings)
        results = store.search(query_vec, top_k)

        max_len = expected.get("max_length", len(all_chunks))
        if len(results) > max_len:
            return {
                "status": "fail",
                "detail": f"결과 수 초과: {len(results)} > {max_len}",
            }

        return {
            "status": "pass",
            "detail": f"성능 테스트 완료: 파일={len(files)}, 청크={len(all_chunks)}, 결과={len(results)}",
        }

    elif sub_type == "bulk_queries":
        chunker = ASTChunker()
        store = NumpyStore()

        file_path = tc["file_path"]
        content = tc["content"]
        dim = tc["embedding_dim"]
        top_k = tc["top_k"]
        queries = tc["queries"]

        chunks = chunker.chunk(file_path, content)
        if not chunks:
            return {"status": "pass", "detail": "청크 없음"}

        embeddings = _make_mock_embeddings(chunks, dim)
        store.add(chunks, embeddings)

        # 다중 쿼리 실행
        query_count = expected.get("query_count", len(queries))
        results_list = []
        for q in queries[:query_count]:
            res = store.search(q, top_k)
            results_list.append(len(res))

        return {
            "status": "pass",
            "detail": f"대량 검색 완료: {len(queries)}쿼리, 평균 결과={sum(results_list)/len(results_list):.1f}개",
        }

    return {"status": "fail", "detail": f"알 수 없는 sub_type: {sub_type}"}


# ---------------------------------------------------------------------------
# 단일 케이스 실행 디스패처
# ---------------------------------------------------------------------------

def _run_single_case(tc: dict) -> dict:
    """단일 E2E 테스트 케이스를 실행하고 결과를 반환한다."""
    tc_id = tc["id"]
    scenario = tc["scenario"]

    start = time.perf_counter()
    passed = False
    actual = None
    error_msg = None
    root_cause = None

    try:
        if scenario == "full_pipeline":
            outcome = _run_full_pipeline(tc)
        elif scenario == "integration_search":
            outcome = _run_integration_search(tc)
        elif scenario == "data_consistency":
            outcome = _run_data_consistency(tc)
        elif scenario == "performance":
            outcome = _run_performance(tc)
        else:
            outcome = {"status": "fail", "detail": f"알 수 없는 시나리오: {scenario}"}

        passed = outcome["status"] == "pass"
        actual = outcome["detail"]
        if not passed:
            root_cause = actual

    except Exception as e:
        passed = False
        actual = f"예외 발생: {type(e).__name__}: {e}"
        error_msg = traceback.format_exc()
        root_cause = f"{type(e).__name__} in {scenario}"

    elapsed_ms = round((time.perf_counter() - start) * 1000, 3)

    return {
        "id": tc_id,
        "scenario": scenario,
        "sub_type": tc.get("sub_type", ""),
        "passed": passed,
        "actual": actual,
        "error": error_msg,
        "root_cause": root_cause,
        "elapsed_ms": elapsed_ms,
    }


# ---------------------------------------------------------------------------
# QA 실행기
# ---------------------------------------------------------------------------

def run_e2e_qa(
    cases_path: Path,
    report_path: Path,
    batch_size: int = 5000,
) -> dict:
    """E2E QA를 배치로 실행하고 리포트를 저장한다."""
    total = 0
    passed_count = 0
    failed_count = 0
    failures_by_scenario: dict[str, int] = {}
    failures_by_subtype: dict[str, int] = {}
    top_failures: list[dict] = []
    total_elapsed_ms = 0.0
    elapsed_by_scenario: dict[str, float] = {}

    report_path.parent.mkdir(parents=True, exist_ok=True)
    results_path = report_path.parent / "results.jsonl"

    print(f"E2E QA 실행 시작: {cases_path}")
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

                scen = result["scenario"]
                elapsed_by_scenario[scen] = (
                    elapsed_by_scenario.get(scen, 0.0) + result["elapsed_ms"]
                )

                if result["passed"]:
                    passed_count += 1
                else:
                    failed_count += 1
                    failures_by_scenario[scen] = failures_by_scenario.get(scen, 0) + 1
                    sub = result.get("sub_type", "")
                    failures_by_subtype[sub] = failures_by_subtype.get(sub, 0) + 1
                    if len(top_failures) < 100:
                        top_failures.append({
                            "id": result["id"],
                            "scenario": scen,
                            "sub_type": sub,
                            "actual": result["actual"],
                            "root_cause": result["root_cause"],
                        })

            if total % 5000 == 0:
                elapsed = time.time() - wall_start
                rate = total / elapsed if elapsed > 0 else 0
                pass_rate = (passed_count / total * 100) if total > 0 else 0
                print(
                    f"  진행: {total:,}건 / 통과: {passed_count:,} / 실패: {failed_count:,} "
                    f"/ 통과율: {pass_rate:.1f}% ({rate:.0f}건/초)"
                )

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

    # 시나리오별 통과/실패 통계
    scenario_stats: dict[str, dict] = {}
    for scen in ["full_pipeline", "integration_search", "data_consistency", "performance"]:
        fail_cnt = failures_by_scenario.get(scen, 0)
        # 시나리오별 총 처리 건수 계산 (results에서 집계)
        scenario_stats[scen] = {
            "failed": fail_cnt,
            "elapsed_ms": round(elapsed_by_scenario.get(scen, 0.0), 1),
        }

    fix_requests = []
    for scen, cnt in failures_by_scenario.items():
        samples = [f for f in top_failures if f["scenario"] == scen][:3]
        fix_requests.append({
            "scenario": scen,
            "failed_cases_count": cnt,
            "sample_failures": samples,
        })

    summary = {
        "test_type": "e2e_qa",
        "total_cases": total,
        "passed": passed_count,
        "failed": failed_count,
        "pass_rate": round(pass_rate, 4),
        "duration_seconds": round(duration, 2),
        "avg_case_ms": round(total_elapsed_ms / total, 3) if total > 0 else 0,
        "failures_by_scenario": failures_by_scenario,
        "failures_by_subtype": failures_by_subtype,
        "scenario_stats": scenario_stats,
        "top_failures": top_failures[:50],
        "fix_requests": fix_requests,
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\nE2E QA 완료!")
    print(f"  총 케이스: {total:,}건")
    print(f"  통과: {passed_count:,}건")
    print(f"  실패: {failed_count:,}건")
    print(f"  통과율: {pass_rate:.2f}%")
    print(f"  소요시간: {duration:.1f}초")
    print(f"  리포트: {report_path}")

    return summary


def main() -> None:
    """CLI 진입점."""
    parser = argparse.ArgumentParser(description="E2E QA 실행기")
    parser.add_argument(
        "--cases",
        default="tests/qa/test_cases.jsonl",
        help="테스트 케이스 JSONL 파일 경로",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5000,
        help="배치 크기 (기본: 5,000)",
    )
    parser.add_argument(
        "--report",
        default="tests/qa/report.json",
        help="결과 리포트 JSON 파일 경로",
    )
    args = parser.parse_args()

    cases_path = Path(args.cases)
    report_path = Path(args.report)

    if not cases_path.exists():
        print(f"오류: 테스트 케이스 파일이 없습니다: {cases_path}")
        print("먼저 generate_e2e_cases.py를 실행하세요.")
        sys.exit(1)

    summary = run_e2e_qa(cases_path, report_path, args.batch_size)
    sys.exit(0 if summary["pass_rate"] >= 99.0 else 1)


if __name__ == "__main__":
    main()
