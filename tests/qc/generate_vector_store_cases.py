"""NumpyStore QC 테스트 케이스 생성기.

NumpyStore의 add/search/remove/clear 메서드를 대상으로
10,000개의 테스트 케이스를 JSONL 형식으로 생성한다.

각 케이스는 실제 청크 데이터와 임베딩 벡터를 포함한다.

카테고리별 비율:
- normal:   3,000건 (30%)
- boundary: 2,000건 (20%)
- invalid:  2,000건 (20%)
- stress:   1,500건 (15%)
- random:   1,500건 (15%)
"""

from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# 헬퍼 함수
# ---------------------------------------------------------------------------

def _make_chunk(file_path: str, start_line: int, content: str = "def foo(): pass",
                chunk_type: str = "function", name: str | None = None) -> dict:
    """CodeChunk 직렬화 딕셔너리를 생성한다."""
    lines = content.count("\n") + 1
    return {
        "file_path": file_path,
        "content": content,
        "start_line": start_line,
        "end_line": start_line + lines - 1,
        "chunk_type": chunk_type,
        "name": name or f"func_{start_line}",
    }


def _rand_vec(dim: int) -> list[float]:
    """무작위 단위 벡터를 생성한다."""
    v = [random.gauss(0, 1) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def _zero_vec(dim: int) -> list[float]:
    """영벡터를 생성한다."""
    return [0.0] * dim


def _make_chunks_and_embeddings(
    n: int, dim: int, file_prefix: str = "src/file"
) -> tuple[list[dict], list[list[float]]]:
    """n개 청크와 dim 차원 단위 임베딩을 생성한다."""
    chunks = [
        _make_chunk(f"{file_prefix}_{i % 10}.py", i * 10 + 1,
                    content=f"def func_{i}():\n    return {i}")
        for i in range(n)
    ]
    embeddings = [_rand_vec(dim) for _ in range(n)]
    return chunks, embeddings


# ---------------------------------------------------------------------------
# 카테고리별 케이스 생성
# ---------------------------------------------------------------------------

def _gen_normal_cases(count: int) -> list[dict]:
    """일반 add/search 시나리오를 생성한다."""
    cases: list[dict] = []
    random.seed(42)

    dims = [128, 256, 512, 1024]
    top_ks = [1, 5, 10, 50]

    # 1) add_search: 다양한 청크 수 × 차원 × top_k
    for _ in range(int(count * 0.50)):
        n = random.choice([1, 2, 5, 10, 20, 50, 100])
        dim = random.choice(dims)
        top_k = random.choice(top_ks)
        chunks, embeddings = _make_chunks_and_embeddings(n, dim)
        query = _rand_vec(dim)
        cases.append({
            "id": f"TC-NORMAL-{len(cases)+1:05d}",
            "category": "normal",
            "method": "add_search",
            "description": f"add {n}개 + search top_k={top_k} dim={dim}",
            "chunks": chunks,
            "embeddings": embeddings,
            "query_embedding": query,
            "top_k": top_k,
            "remove_path": "",
            "expected": {
                "type": "search_result",
                "length": min(top_k, n),
                "sorted_desc": True,
                "no_exception": True,
            },
        })

    # 2) add만
    for _ in range(int(count * 0.15)):
        n = random.randint(1, 50)
        dim = random.choice(dims)
        chunks, embeddings = _make_chunks_and_embeddings(n, dim)
        cases.append({
            "id": f"TC-NORMAL-{len(cases)+1:05d}",
            "category": "normal",
            "method": "add",
            "description": f"add {n}개 dim={dim}",
            "chunks": chunks,
            "embeddings": embeddings,
            "query_embedding": [],
            "top_k": 0,
            "remove_path": "",
            "expected": {"type": "no_exception", "no_exception": True},
        })

    # 3) add → remove → search
    for _ in range(int(count * 0.15)):
        dim = random.choice(dims)
        n = random.randint(3, 20)
        chunks, embeddings = _make_chunks_and_embeddings(n, dim, "src/module")
        remove_path = chunks[0]["file_path"]
        remaining = sum(1 for c in chunks if c["file_path"] != remove_path)
        top_k = min(5, remaining) if remaining > 0 else 1
        query = _rand_vec(dim)
        cases.append({
            "id": f"TC-NORMAL-{len(cases)+1:05d}",
            "category": "normal",
            "method": "add_remove_search",
            "description": f"add {n}개 → remove → search",
            "chunks": chunks,
            "embeddings": embeddings,
            "query_embedding": query,
            "top_k": top_k,
            "remove_path": remove_path,
            "expected": {
                "type": "search_result",
                "max_length": remaining,
                "no_removed_path": remove_path,
                "no_exception": True,
            },
        })

    # 4) add → clear → search
    for _ in range(int(count * 0.10)):
        dim = random.choice(dims)
        n = random.randint(1, 10)
        chunks, embeddings = _make_chunks_and_embeddings(n, dim)
        query = _rand_vec(dim)
        cases.append({
            "id": f"TC-NORMAL-{len(cases)+1:05d}",
            "category": "normal",
            "method": "add_search",
            "description": f"add {n}개 → clear → search",
            "chunks": chunks,
            "embeddings": embeddings,
            "query_embedding": query,
            "top_k": 5,
            "remove_path": "__clear__",
            "expected": {"type": "empty_list", "no_exception": True},
        })

    # 나머지 채우기
    while len(cases) < count:
        n = random.randint(1, 30)
        dim = random.choice(dims)
        top_k = random.randint(1, 20)
        chunks, embeddings = _make_chunks_and_embeddings(n, dim)
        query = _rand_vec(dim)
        cases.append({
            "id": f"TC-NORMAL-{len(cases)+1:05d}",
            "category": "normal",
            "method": "add_search",
            "description": f"일반 add_search n={n}",
            "chunks": chunks,
            "embeddings": embeddings,
            "query_embedding": query,
            "top_k": top_k,
            "remove_path": "",
            "expected": {
                "type": "search_result",
                "length": min(top_k, n),
                "sorted_desc": True,
                "no_exception": True,
            },
        })

    return cases[:count]


def _gen_boundary_cases(count: int) -> list[dict]:
    """경계 케이스를 생성한다."""
    cases: list[dict] = []
    random.seed(43)
    dim = 128

    # 1) 빈 스토어 search
    for _ in range(int(count * 0.10)):
        query = _rand_vec(dim)
        cases.append({
            "id": f"TC-BOUNDARY-{len(cases)+1:05d}",
            "category": "boundary",
            "method": "search",
            "description": "빈 스토어 search",
            "chunks": [],
            "embeddings": [],
            "query_embedding": query,
            "top_k": 5,
            "remove_path": "",
            "expected": {"type": "empty_list", "no_exception": True},
        })

    # 2) top_k=0
    for _ in range(int(count * 0.10)):
        n = random.randint(1, 10)
        chunks, embeddings = _make_chunks_and_embeddings(n, dim)
        query = _rand_vec(dim)
        cases.append({
            "id": f"TC-BOUNDARY-{len(cases)+1:05d}",
            "category": "boundary",
            "method": "add_search",
            "description": "top_k=0 → 빈 리스트",
            "chunks": chunks,
            "embeddings": embeddings,
            "query_embedding": query,
            "top_k": 0,
            "remove_path": "",
            "expected": {"type": "empty_list", "no_exception": True},
        })

    # 3) top_k=1
    for _ in range(int(count * 0.10)):
        n = random.randint(1, 20)
        chunks, embeddings = _make_chunks_and_embeddings(n, dim)
        query = _rand_vec(dim)
        cases.append({
            "id": f"TC-BOUNDARY-{len(cases)+1:05d}",
            "category": "boundary",
            "method": "add_search",
            "description": "top_k=1 → 1개 반환",
            "chunks": chunks,
            "embeddings": embeddings,
            "query_embedding": query,
            "top_k": 1,
            "remove_path": "",
            "expected": {"type": "search_result", "length": 1, "no_exception": True},
        })

    # 4) top_k > size
    for _ in range(int(count * 0.10)):
        n = random.randint(1, 10)
        chunks, embeddings = _make_chunks_and_embeddings(n, dim)
        query = _rand_vec(dim)
        top_k = n + random.randint(1, 50)
        cases.append({
            "id": f"TC-BOUNDARY-{len(cases)+1:05d}",
            "category": "boundary",
            "method": "add_search",
            "description": f"top_k({top_k}) > size({n}) → {n}개 반환",
            "chunks": chunks,
            "embeddings": embeddings,
            "query_embedding": query,
            "top_k": top_k,
            "remove_path": "",
            "expected": {"type": "search_result", "length": n, "no_exception": True},
        })

    # 5) 청크 1개
    for _ in range(int(count * 0.08)):
        chunk = _make_chunk("src/single.py", 1)
        vec = _rand_vec(dim)
        query = _rand_vec(dim)
        cases.append({
            "id": f"TC-BOUNDARY-{len(cases)+1:05d}",
            "category": "boundary",
            "method": "add_search",
            "description": "청크 1개 add_search",
            "chunks": [chunk],
            "embeddings": [vec],
            "query_embedding": query,
            "top_k": 5,
            "remove_path": "",
            "expected": {"type": "search_result", "length": 1, "no_exception": True},
        })

    # 6) 동일 벡터 여러 개
    for _ in range(int(count * 0.08)):
        n = 20
        vec = _rand_vec(dim)
        chunks = [_make_chunk(f"src/dup_{i}.py", i * 5 + 1) for i in range(n)]
        embeddings = [vec[:] for _ in range(n)]
        query = vec[:]
        cases.append({
            "id": f"TC-BOUNDARY-{len(cases)+1:05d}",
            "category": "boundary",
            "method": "add_search",
            "description": f"동일 벡터 {n}개 → top_k=10",
            "chunks": chunks,
            "embeddings": embeddings,
            "query_embedding": query,
            "top_k": 10,
            "remove_path": "",
            "expected": {"type": "search_result", "length": 10, "no_exception": True},
        })

    # 7) 영벡터 임베딩 (norm=0 → 유사도 0으로 처리, 그래도 반환)
    for _ in range(int(count * 0.08)):
        n = random.randint(1, 10)
        chunks = [_make_chunk(f"src/zero_{i}.py", i + 1) for i in range(n)]
        embeddings = [_zero_vec(dim) for _ in range(n)]
        query = _rand_vec(dim)
        cases.append({
            "id": f"TC-BOUNDARY-{len(cases)+1:05d}",
            "category": "boundary",
            "method": "add_search",
            "description": f"영벡터 임베딩 {n}개 → 유사도 0으로 처리",
            "chunks": chunks,
            "embeddings": embeddings,
            "query_embedding": query,
            "top_k": 5,
            "remove_path": "",
            "expected": {
                "type": "search_result",
                "length": min(5, n),
                "no_exception": True,
            },
        })

    # 8) 쿼리가 영벡터 → 빈 리스트
    for _ in range(int(count * 0.08)):
        n = random.randint(1, 10)
        chunks, embeddings = _make_chunks_and_embeddings(n, dim)
        cases.append({
            "id": f"TC-BOUNDARY-{len(cases)+1:05d}",
            "category": "boundary",
            "method": "add_search",
            "description": "쿼리 영벡터 → 빈 리스트",
            "chunks": chunks,
            "embeddings": embeddings,
            "query_embedding": _zero_vec(dim),
            "top_k": 5,
            "remove_path": "",
            "expected": {"type": "empty_list", "no_exception": True},
        })

    # 9) clear 후 search
    for _ in range(int(count * 0.08)):
        n = random.randint(1, 10)
        chunks, embeddings = _make_chunks_and_embeddings(n, dim)
        cases.append({
            "id": f"TC-BOUNDARY-{len(cases)+1:05d}",
            "category": "boundary",
            "method": "add_search",
            "description": "add → clear → search",
            "chunks": chunks,
            "embeddings": embeddings,
            "query_embedding": _rand_vec(dim),
            "top_k": 5,
            "remove_path": "__clear__",
            "expected": {"type": "empty_list", "no_exception": True},
        })

    # 10) 존재하지 않는 파일 remove → 조용히 처리
    for _ in range(int(count * 0.08)):
        n = random.randint(1, 10)
        chunks, embeddings = _make_chunks_and_embeddings(n, dim)
        query = _rand_vec(dim)
        cases.append({
            "id": f"TC-BOUNDARY-{len(cases)+1:05d}",
            "category": "boundary",
            "method": "add_remove_search",
            "description": "존재하지 않는 파일 remove → 정상 처리",
            "chunks": chunks,
            "embeddings": embeddings,
            "query_embedding": query,
            "top_k": min(5, n),
            "remove_path": "nonexistent/file.py",
            "expected": {
                "type": "search_result",
                "length": min(5, n),
                "no_exception": True,
            },
        })

    # 나머지 채우기
    while len(cases) < count:
        variant = random.randint(0, 3)
        if variant == 0:
            query = _rand_vec(dim)
            cases.append({
                "id": f"TC-BOUNDARY-{len(cases)+1:05d}",
                "category": "boundary",
                "method": "search",
                "description": "빈 스토어 search",
                "chunks": [], "embeddings": [],
                "query_embedding": query, "top_k": 5, "remove_path": "",
                "expected": {"type": "empty_list", "no_exception": True},
            })
        elif variant == 1:
            n = random.randint(1, 10)
            chunks, embeddings = _make_chunks_and_embeddings(n, dim)
            cases.append({
                "id": f"TC-BOUNDARY-{len(cases)+1:05d}",
                "category": "boundary",
                "method": "add_search",
                "description": "top_k=0",
                "chunks": chunks, "embeddings": embeddings,
                "query_embedding": _rand_vec(dim), "top_k": 0, "remove_path": "",
                "expected": {"type": "empty_list", "no_exception": True},
            })
        elif variant == 2:
            n = random.randint(1, 5)
            chunks, embeddings = _make_chunks_and_embeddings(n, dim)
            cases.append({
                "id": f"TC-BOUNDARY-{len(cases)+1:05d}",
                "category": "boundary",
                "method": "add_search",
                "description": "zero 쿼리",
                "chunks": chunks, "embeddings": embeddings,
                "query_embedding": _zero_vec(dim), "top_k": 5, "remove_path": "",
                "expected": {"type": "empty_list", "no_exception": True},
            })
        else:
            n = random.randint(1, 10)
            chunks, embeddings = _make_chunks_and_embeddings(n, dim)
            top_k = n + 10
            query = _rand_vec(dim)
            cases.append({
                "id": f"TC-BOUNDARY-{len(cases)+1:05d}",
                "category": "boundary",
                "method": "add_search",
                "description": "top_k > size",
                "chunks": chunks, "embeddings": embeddings,
                "query_embedding": query, "top_k": top_k, "remove_path": "",
                "expected": {"type": "search_result", "length": n, "no_exception": True},
            })

    return cases[:count]


def _gen_invalid_cases(count: int) -> list[dict]:
    """잘못된 입력 케이스를 생성한다."""
    cases: list[dict] = []
    random.seed(44)
    dim = 128

    # 1) chunks > embeddings → ValueError
    for _ in range(int(count * 0.30)):
        n = random.randint(2, 20)
        m = random.randint(1, n - 1)
        chunks = [_make_chunk(f"src/a_{i}.py", i * 10 + 1) for i in range(n)]
        embeddings = [_rand_vec(dim) for _ in range(m)]
        cases.append({
            "id": f"TC-INVALID-{len(cases)+1:05d}",
            "category": "invalid",
            "method": "add",
            "description": f"chunks({n}) > embeddings({m}) → ValueError",
            "chunks": chunks,
            "embeddings": embeddings,
            "query_embedding": [],
            "top_k": 0,
            "remove_path": "",
            "expected": {
                "type": "exception",
                "exception_type": "ValueError",
                "no_exception": False,
            },
        })

    # 2) embeddings > chunks → ValueError
    for _ in range(int(count * 0.30)):
        n = random.randint(1, 10)
        m = n + random.randint(1, 10)
        chunks = [_make_chunk(f"src/b_{i}.py", i * 10 + 1) for i in range(n)]
        embeddings = [_rand_vec(dim) for _ in range(m)]
        cases.append({
            "id": f"TC-INVALID-{len(cases)+1:05d}",
            "category": "invalid",
            "method": "add",
            "description": f"embeddings({m}) > chunks({n}) → ValueError",
            "chunks": chunks,
            "embeddings": embeddings,
            "query_embedding": [],
            "top_k": 0,
            "remove_path": "",
            "expected": {
                "type": "exception",
                "exception_type": "ValueError",
                "no_exception": False,
            },
        })

    # 3) 빈 add (둘 다 0) → no_exception
    for _ in range(int(count * 0.20)):
        cases.append({
            "id": f"TC-INVALID-{len(cases)+1:05d}",
            "category": "invalid",
            "method": "add",
            "description": "빈 chunks + 빈 embeddings add → 예외 없음",
            "chunks": [], "embeddings": [],
            "query_embedding": [], "top_k": 0, "remove_path": "",
            "expected": {"type": "no_exception", "no_exception": True},
        })

    # 4) 음수 top_k → 빈 리스트
    for _ in range(int(count * 0.20)):
        n = random.randint(1, 10)
        chunks, embeddings = _make_chunks_and_embeddings(n, dim)
        query = _rand_vec(dim)
        top_k = random.randint(-100, -1)
        cases.append({
            "id": f"TC-INVALID-{len(cases)+1:05d}",
            "category": "invalid",
            "method": "add_search",
            "description": f"음수 top_k={top_k} → 빈 리스트",
            "chunks": chunks,
            "embeddings": embeddings,
            "query_embedding": query,
            "top_k": top_k,
            "remove_path": "",
            "expected": {"type": "empty_list", "no_exception": True},
        })

    # 나머지 채우기
    while len(cases) < count:
        variant = random.randint(0, 3)
        if variant == 0:
            n = random.randint(2, 10)
            m = random.randint(1, n - 1)
            chunks = [_make_chunk(f"src/c_{i}.py", i + 1) for i in range(n)]
            embeddings = [_rand_vec(dim) for _ in range(m)]
            cases.append({
                "id": f"TC-INVALID-{len(cases)+1:05d}",
                "category": "invalid",
                "method": "add",
                "description": "길이 불일치 → ValueError",
                "chunks": chunks, "embeddings": embeddings,
                "query_embedding": [], "top_k": 0, "remove_path": "",
                "expected": {
                    "type": "exception",
                    "exception_type": "ValueError",
                    "no_exception": False,
                },
            })
        elif variant == 1:
            cases.append({
                "id": f"TC-INVALID-{len(cases)+1:05d}",
                "category": "invalid",
                "method": "add",
                "description": "빈 add",
                "chunks": [], "embeddings": [],
                "query_embedding": [], "top_k": 0, "remove_path": "",
                "expected": {"type": "no_exception", "no_exception": True},
            })
        elif variant == 2:
            n = random.randint(1, 10)
            chunks, embeddings = _make_chunks_and_embeddings(n, dim)
            query = _rand_vec(dim)
            cases.append({
                "id": f"TC-INVALID-{len(cases)+1:05d}",
                "category": "invalid",
                "method": "add_search",
                "description": "음수 top_k",
                "chunks": chunks, "embeddings": embeddings,
                "query_embedding": query,
                "top_k": random.randint(-50, -1),
                "remove_path": "",
                "expected": {"type": "empty_list", "no_exception": True},
            })
        else:
            n = random.randint(1, 5)
            m = n + random.randint(1, 5)
            chunks = [_make_chunk(f"src/d_{i}.py", i + 1) for i in range(n)]
            embeddings = [_rand_vec(dim) for _ in range(m)]
            cases.append({
                "id": f"TC-INVALID-{len(cases)+1:05d}",
                "category": "invalid",
                "method": "add",
                "description": "embeddings > chunks → ValueError",
                "chunks": chunks, "embeddings": embeddings,
                "query_embedding": [], "top_k": 0, "remove_path": "",
                "expected": {
                    "type": "exception",
                    "exception_type": "ValueError",
                    "no_exception": False,
                },
            })

    return cases[:count]


def _gen_stress_cases(count: int) -> list[dict]:
    """스트레스 케이스를 생성한다."""
    cases: list[dict] = []
    random.seed(45)

    # 1) 대량 청크 (100~500개)
    for _ in range(int(count * 0.40)):
        n = random.randint(100, 500)
        dim = random.choice([128, 256])
        chunks, embeddings = _make_chunks_and_embeddings(n, dim, "src/large")
        query = _rand_vec(dim)
        top_k = random.choice([10, 20, 50])
        cases.append({
            "id": f"TC-STRESS-{len(cases)+1:05d}",
            "category": "stress",
            "method": "add_search",
            "description": f"대량 add {n}개 + search top_k={top_k}",
            "chunks": chunks,
            "embeddings": embeddings,
            "query_embedding": query,
            "top_k": top_k,
            "remove_path": "",
            "expected": {
                "type": "search_result",
                "length": min(top_k, n),
                "sorted_desc": True,
                "no_exception": True,
            },
        })

    # 2) add → remove → search (대량)
    for _ in range(int(count * 0.30)):
        dim = 128
        n = random.randint(50, 200)
        files = [f"src/stress_{i}.py" for i in range(10)]
        chunks = []
        for i in range(n):
            chunks.append(_make_chunk(files[i % 10], i * 5 + 1,
                                      content=f"def f_{i}(): pass"))
        embeddings = [_rand_vec(dim) for _ in range(n)]
        remove_path = files[0]
        remaining = sum(1 for c in chunks if c["file_path"] != remove_path)
        top_k = min(10, remaining) if remaining > 0 else 1
        query = _rand_vec(dim)
        cases.append({
            "id": f"TC-STRESS-{len(cases)+1:05d}",
            "category": "stress",
            "method": "add_remove_search",
            "description": f"add {n}개 → remove {remove_path} → search",
            "chunks": chunks,
            "embeddings": embeddings,
            "query_embedding": query,
            "top_k": top_k,
            "remove_path": remove_path,
            "expected": {
                "type": "search_result",
                "max_length": remaining,
                "no_removed_path": remove_path,
                "no_exception": True,
            },
        })

    # 3) 고차원 벡터
    for _ in range(int(count * 0.20)):
        dim = random.choice([512, 1024])
        n = random.randint(10, 50)
        chunks, embeddings = _make_chunks_and_embeddings(n, dim, "src/highdim")
        query = _rand_vec(dim)
        top_k = random.randint(1, min(10, n))
        cases.append({
            "id": f"TC-STRESS-{len(cases)+1:05d}",
            "category": "stress",
            "method": "add_search",
            "description": f"고차원 dim={dim} n={n}",
            "chunks": chunks,
            "embeddings": embeddings,
            "query_embedding": query,
            "top_k": top_k,
            "remove_path": "",
            "expected": {
                "type": "search_result",
                "length": min(top_k, n),
                "no_exception": True,
            },
        })

    # 나머지 채우기
    while len(cases) < count:
        n = random.randint(50, 200)
        dim = 128
        chunks, embeddings = _make_chunks_and_embeddings(n, dim)
        query = _rand_vec(dim)
        top_k = random.randint(1, 20)
        cases.append({
            "id": f"TC-STRESS-{len(cases)+1:05d}",
            "category": "stress",
            "method": "add_search",
            "description": f"stress add_search n={n}",
            "chunks": chunks,
            "embeddings": embeddings,
            "query_embedding": query,
            "top_k": top_k,
            "remove_path": "",
            "expected": {
                "type": "search_result",
                "length": min(top_k, n),
                "no_exception": True,
            },
        })

    return cases[:count]


def _gen_random_cases(count: int) -> list[dict]:
    """무작위 퍼징 케이스를 생성한다."""
    cases: list[dict] = []
    random.seed(46)

    for i in range(count):
        tc_id = f"TC-RANDOM-{i+1:05d}"
        dim = random.randint(1, 256)
        n = random.randint(0, 100)
        top_k = random.randint(0, 200)
        variant = random.random()

        if n == 0:
            query = _rand_vec(dim)
            cases.append({
                "id": tc_id, "category": "random", "method": "search",
                "description": f"무작위 빈 스토어 dim={dim} top_k={top_k}",
                "chunks": [], "embeddings": [],
                "query_embedding": query, "top_k": top_k, "remove_path": "",
                "expected": {"type": "empty_list", "no_exception": True},
            })
        elif variant < 0.35:
            chunks, embeddings = _make_chunks_and_embeddings(n, dim, "src/rand")
            query = _rand_vec(dim)
            if top_k <= 0:
                expected = {"type": "empty_list", "no_exception": True}
            else:
                expected = {
                    "type": "search_result",
                    "length": min(top_k, n),
                    "no_exception": True,
                }
            cases.append({
                "id": tc_id, "category": "random", "method": "add_search",
                "description": f"무작위 add_search n={n} dim={dim} top_k={top_k}",
                "chunks": chunks, "embeddings": embeddings,
                "query_embedding": query, "top_k": top_k, "remove_path": "",
                "expected": expected,
            })
        elif variant < 0.55:
            chunks, embeddings = _make_chunks_and_embeddings(n, dim, "src/rand2")
            cases.append({
                "id": tc_id, "category": "random", "method": "add_search",
                "description": f"무작위 zero 쿼리 n={n} dim={dim}",
                "chunks": chunks, "embeddings": embeddings,
                "query_embedding": _zero_vec(dim), "top_k": top_k, "remove_path": "",
                "expected": {"type": "empty_list", "no_exception": True},
            })
        elif variant < 0.75:
            chunks, embeddings = _make_chunks_and_embeddings(n, dim, "src/rand3")
            remove_path = f"src/rand3_{(i % 10)}.py"
            query = _rand_vec(dim)
            remaining = sum(1 for c in chunks if c["file_path"] != remove_path)
            if top_k <= 0:
                expected = {"type": "empty_list", "no_exception": True}
            else:
                expected = {
                    "type": "search_result",
                    "max_length": remaining,
                    "no_exception": True,
                }
            cases.append({
                "id": tc_id, "category": "random", "method": "add_remove_search",
                "description": f"무작위 add_remove_search n={n} dim={dim}",
                "chunks": chunks, "embeddings": embeddings,
                "query_embedding": query, "top_k": top_k,
                "remove_path": remove_path, "expected": expected,
            })
        else:
            chunks, embeddings = _make_chunks_and_embeddings(n, dim, "src/rand4")
            query = _rand_vec(dim)
            cases.append({
                "id": tc_id, "category": "random", "method": "add_search",
                "description": f"무작위 add → clear → search n={n}",
                "chunks": chunks, "embeddings": embeddings,
                "query_embedding": query, "top_k": top_k,
                "remove_path": "__clear__",
                "expected": {"type": "empty_list", "no_exception": True},
            })

    return cases[:count]


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def generate_cases(total: int = 10000) -> list[dict]:
    """전체 테스트 케이스를 생성하고 ID를 재지정한다."""
    counts = {
        "normal": int(total * 0.30),
        "boundary": int(total * 0.20),
        "invalid": int(total * 0.20),
        "stress": int(total * 0.15),
        "random": int(total * 0.15),
    }
    remainder = total - sum(counts.values())
    counts["normal"] += remainder

    all_cases: list[dict] = []
    all_cases.extend(_gen_normal_cases(counts["normal"]))
    all_cases.extend(_gen_boundary_cases(counts["boundary"]))
    all_cases.extend(_gen_invalid_cases(counts["invalid"]))
    all_cases.extend(_gen_stress_cases(counts["stress"]))
    all_cases.extend(_gen_random_cases(counts["random"]))

    # ID를 TC-MODULE-XXXXX로 통일
    for idx, tc in enumerate(all_cases, 1):
        tc["id"] = f"TC-MODULE-{idx:05d}"

    return all_cases


def main() -> None:
    """CLI 진입점."""
    parser = argparse.ArgumentParser(description="NumpyStore QC 케이스 생성기")
    parser.add_argument("--count", type=int, default=10000)
    parser.add_argument("--output", default="tests/qc/vector_store/")
    parser.add_argument("--module", default="src/rag/vector_store.py")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "test_cases.jsonl"

    print(f"케이스 생성 중... (총 {args.count:,}건)")
    cases = generate_cases(args.count)

    with open(output_path, "w", encoding="utf-8") as f:
        for tc in cases:
            f.write(json.dumps(tc, ensure_ascii=False) + "\n")

    print(f"생성 완료: {output_path} ({len(cases):,}건)")

    from collections import Counter
    cats = Counter(tc["category"] for tc in cases)
    for cat, cnt in sorted(cats.items()):
        print(f"  {cat}: {cnt:,}건")


if __name__ == "__main__":
    main()
