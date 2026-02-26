"""E2E QA 테스트 케이스 생성기.

100,000건의 E2E 시나리오를 JSONL 형식으로 생성한다.

시나리오별 비율:
- full_pipeline:        40,000건 (40%) — 파일 → chunker → embedder(mock) → vector_store → search
- integration_search:  30,000건 (30%) — chunker + scorer, chunker + embedder + vector_store
- data_consistency:    20,000건 (20%) — 동일 파일 재청킹, 캐시 히트, remove 후 검색
- performance:         10,000건 (10%) — 대량 파일 처리, 고차원 임베딩, 대량 검색
"""

from __future__ import annotations

import argparse
import json
import math
import random
import textwrap
from pathlib import Path


# ---------------------------------------------------------------------------
# 헬퍼 함수
# ---------------------------------------------------------------------------

def _rand_vec(dim: int, seed_offset: int = 0) -> list[float]:
    """재현 가능한 단위 벡터를 생성한다."""
    v = [random.gauss(0, 1) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def _zero_vec(dim: int) -> list[float]:
    """영벡터를 생성한다."""
    return [0.0] * dim


def _make_python_content(func_count: int, class_count: int = 0) -> str:
    """테스트용 Python 소스 코드를 생성한다."""
    lines = ['"""테스트 모듈."""', ""]
    for i in range(func_count):
        lines += [
            f"def func_{i}(x: int, y: int) -> int:",
            f'    """함수 {i}."""',
            f"    result = x + y + {i}",
            f"    return result",
            "",
        ]
    for i in range(class_count):
        lines += [
            f"class MyClass{i}:",
            f'    """클래스 {i}."""',
            f"",
            f"    def __init__(self) -> None:",
            f"        self.value = {i}",
            f"",
            f"    def get_value(self) -> int:",
            f"        return self.value",
            "",
        ]
    return "\n".join(lines)


def _make_non_python_content(line_count: int, lang: str = "js") -> str:
    """테스트용 비Python 소스 코드를 생성한다."""
    if lang == "js":
        lines = [f"// 라인 {i + 1}" for i in range(line_count)]
        lines.insert(0, "// JavaScript 테스트 파일")
    elif lang == "go":
        lines = [f"// 라인 {i + 1}" for i in range(line_count)]
        lines.insert(0, "package main")
    else:
        lines = [f"# 라인 {i + 1}" for i in range(line_count)]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 시나리오별 케이스 생성
# ---------------------------------------------------------------------------

def _gen_full_pipeline_cases(count: int, base_id: int) -> list[dict]:
    """전체 파이프라인 E2E 케이스를 생성한다.

    파일 → chunker → embedder(mock) → vector_store → search 전체 흐름 검증.
    """
    cases: list[dict] = []
    random.seed(100)
    dims = [256, 512, 1024]
    top_ks = [1, 3, 5, 10]

    # 1) Python 파일 전체 파이프라인 (60%)
    for i in range(int(count * 0.60)):
        func_count = random.randint(1, 10)
        class_count = random.randint(0, 3)
        dim = random.choice(dims)
        top_k = random.choice(top_ks)
        content = _make_python_content(func_count, class_count)
        file_path = f"src/module_{i % 50}.py"

        cases.append({
            "id": f"TC-E2E-{base_id + len(cases):06d}",
            "scenario": "full_pipeline",
            "sub_type": "python_pipeline",
            "description": f"Python {func_count}함수 {class_count}클래스 → 청킹 → 임베딩(mock) → 검색",
            "file_path": file_path,
            "content": content,
            "embedding_dim": dim,
            "top_k": top_k,
            "query_vec": _rand_vec(dim),
            "expected": {
                "min_chunks": 1,
                "search_result_type": "list",
                "top_k_limit": top_k,
            },
        })

    # 2) 비Python 파일 파이프라인 (25%)
    langs = ["js", "go", "md"]
    for i in range(int(count * 0.25)):
        lang = random.choice(langs)
        ext = {"js": ".js", "go": ".go", "md": ".md"}[lang]
        line_count = random.randint(30, 200)
        dim = random.choice(dims)
        top_k = random.choice(top_ks)
        content = _make_non_python_content(line_count, lang)
        file_path = f"src/file_{i % 30}{ext}"

        cases.append({
            "id": f"TC-E2E-{base_id + len(cases):06d}",
            "scenario": "full_pipeline",
            "sub_type": "non_python_pipeline",
            "description": f"{lang.upper()} {line_count}줄 → 청킹(fallback) → 임베딩(mock) → 검색",
            "file_path": file_path,
            "content": content,
            "embedding_dim": dim,
            "top_k": top_k,
            "query_vec": _rand_vec(dim),
            "expected": {
                "min_chunks": 1,
                "search_result_type": "list",
                "top_k_limit": top_k,
            },
        })

    # 3) 빈 파일 파이프라인 (5%)
    for i in range(int(count * 0.05)):
        dim = random.choice(dims)
        cases.append({
            "id": f"TC-E2E-{base_id + len(cases):06d}",
            "scenario": "full_pipeline",
            "sub_type": "empty_file_pipeline",
            "description": "빈 파일 → 청킹 → 빈 결과",
            "file_path": f"src/empty_{i}.py",
            "content": "",
            "embedding_dim": dim,
            "top_k": 5,
            "query_vec": _rand_vec(dim),
            "expected": {
                "min_chunks": 0,
                "max_chunks": 0,
                "search_result_type": "empty_list",
            },
        })

    # 나머지 채우기 (다양한 파이프라인)
    while len(cases) < count:
        func_count = random.randint(1, 5)
        dim = random.choice(dims)
        top_k = random.randint(1, 10)
        content = _make_python_content(func_count)
        file_path = f"src/extra_{len(cases)}.py"
        cases.append({
            "id": f"TC-E2E-{base_id + len(cases):06d}",
            "scenario": "full_pipeline",
            "sub_type": "python_pipeline",
            "description": f"Python {func_count}함수 파이프라인 (추가)",
            "file_path": file_path,
            "content": content,
            "embedding_dim": dim,
            "top_k": top_k,
            "query_vec": _rand_vec(dim),
            "expected": {
                "min_chunks": 1,
                "search_result_type": "list",
                "top_k_limit": top_k,
            },
        })

    return cases[:count]


def _gen_integration_search_cases(count: int, base_id: int) -> list[dict]:
    """통합 검색 E2E 케이스를 생성한다.

    chunker + scorer (BM25), chunker + embedder + vector_store 통합 검증.
    """
    cases: list[dict] = []
    random.seed(200)
    dims = [256, 512]
    top_ks = [3, 5, 10]

    # 1) BM25 텍스트 검색 (40%)
    queries_pool = [
        "def authenticate",
        "class UserService",
        "import numpy",
        "return result",
        "async def fetch",
        "configuration settings",
        "error handling",
        "database connection",
        "api endpoint",
        "unit test",
    ]
    for i in range(int(count * 0.40)):
        doc_count = random.randint(5, 30)
        query = random.choice(queries_pool)
        top_k = random.choice(top_ks)
        docs = [
            f"def func_{j}(): pass  # {random.choice(queries_pool)}"
            for j in range(doc_count)
        ]
        # query가 포함된 문서 삽입
        insert_idx = random.randint(0, doc_count - 1)
        docs[insert_idx] = f"{query}: implementation code"

        cases.append({
            "id": f"TC-E2E-{base_id + len(cases):06d}",
            "scenario": "integration_search",
            "sub_type": "bm25_search",
            "description": f"BM25 검색: '{query}' in {doc_count}개 문서",
            "documents": docs,
            "query": query,
            "top_k": top_k,
            "expected": {
                "result_type": "scored_list",
                "max_length": min(top_k, doc_count),
                "contains_query": True,
            },
        })

    # 2) 벡터 검색 (40%)
    for i in range(int(count * 0.40)):
        n_chunks = random.randint(3, 20)
        dim = random.choice(dims)
        top_k = random.choice(top_ks)
        file_path = f"src/search_test_{i % 20}.py"
        content = _make_python_content(n_chunks, 0)

        cases.append({
            "id": f"TC-E2E-{base_id + len(cases):06d}",
            "scenario": "integration_search",
            "sub_type": "vector_search",
            "description": f"벡터 검색: {n_chunks}함수 코드베이스 검색",
            "file_path": file_path,
            "content": content,
            "embedding_dim": dim,
            "top_k": top_k,
            "query_vec": _rand_vec(dim),
            "expected": {
                "result_type": "vector_results",
                "max_length": top_k,
                "sorted_desc": True,
            },
        })

    # 3) 빈 코퍼스 검색 (10%)
    for i in range(int(count * 0.10)):
        dim = random.choice(dims)
        cases.append({
            "id": f"TC-E2E-{base_id + len(cases):06d}",
            "scenario": "integration_search",
            "sub_type": "empty_corpus_search",
            "description": "빈 코퍼스 검색 → 빈 결과",
            "documents": [],
            "query": "def test",
            "top_k": 5,
            "embedding_dim": dim,
            "query_vec": _rand_vec(dim),
            "expected": {
                "result_type": "empty_list",
            },
        })

    # 나머지 채우기
    while len(cases) < count:
        n_chunks = random.randint(2, 10)
        dim = random.choice(dims)
        top_k = random.randint(1, 5)
        cases.append({
            "id": f"TC-E2E-{base_id + len(cases):06d}",
            "scenario": "integration_search",
            "sub_type": "vector_search",
            "description": f"벡터 검색 추가 케이스 {n_chunks}청크",
            "file_path": f"src/extra_search_{len(cases)}.py",
            "content": _make_python_content(n_chunks),
            "embedding_dim": dim,
            "top_k": top_k,
            "query_vec": _rand_vec(dim),
            "expected": {
                "result_type": "vector_results",
                "max_length": top_k,
                "sorted_desc": True,
            },
        })

    return cases[:count]


def _gen_data_consistency_cases(count: int, base_id: int) -> list[dict]:
    """데이터 일관성 E2E 케이스를 생성한다.

    동일 파일 재청킹, remove 후 검색 등 데이터 일관성 검증.
    """
    cases: list[dict] = []
    random.seed(300)
    dims = [256, 512]

    # 1) 동일 파일 재청킹 결과 일관성 (40%)
    for i in range(int(count * 0.40)):
        func_count = random.randint(1, 8)
        content = _make_python_content(func_count)
        file_path = f"src/consistent_{i % 20}.py"

        cases.append({
            "id": f"TC-E2E-{base_id + len(cases):06d}",
            "scenario": "data_consistency",
            "sub_type": "rechunk_consistency",
            "description": f"동일 파일({func_count}함수) 두 번 청킹 → 동일 결과",
            "file_path": file_path,
            "content": content,
            "expected": {
                "consistency": True,
                "same_chunk_count": True,
                "same_content": True,
            },
        })

    # 2) remove 후 검색 → 삭제된 청크 미포함 (30%)
    for i in range(int(count * 0.30)):
        n_files = random.randint(3, 8)
        func_per_file = random.randint(2, 5)
        dim = random.choice(dims)
        top_k = random.randint(3, 10)
        remove_idx = random.randint(0, n_files - 1)

        files = [
            {
                "path": f"src/remove_test_{i * n_files + j}.py",
                "content": _make_python_content(func_per_file),
            }
            for j in range(n_files)
        ]
        remove_path = files[remove_idx]["path"]

        cases.append({
            "id": f"TC-E2E-{base_id + len(cases):06d}",
            "scenario": "data_consistency",
            "sub_type": "remove_search",
            "description": f"{n_files}개 파일 추가 후 {remove_path} 삭제 → 검색 결과에 미포함",
            "files": files,
            "remove_path": remove_path,
            "embedding_dim": dim,
            "top_k": top_k,
            "query_vec": _rand_vec(dim),
            "expected": {
                "no_removed_path": remove_path,
                "result_type": "filtered_search",
            },
        })

    # 3) clear 후 검색 → 빈 결과 (15%)
    for i in range(int(count * 0.15)):
        n_files = random.randint(2, 5)
        dim = random.choice(dims)
        files = [
            {
                "path": f"src/clear_test_{i * n_files + j}.py",
                "content": _make_python_content(random.randint(1, 3)),
            }
            for j in range(n_files)
        ]

        cases.append({
            "id": f"TC-E2E-{base_id + len(cases):06d}",
            "scenario": "data_consistency",
            "sub_type": "clear_search",
            "description": f"{n_files}개 파일 추가 후 clear → 검색 결과 없음",
            "files": files,
            "embedding_dim": dim,
            "top_k": 5,
            "query_vec": _rand_vec(dim),
            "expected": {
                "result_type": "empty_list",
            },
        })

    # 나머지 채우기
    while len(cases) < count:
        func_count = random.randint(1, 5)
        content = _make_python_content(func_count)
        cases.append({
            "id": f"TC-E2E-{base_id + len(cases):06d}",
            "scenario": "data_consistency",
            "sub_type": "rechunk_consistency",
            "description": f"재청킹 일관성 추가 케이스 {func_count}함수",
            "file_path": f"src/extra_consistency_{len(cases)}.py",
            "content": content,
            "expected": {
                "consistency": True,
                "same_chunk_count": True,
            },
        })

    return cases[:count]


def _gen_performance_cases(count: int, base_id: int) -> list[dict]:
    """성능 E2E 케이스를 생성한다.

    대량 파일 처리, 고차원 임베딩, 대량 검색 쿼리 성능 검증.
    """
    cases: list[dict] = []
    random.seed(400)

    # 1) 대량 파일 처리 (40%)
    for i in range(int(count * 0.40)):
        n_files = random.randint(10, 50)
        func_per_file = random.randint(3, 10)
        dim = 256
        top_k = 10

        files = [
            {
                "path": f"src/perf_batch_{i * n_files + j}.py",
                "content": _make_python_content(func_per_file),
            }
            for j in range(n_files)
        ]

        cases.append({
            "id": f"TC-E2E-{base_id + len(cases):06d}",
            "scenario": "performance",
            "sub_type": "bulk_files",
            "description": f"대량 파일 {n_files}개 × {func_per_file}함수 처리",
            "files": files,
            "embedding_dim": dim,
            "top_k": top_k,
            "query_vec": _rand_vec(dim),
            "expected": {
                "result_type": "vector_results",
                "max_latency_ms": 5000,
            },
        })

    # 2) 고차원 임베딩 (30%)
    high_dims = [1024, 2048]
    for i in range(int(count * 0.30)):
        dim = random.choice(high_dims)
        n_chunks = random.randint(5, 20)
        top_k = random.randint(3, 10)
        content = _make_python_content(n_chunks)

        cases.append({
            "id": f"TC-E2E-{base_id + len(cases):06d}",
            "scenario": "performance",
            "sub_type": "high_dim_embedding",
            "description": f"고차원 임베딩 dim={dim} {n_chunks}청크 검색",
            "file_path": f"src/highdim_{i}.py",
            "content": content,
            "embedding_dim": dim,
            "top_k": top_k,
            "query_vec": _rand_vec(dim),
            "expected": {
                "result_type": "vector_results",
                "max_length": min(top_k, n_chunks),
            },
        })

    # 3) 대량 검색 쿼리 (20%)
    for i in range(int(count * 0.20)):
        dim = 256
        n_chunks = random.randint(20, 100)
        n_queries = random.randint(5, 20)
        top_k = 5

        content = _make_python_content(n_chunks)
        queries = [_rand_vec(dim) for _ in range(n_queries)]

        cases.append({
            "id": f"TC-E2E-{base_id + len(cases):06d}",
            "scenario": "performance",
            "sub_type": "bulk_queries",
            "description": f"대량 검색 {n_queries}쿼리 × {n_chunks}청크 코퍼스",
            "file_path": f"src/bulk_queries_{i}.py",
            "content": content,
            "embedding_dim": dim,
            "top_k": top_k,
            "queries": queries,
            "expected": {
                "result_type": "multi_search_results",
                "query_count": n_queries,
            },
        })

    # 나머지 채우기
    while len(cases) < count:
        dim = 256
        n_chunks = random.randint(5, 30)
        top_k = random.randint(1, 10)
        cases.append({
            "id": f"TC-E2E-{base_id + len(cases):06d}",
            "scenario": "performance",
            "sub_type": "bulk_files",
            "description": f"성능 테스트 추가 케이스 {n_chunks}청크",
            "files": [
                {
                    "path": f"src/perf_extra_{len(cases)}.py",
                    "content": _make_python_content(n_chunks),
                }
            ],
            "embedding_dim": dim,
            "top_k": top_k,
            "query_vec": _rand_vec(dim),
            "expected": {
                "result_type": "vector_results",
                "max_latency_ms": 5000,
            },
        })

    return cases[:count]


# ---------------------------------------------------------------------------
# 메인 생성 함수
# ---------------------------------------------------------------------------

def generate_e2e_cases(total: int = 100000) -> list[dict]:
    """전체 E2E 테스트 케이스를 생성한다."""
    counts = {
        "full_pipeline": int(total * 0.40),       # 40,000
        "integration_search": int(total * 0.30),  # 30,000
        "data_consistency": int(total * 0.20),    # 20,000
        "performance": int(total * 0.10),         # 10,000
    }
    remainder = total - sum(counts.values())
    counts["full_pipeline"] += remainder

    all_cases: list[dict] = []
    base_id = 1

    print("  full_pipeline 케이스 생성 중...")
    fp_cases = _gen_full_pipeline_cases(counts["full_pipeline"], base_id)
    all_cases.extend(fp_cases)
    base_id += len(fp_cases)
    print(f"  full_pipeline: {len(fp_cases):,}건")

    print("  integration_search 케이스 생성 중...")
    is_cases = _gen_integration_search_cases(counts["integration_search"], base_id)
    all_cases.extend(is_cases)
    base_id += len(is_cases)
    print(f"  integration_search: {len(is_cases):,}건")

    print("  data_consistency 케이스 생성 중...")
    dc_cases = _gen_data_consistency_cases(counts["data_consistency"], base_id)
    all_cases.extend(dc_cases)
    base_id += len(dc_cases)
    print(f"  data_consistency: {len(dc_cases):,}건")

    print("  performance 케이스 생성 중...")
    perf_cases = _gen_performance_cases(counts["performance"], base_id)
    all_cases.extend(perf_cases)
    print(f"  performance: {len(perf_cases):,}건")

    return all_cases


def main() -> None:
    """CLI 진입점."""
    parser = argparse.ArgumentParser(description="E2E QA 케이스 생성기")
    parser.add_argument("--count", type=int, default=100000)
    parser.add_argument("--output", default="tests/qa/test_cases.jsonl")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"E2E QA 케이스 생성 중... (총 {args.count:,}건)")
    cases = generate_e2e_cases(args.count)

    with open(output_path, "w", encoding="utf-8") as f:
        for tc in cases:
            f.write(json.dumps(tc, ensure_ascii=False) + "\n")

    print(f"\n생성 완료: {output_path} ({len(cases):,}건)")

    from collections import Counter
    cats = Counter(tc["scenario"] for tc in cases)
    for cat, cnt in sorted(cats.items()):
        print(f"  {cat}: {cnt:,}건")


if __name__ == "__main__":
    main()
