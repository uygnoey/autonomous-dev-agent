"""HybridSearcher 모듈 QC 케이스 생성기.

10,000건의 JSONL 테스트 케이스를 생성한다.

케이스 포맷:
- id: 케이스 고유 ID (TC-HYBRID-XXXXX)
- category: normal / boundary / invalid / stress / random
- description: 케이스 설명
- query: 검색 쿼리 문자열
- top_k: 반환할 최대 결과 수
- chunks: CodeChunk 직렬화 목록 (BM25 fit 코퍼스)
- embeddings: 각 청크의 임베딩 벡터 (NumpyStore에 저장)
- bm25_weight: HybridSearcher bm25_weight
- vector_weight: HybridSearcher vector_weight
- embedder_available: bool — AnthropicEmbedder.is_available mock 값
- query_embedding: 쿼리 임베딩 벡터 (embedder_available=True 시 사용)
- expected:
    type: "search_result" | "empty_list" | "no_exception"
    max_length: 최대 결과 수 (search_result일 때)
    sorted_desc: 내림차순 정렬 여부 (search_result일 때)
"""

from __future__ import annotations

import argparse
import json
import math
import random
import string
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


# ------------------------------------------------------------------
# 벡터 유틸리티
# ------------------------------------------------------------------

def _rand_unit_vec(dim: int) -> list[float]:
    """dim 차원 단위 벡터를 무작위 생성한다."""
    v = [random.gauss(0.0, 1.0) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def _zero_vec(dim: int) -> list[float]:
    return [0.0] * dim


# ------------------------------------------------------------------
# CodeChunk 직렬화 헬퍼
# ------------------------------------------------------------------

_CHUNK_TYPES = ("function", "class", "module", "block")
_KEYWORDS = [
    "search", "index", "embed", "chunk", "score", "query", "result",
    "fetch", "parse", "build", "run", "test", "load", "save", "delete",
    "update", "create", "get", "set", "check",
]


def _rand_word() -> str:
    return random.choice(_KEYWORDS)


def _rand_identifier() -> str:
    parts = [random.choice(_KEYWORDS) for _ in range(random.randint(1, 3))]
    return "_".join(parts)


def _rand_content(n_words: int = 10) -> str:
    words = [_rand_word() for _ in range(n_words)]
    return " ".join(words)


def _make_chunk(
    file_path: str | None = None,
    start_line: int | None = None,
    chunk_type: str | None = None,
    name: str | None = None,
    content: str | None = None,
) -> dict:
    fp = file_path or f"src/{_rand_identifier()}.py"
    sl = start_line if start_line is not None else random.randint(1, 500)
    el = sl + random.randint(1, 50)
    ct = chunk_type or random.choice(_CHUNK_TYPES)
    nm = name or _rand_identifier()
    cnt = content or _rand_content(random.randint(5, 30))
    return {
        "file_path": fp,
        "content": cnt,
        "start_line": sl,
        "end_line": el,
        "chunk_type": ct,
        "name": nm,
    }


def _make_chunks(n: int, dim: int) -> tuple[list[dict], list[list[float]]]:
    """n개의 청크와 대응 임베딩 벡터를 생성한다."""
    chunks: list[dict] = []
    embeddings: list[list[float]] = []
    base_line = 1
    for _ in range(n):
        c = _make_chunk(start_line=base_line)
        base_line = c["end_line"] + random.randint(1, 10)
        chunks.append(c)
        embeddings.append(_rand_unit_vec(dim))
    return chunks, embeddings


# ------------------------------------------------------------------
# 카테고리별 케이스 생성 함수
# ------------------------------------------------------------------

def _gen_normal(tc_id: str, dim: int = 128) -> dict:
    """정상 동작: 쿼리 + 청크 + 임베딩 모두 유효."""
    n = random.randint(3, 20)
    top_k = random.randint(1, n)
    chunks, embeddings = _make_chunks(n, dim)
    query = _rand_content(random.randint(2, 8))
    query_embedding = _rand_unit_vec(dim)
    embedder_available = random.choice([True, False])

    return {
        "id": tc_id,
        "category": "normal",
        "description": f"정상 검색: n={n}, top_k={top_k}, embedder={embedder_available}",
        "query": query,
        "top_k": top_k,
        "chunks": chunks,
        "embeddings": embeddings,
        "bm25_weight": round(random.uniform(0.3, 0.8), 2),
        "vector_weight": round(random.uniform(0.2, 0.7), 2),
        "embedder_available": embedder_available,
        "query_embedding": query_embedding if embedder_available else [],
        "expected": {
            "type": "search_result",
            "max_length": top_k,
            "sorted_desc": True,
        },
    }


def _gen_normal_bm25_only(tc_id: str, dim: int = 128) -> dict:
    """BM25 전용 모드: embedder_available=False."""
    n = random.randint(3, 15)
    top_k = random.randint(1, n)
    chunks, embeddings = _make_chunks(n, dim)
    # 쿼리에 청크 내용의 단어 포함 → BM25 히트 유도
    chunk_words = chunks[0]["content"].split()[:3]
    query = " ".join(chunk_words) + " " + _rand_content(2)

    return {
        "id": tc_id,
        "category": "normal",
        "description": f"BM25 전용 모드: n={n}, top_k={top_k}",
        "query": query,
        "top_k": top_k,
        "chunks": chunks,
        "embeddings": embeddings,
        "bm25_weight": 0.6,
        "vector_weight": 0.4,
        "embedder_available": False,
        "query_embedding": [],
        "expected": {
            "type": "search_result",
            "max_length": top_k,
            "sorted_desc": True,
        },
    }


def _gen_boundary_empty_query(tc_id: str, dim: int = 128) -> dict:
    """경계값: 빈 쿼리 → 빈 리스트."""
    n = random.randint(1, 10)
    chunks, embeddings = _make_chunks(n, dim)
    query = random.choice(["", "   ", "\t", "\n"])

    return {
        "id": tc_id,
        "category": "boundary",
        "description": "빈 쿼리 → empty_list",
        "query": query,
        "top_k": random.randint(1, 5),
        "chunks": chunks,
        "embeddings": embeddings,
        "bm25_weight": 0.6,
        "vector_weight": 0.4,
        "embedder_available": True,
        "query_embedding": _rand_unit_vec(dim),
        "expected": {"type": "empty_list"},
    }


def _gen_boundary_empty_chunks(tc_id: str, dim: int = 128) -> dict:
    """경계값: 빈 청크 리스트 → 빈 리스트."""
    return {
        "id": tc_id,
        "category": "boundary",
        "description": "빈 청크 → empty_list",
        "query": _rand_content(3),
        "top_k": random.randint(1, 5),
        "chunks": [],
        "embeddings": [],
        "bm25_weight": 0.6,
        "vector_weight": 0.4,
        "embedder_available": True,
        "query_embedding": _rand_unit_vec(dim),
        "expected": {"type": "empty_list"},
    }


def _gen_boundary_topk_zero(tc_id: str, dim: int = 128) -> dict:
    """경계값: top_k=0 → 빈 리스트."""
    n = random.randint(1, 10)
    chunks, embeddings = _make_chunks(n, dim)

    return {
        "id": tc_id,
        "category": "boundary",
        "description": "top_k=0 → empty_list",
        "query": _rand_content(3),
        "top_k": 0,
        "chunks": chunks,
        "embeddings": embeddings,
        "bm25_weight": 0.6,
        "vector_weight": 0.4,
        "embedder_available": True,
        "query_embedding": _rand_unit_vec(dim),
        "expected": {"type": "empty_list"},
    }


def _gen_boundary_topk_negative(tc_id: str, dim: int = 128) -> dict:
    """경계값: top_k 음수 → 빈 리스트."""
    n = random.randint(1, 10)
    chunks, embeddings = _make_chunks(n, dim)

    return {
        "id": tc_id,
        "category": "boundary",
        "description": "top_k 음수 → empty_list",
        "query": _rand_content(3),
        "top_k": random.randint(-10, -1),
        "chunks": chunks,
        "embeddings": embeddings,
        "bm25_weight": 0.6,
        "vector_weight": 0.4,
        "embedder_available": True,
        "query_embedding": _rand_unit_vec(dim),
        "expected": {"type": "empty_list"},
    }


def _gen_boundary_single_chunk(tc_id: str, dim: int = 128) -> dict:
    """경계값: 청크 1개."""
    chunks, embeddings = _make_chunks(1, dim)
    query = chunks[0]["content"].split()[0] if chunks[0]["content"].split() else "search"

    return {
        "id": tc_id,
        "category": "boundary",
        "description": "청크 1개 top_k=1",
        "query": query,
        "top_k": 1,
        "chunks": chunks,
        "embeddings": embeddings,
        "bm25_weight": 0.6,
        "vector_weight": 0.4,
        "embedder_available": False,
        "query_embedding": [],
        "expected": {
            "type": "search_result",
            "max_length": 1,
            "sorted_desc": True,
        },
    }


def _gen_boundary_topk_larger_than_chunks(tc_id: str, dim: int = 128) -> dict:
    """경계값: top_k > 청크 수 → 최대 청크 수만큼 반환."""
    n = random.randint(1, 5)
    chunks, embeddings = _make_chunks(n, dim)
    top_k = n + random.randint(1, 10)
    query = _rand_content(3)

    return {
        "id": tc_id,
        "category": "boundary",
        "description": f"top_k({top_k}) > chunks({n}) → max={n}",
        "query": query,
        "top_k": top_k,
        "chunks": chunks,
        "embeddings": embeddings,
        "bm25_weight": 0.6,
        "vector_weight": 0.4,
        "embedder_available": False,
        "query_embedding": [],
        "expected": {
            "type": "search_result",
            "max_length": top_k,
            "sorted_desc": True,
        },
    }


def _gen_boundary_query_no_bm25_hit(tc_id: str, dim: int = 128) -> dict:
    """경계값: BM25 히트 없는 쿼리 (랜덤 문자열) + embedder=False → 빈 리스트."""
    n = random.randint(2, 8)
    chunks, embeddings = _make_chunks(n, dim)
    # 완전 랜덤 문자열 → BM25 토큰 없음
    query = "".join(random.choices(string.punctuation + string.digits, k=20))

    return {
        "id": tc_id,
        "category": "boundary",
        "description": "BM25 히트 없는 쿼리 + embedder=False → empty_list",
        "query": query,
        "top_k": random.randint(1, 5),
        "chunks": chunks,
        "embeddings": embeddings,
        "bm25_weight": 0.6,
        "vector_weight": 0.4,
        "embedder_available": False,
        "query_embedding": [],
        "expected": {"type": "empty_list"},
    }


def _gen_invalid_embed_fail(tc_id: str, dim: int = 128) -> dict:
    """invalid: embedder.embed() 예외 발생 → BM25 전용 폴백, no_exception."""
    n = random.randint(3, 10)
    chunks, embeddings = _make_chunks(n, dim)
    query = _rand_content(3)
    top_k = random.randint(1, n)

    return {
        "id": tc_id,
        "category": "invalid",
        "description": "embedder.embed() 예외 → BM25 전용 폴백",
        "query": query,
        "top_k": top_k,
        "chunks": chunks,
        "embeddings": embeddings,
        "bm25_weight": 0.6,
        "vector_weight": 0.4,
        "embedder_available": True,
        "query_embedding": None,  # None → embed()가 예외 발생하도록 신호
        "expected": {
            "type": "search_result",
            "max_length": top_k,
            "sorted_desc": True,
        },
    }


def _gen_invalid_zero_query_embedding(tc_id: str, dim: int = 128) -> dict:
    """invalid: 영벡터 쿼리 임베딩 (코사인 유사도 계산 시 0으로 처리)."""
    n = random.randint(3, 10)
    chunks, embeddings = _make_chunks(n, dim)
    query = _rand_content(3)

    return {
        "id": tc_id,
        "category": "invalid",
        "description": "영벡터 쿼리 임베딩 → no_exception",
        "query": query,
        "top_k": random.randint(1, n),
        "chunks": chunks,
        "embeddings": embeddings,
        "bm25_weight": 0.6,
        "vector_weight": 0.4,
        "embedder_available": True,
        "query_embedding": _zero_vec(dim),
        "expected": {
            "type": "no_exception",
        },
    }


def _gen_invalid_unfitted_scorer(tc_id: str, dim: int = 128) -> dict:
    """invalid: BM25 scorer.fit() 미실행 → no_exception (top_k()가 빈 리스트 반환)."""
    n = random.randint(3, 10)
    chunks, embeddings = _make_chunks(n, dim)
    query = _rand_content(3)

    return {
        "id": tc_id,
        "category": "invalid",
        "description": "BM25 fit 미실행 → no_exception",
        "query": query,
        "top_k": random.randint(1, n),
        "chunks": chunks,
        "embeddings": embeddings,
        "bm25_weight": 0.6,
        "vector_weight": 0.4,
        "embedder_available": False,
        "query_embedding": [],
        "scorer_unfitted": True,  # QC 실행기가 fit() 호출 안 함
        "expected": {
            "type": "empty_list",
        },
    }


def _gen_invalid_weight_zero(tc_id: str, dim: int = 128) -> dict:
    """invalid: bm25_weight=0, vector_weight=0 → no_exception."""
    n = random.randint(3, 10)
    chunks, embeddings = _make_chunks(n, dim)

    return {
        "id": tc_id,
        "category": "invalid",
        "description": "가중치 모두 0 → no_exception",
        "query": _rand_content(3),
        "top_k": random.randint(1, n),
        "chunks": chunks,
        "embeddings": embeddings,
        "bm25_weight": 0.0,
        "vector_weight": 0.0,
        "embedder_available": True,
        "query_embedding": _rand_unit_vec(dim),
        "expected": {"type": "no_exception"},
    }


def _gen_stress_large_corpus(tc_id: str, dim: int = 128) -> dict:
    """stress: 대규모 코퍼스 (500~1000개 청크)."""
    n = random.randint(500, 1000)
    top_k = random.randint(5, 20)
    chunks, embeddings = _make_chunks(n, dim)
    query = _rand_content(5)

    return {
        "id": tc_id,
        "category": "stress",
        "description": f"대규모 코퍼스 n={n}, top_k={top_k}",
        "query": query,
        "top_k": top_k,
        "chunks": chunks,
        "embeddings": embeddings,
        "bm25_weight": 0.6,
        "vector_weight": 0.4,
        "embedder_available": False,
        "query_embedding": [],
        "expected": {
            "type": "search_result",
            "max_length": top_k,
            "sorted_desc": True,
        },
    }


def _gen_stress_high_top_k(tc_id: str, dim: int = 128) -> dict:
    """stress: top_k가 코퍼스 크기에 근접."""
    n = random.randint(50, 200)
    top_k = n - random.randint(0, 5)
    top_k = max(1, top_k)
    chunks, embeddings = _make_chunks(n, dim)
    query = _rand_content(5)

    return {
        "id": tc_id,
        "category": "stress",
        "description": f"top_k≈n: n={n}, top_k={top_k}",
        "query": query,
        "top_k": top_k,
        "chunks": chunks,
        "embeddings": embeddings,
        "bm25_weight": 0.6,
        "vector_weight": 0.4,
        "embedder_available": False,
        "query_embedding": [],
        "expected": {
            "type": "search_result",
            "max_length": top_k,
            "sorted_desc": True,
        },
    }


def _gen_stress_high_dim(tc_id: str) -> dict:
    """stress: 고차원 임베딩 (1024차원)."""
    dim = 1024
    n = random.randint(10, 50)
    top_k = random.randint(1, min(10, n))
    chunks, embeddings = _make_chunks(n, dim)
    query = _rand_content(5)
    query_embedding = _rand_unit_vec(dim)

    return {
        "id": tc_id,
        "category": "stress",
        "description": f"고차원 임베딩 dim={dim}, n={n}",
        "query": query,
        "top_k": top_k,
        "chunks": chunks,
        "embeddings": embeddings,
        "bm25_weight": 0.6,
        "vector_weight": 0.4,
        "embedder_available": True,
        "query_embedding": query_embedding,
        "expected": {
            "type": "search_result",
            "max_length": top_k,
            "sorted_desc": True,
        },
    }


def _gen_random(tc_id: str) -> dict:
    """random: 무작위 파라미터 조합."""
    dim = random.choice([64, 128, 256])
    n = random.randint(1, 50)
    top_k = random.randint(0, n + 5)
    chunks, embeddings = _make_chunks(n, dim)
    query_words = random.randint(0, 10)
    query = _rand_content(query_words) if query_words > 0 else ""
    embedder_available = random.choice([True, False])
    query_embedding = _rand_unit_vec(dim) if embedder_available else []
    bm25_weight = round(random.uniform(0.0, 1.0), 2)
    vector_weight = round(random.uniform(0.0, 1.0), 2)

    # expected 결정
    if not query.strip() or not chunks or top_k <= 0:
        exp = {"type": "empty_list"}
    else:
        exp = {
            "type": "search_result",
            "max_length": top_k,
            "sorted_desc": True,
        }

    return {
        "id": tc_id,
        "category": "random",
        "description": f"random: dim={dim}, n={n}, top_k={top_k}, embedder={embedder_available}",
        "query": query,
        "top_k": top_k,
        "chunks": chunks,
        "embeddings": embeddings,
        "bm25_weight": bm25_weight,
        "vector_weight": vector_weight,
        "embedder_available": embedder_available,
        "query_embedding": query_embedding,
        "expected": exp,
    }


# ------------------------------------------------------------------
# 생성 스케줄
# ------------------------------------------------------------------

# (함수, 개수) 튜플 목록 — 합계 10,000건
_SCHEDULE = [
    # normal 3,000건
    (_gen_normal,                        1500),
    (_gen_normal_bm25_only,              1500),
    # boundary 2,000건
    (_gen_boundary_empty_query,           400),
    (_gen_boundary_empty_chunks,          300),
    (_gen_boundary_topk_zero,             300),
    (_gen_boundary_topk_negative,         200),
    (_gen_boundary_single_chunk,          200),
    (_gen_boundary_topk_larger_than_chunks, 300),
    (_gen_boundary_query_no_bm25_hit,     300),
    # invalid 2,000건
    (_gen_invalid_embed_fail,             600),
    (_gen_invalid_zero_query_embedding,   400),
    (_gen_invalid_unfitted_scorer,        600),
    (_gen_invalid_weight_zero,            400),
    # stress 1,500건
    (_gen_stress_large_corpus,            500),
    (_gen_stress_high_top_k,              600),
    (_gen_stress_high_dim,                400),
    # random 1,500건
    (_gen_random,                        1500),
]


def generate_cases(output_dir: Path, total: int = 10000) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "test_cases.jsonl"

    # 스케줄 총합 확인
    schedule_total = sum(cnt for _, cnt in _SCHEDULE)
    if schedule_total != total:
        raise ValueError(
            f"스케줄 합계({schedule_total})가 total({total})과 다릅니다. "
            "_SCHEDULE을 수정하세요."
        )

    print(f"케이스 생성 중... (총 {total:,}건)")

    counter = 0
    category_counts: dict[str, int] = {}

    with open(out_path, "w", encoding="utf-8") as f:
        for gen_fn, count in _SCHEDULE:
            for _ in range(count):
                counter += 1
                tc_id = f"TC-HYBRID-{counter:05d}"
                tc = gen_fn(tc_id)
                f.write(json.dumps(tc, ensure_ascii=False) + "\n")
                cat = tc["category"]
                category_counts[cat] = category_counts.get(cat, 0) + 1

    print(f"생성 완료: {out_path} ({counter:,}건)")
    for cat, cnt in sorted(category_counts.items()):
        print(f"  {cat}: {cnt:,}건")


def main() -> None:
    parser = argparse.ArgumentParser(description="HybridSearcher 모듈 QC 케이스 생성기")
    parser.add_argument(
        "--module",
        default="src/rag/hybrid_search.py",
        help="대상 모듈 경로 (정보 참고용)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10000,
        help="생성할 케이스 수",
    )
    parser.add_argument(
        "--output",
        default="tests/qc/hybrid_search/",
        help="출력 디렉토리",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    generate_cases(output_dir, args.count)


if __name__ == "__main__":
    main()
