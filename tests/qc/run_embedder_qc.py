"""AnthropicEmbedder 모듈 QC 실행기.

JSONL 테스트 케이스를 배치(1,000건)로 읽어서 실행하고,
결과를 report.json에 저장한다.

embed()는 async + 실제 API 호출이므로:
- asyncio.run()으로 실행
- httpx.AsyncClient를 unittest.mock으로 모킹
- api_scenario에 따라 성공/실패 응답을 시뮬레이션
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import traceback
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

import httpx

from src.rag.embedder import AnthropicEmbedder

# 테스트용 임베딩 차원 (실제 voyage-3은 1024, 테스트는 4로 축소)
_TEST_DIM = 4


def _make_success_response(texts: list[str]) -> MagicMock:
    """성공 응답 mock을 생성한다."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {"index": i, "embedding": [float(i % 100) / 100.0] * _TEST_DIM}
            for i in range(len(texts))
        ]
    }
    mock_resp.raise_for_status = MagicMock()  # 예외 없음
    return mock_resp


def _make_4xx_response(status: int = 401) -> MagicMock:
    """4xx 오류 응답 mock을 생성한다."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = status
    mock_resp.headers = {}

    def _raise():
        raise httpx.HTTPStatusError(
            f"HTTP {status}",
            request=MagicMock(),
            response=mock_resp,
        )

    mock_resp.raise_for_status = _raise
    return mock_resp


def _make_5xx_response(status: int = 500) -> MagicMock:
    """5xx 오류 응답 mock을 생성한다."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = status
    mock_resp.headers = {}

    def _raise():
        raise httpx.HTTPStatusError(
            f"HTTP {status}",
            request=MagicMock(),
            response=mock_resp,
        )

    mock_resp.raise_for_status = _raise
    return mock_resp


async def _run_embed_with_mock(
    texts: list[str],
    api_scenario: str,
    cache_path: str,
) -> list[list[float]]:
    """api_scenario에 맞는 mock을 적용하여 embed()를 실행한다.

    Args:
        texts: 임베딩할 텍스트 목록
        api_scenario: "success" | "api_key_missing" | "http_4xx" | "http_5xx" | "network_error"
        cache_path: 테스트용 임시 캐시 경로

    Returns:
        embed() 반환값
    """
    env_patch = {"VOYAGE_API_KEY": "test-key-qc"}

    if api_scenario == "api_key_missing":
        # API 키 없음
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VOYAGE_API_KEY", None)
            os.environ.pop("ANTHROPIC_API_KEY", None)
            embedder = AnthropicEmbedder(cache_path=cache_path)
            return await embedder.embed(texts)

    # API 키 있는 경우
    with patch.dict(os.environ, env_patch, clear=False):
        embedder = AnthropicEmbedder(cache_path=cache_path)

        if api_scenario == "success":
            # 성공 시뮬레이션: 배치별로 실제 텍스트 수에 맞는 응답 생성
            call_count = 0
            original_call = embedder._call_voyage_api

            async def mock_call(batch_texts: list[str]) -> list[list[float]]:
                nonlocal call_count
                call_count += 1
                return [
                    [float(j % 100) / 100.0] * _TEST_DIM
                    for j in range(len(batch_texts))
                ]

            embedder._call_voyage_api = mock_call
            return await embedder.embed(texts)

        elif api_scenario == "http_4xx":
            # 4xx 오류: 재시도 없이 None 반환
            async def mock_call_4xx(batch_texts: list[str]) -> list[list[float]]:
                mock_resp = _make_4xx_response(401)
                raise httpx.HTTPStatusError(
                    "HTTP 401",
                    request=MagicMock(),
                    response=mock_resp,
                )

            embedder._call_voyage_api = mock_call_4xx
            return await embedder.embed(texts)

        elif api_scenario == "http_5xx":
            # 5xx 오류: 재시도 후 None 반환 (sleep 0으로 대체하여 빠르게 실행)
            async def mock_call_5xx(batch_texts: list[str]) -> list[list[float]]:
                mock_resp = _make_5xx_response(500)
                raise httpx.HTTPStatusError(
                    "HTTP 500",
                    request=MagicMock(),
                    response=mock_resp,
                )

            embedder._call_voyage_api = mock_call_5xx
            # asyncio.sleep을 no-op으로 대체 (실제 대기 제거)
            import src.rag.embedder as _embedder_mod
            original_sleep = _embedder_mod.asyncio.sleep
            async def _noop_sleep(delay: float) -> None:
                pass
            _embedder_mod.asyncio.sleep = _noop_sleep
            try:
                return await embedder.embed(texts)
            finally:
                _embedder_mod.asyncio.sleep = original_sleep

        elif api_scenario == "network_error":
            # 네트워크 오류: 재시도 후 None 반환 (sleep 제거)
            async def mock_call_net(batch_texts: list[str]) -> list[list[float]]:
                raise httpx.ConnectError("Connection refused")

            embedder._call_voyage_api = mock_call_net
            import src.rag.embedder as _embedder_mod
            original_sleep = _embedder_mod.asyncio.sleep
            async def _noop_sleep2(delay: float) -> None:
                pass
            _embedder_mod.asyncio.sleep = _noop_sleep2
            try:
                return await embedder.embed(texts)
            finally:
                _embedder_mod.asyncio.sleep = original_sleep

        else:
            # 알 수 없는 시나리오 — success로 폴백
            async def mock_call_default(batch_texts: list[str]) -> list[list[float]]:
                return [[0.0] * _TEST_DIM for _ in batch_texts]

            embedder._call_voyage_api = mock_call_default
            return await embedder.embed(texts)


def _run_single_case(tc: dict, tmp_cache_path: str) -> dict:
    """단일 테스트 케이스를 실행하고 결과를 반환한다."""
    import tempfile

    tc_id = tc["id"]
    category = tc["category"]
    texts = tc.get("texts") or []
    api_scenario = tc.get("api_scenario", "success")
    expected = tc["expected"]

    start = time.perf_counter()
    passed = False
    actual = None
    error_msg = None
    root_cause = None

    # 오류 시나리오(캐시 히트 시 빈 리스트 아닌 정상 벡터 반환 가능)는 독립 캐시 사용
    _ISOLATED_SCENARIOS = {"api_key_missing", "http_4xx", "http_5xx", "network_error"}

    try:
        if api_scenario in _ISOLATED_SCENARIOS:
            with tempfile.TemporaryDirectory() as fresh_dir:
                fresh_cache = str(Path(fresh_dir) / "embeddings.json")
                result = asyncio.run(
                    _run_embed_with_mock(texts, api_scenario, fresh_cache)
                )
        else:
            result = asyncio.run(
                _run_embed_with_mock(texts, api_scenario, tmp_cache_path)
            )
        elapsed = time.perf_counter() - start

        exp_type = expected.get("type", "list_of_vectors")
        checks = []

        if exp_type == "empty_list":
            if result != []:
                checks.append(f"빈 리스트가 아님: 길이={len(result)}")

        elif exp_type == "list_of_vectors":
            if not isinstance(result, list):
                checks.append(f"list가 아닌 타입: {type(result)}")
            else:
                exp_len = expected.get("length")
                if exp_len is not None and len(result) != exp_len:
                    checks.append(f"길이 불일치: 기대={exp_len}, 실제={len(result)}")

                # 각 원소가 list[float]인지 검증
                for i, vec in enumerate(result):
                    if not isinstance(vec, list):
                        checks.append(f"원소[{i}]가 list 아님: {type(vec)}")
                        break
                    if len(vec) == 0:
                        checks.append(f"원소[{i}]가 빈 벡터")
                        break
                    if not all(isinstance(v, float) for v in vec):
                        checks.append(f"원소[{i}] 비float 값 포함")
                        break

        else:  # "list" — no_exception만 확인
            pass

        if checks:
            passed = False
            actual = "; ".join(checks)
            root_cause = checks[0]
        else:
            passed = True
            actual = f"정상: {type(result).__name__}({len(result)}개)"

    except Exception as e:
        elapsed = time.perf_counter() - start
        passed = False
        actual = f"예외 발생: {type(e).__name__}: {e}"
        error_msg = traceback.format_exc()
        root_cause = f"{type(e).__name__} in AnthropicEmbedder.embed()"

    return {
        "id": tc_id,
        "category": category,
        "api_scenario": api_scenario,
        "texts_count": len(texts),
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
    import tempfile

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
        tempfile.TemporaryDirectory() as tmp_dir,
    ):
        tmp_cache = str(Path(tmp_dir) / "embeddings.json")
        batch = []

        for line in cases_f:
            line = line.strip()
            if not line:
                continue
            tc = json.loads(line)
            batch.append(tc)

            if len(batch) >= batch_size:
                for item in batch:
                    result = _run_single_case(item, tmp_cache)
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
                                "api_scenario": result["api_scenario"],
                                "texts_count": result["texts_count"],
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
            result = _run_single_case(item, tmp_cache)
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
                        "api_scenario": result["api_scenario"],
                        "texts_count": result["texts_count"],
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
        "target": "src/rag/embedder.py",
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
    parser = argparse.ArgumentParser(description="AnthropicEmbedder 모듈 QC 실행기")
    parser.add_argument("--cases", default="tests/qc/embedder/test_cases.jsonl")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--report", default="tests/qc/embedder/report.json")
    args = parser.parse_args()

    cases_path = Path(args.cases)
    report_path = Path(args.report)

    if not cases_path.exists():
        print(f"오류: 테스트 케이스 파일이 없습니다: {cases_path}")
        print("먼저 generate_embedder_cases.py를 실행하세요.")
        sys.exit(1)

    summary = run_qc(cases_path, report_path, args.batch_size)
    sys.exit(0 if summary["pass_rate"] == 100.0 else 1)


if __name__ == "__main__":
    main()
