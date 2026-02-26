"""BM25Scorer 모듈 QC 테스트 케이스 생성기.

BM25Scorer의 fit(), score(), top_k() 메서드를 대상으로
10,000개의 인풋/아웃풋 테스트 케이스를 자동 생성한다.

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
import random
import string
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

random.seed(42)

# 코드 검색에 사용하는 샘플 도메인 단어
CODE_WORDS = [
    "function", "class", "method", "variable", "import", "return",
    "async", "await", "def", "for", "while", "if", "else",
    "getUserById", "fetchData", "processInput", "handleError",
    "authenticate", "database", "connection", "endpoint",
    "token", "session", "cache", "index", "search", "query",
    "parse", "serialize", "deserialize", "validate", "filter",
    "map", "reduce", "sort", "chunk", "embed", "score",
    "사용자", "인증", "데이터", "검색", "쿼리",
]

PYTHON_SNIPPETS = [
    "def get_user(user_id: int) -> User:\n    return db.query(user_id)",
    "class AuthService:\n    def authenticate(self, token: str) -> bool:\n        return verify_token(token)",
    "async def fetch_data(url: str) -> dict:\n    async with session.get(url) as resp:\n        return await resp.json()",
    "def process_input(data: list) -> list:\n    return [validate(item) for item in data if item is not None]",
    "def bm25_score(query: str, doc: str) -> float:\n    tokens = tokenize(query)\n    return sum(idf[t] for t in tokens)",
    "import os\nimport sys\nfrom pathlib import Path",
    "MAX_RETRIES = 3\nTIMEOUT = 30\nBASE_URL = os.getenv('API_URL')",
    "def _tokenize(text: str) -> list[str]:\n    text = camel_re.sub(' ', text)\n    return text.lower().split()",
]

NON_CODE_SNIPPETS = [
    "The quick brown fox jumps over the lazy dog",
    "Lorem ipsum dolor sit amet consectetur adipiscing elit",
    "Hello world this is a test document",
    "Python programming language tutorial for beginners",
    "Data structures and algorithms in computer science",
]


@dataclass
class ScorerTestCase:
    """BM25Scorer QC 테스트 케이스."""

    id: str
    category: str
    method: str          # "fit", "score", "top_k", "fit_score", "fit_top_k"
    documents: list[str] | None
    query: str | None
    doc_index: int | None
    k: int | None
    description: str
    expected: dict


# ---------------------------------------------------------------------------
# 케이스 생성 헬퍼
# ---------------------------------------------------------------------------

def _rand_doc(n_words: int = 20) -> str:
    """무작위 단어로 문서를 생성한다."""
    return " ".join(random.choices(CODE_WORDS, k=n_words))


def _rand_docs(count: int, words_per_doc: int = 20) -> list[str]:
    """무작위 문서 목록을 생성한다."""
    return [_rand_doc(words_per_doc) for _ in range(count)]


def _rand_query(n_words: int = 3) -> str:
    """무작위 쿼리를 생성한다."""
    return " ".join(random.choices(CODE_WORDS, k=n_words))


# ---------------------------------------------------------------------------
# 카테고리별 생성 함수
# ---------------------------------------------------------------------------

def _gen_normal_cases(count: int) -> list[ScorerTestCase]:
    """정상 입력 케이스를 생성한다."""
    cases: list[ScorerTestCase] = []
    random.seed(10)

    # 1) fit 후 score — 유효 쿼리 + 유효 인덱스
    # BM25Okapi는 음수 점수가 나올 수 있으므로 min 조건 제거
    for i in range(count // 5):
        n_docs = random.randint(3, 20)
        docs = _rand_docs(n_docs)
        idx = random.randint(0, n_docs - 1)
        query = _rand_query(random.randint(1, 5))
        cases.append(ScorerTestCase(
            id=f"TC-NORMAL-{len(cases)+1:05d}",
            category="normal",
            method="fit_score",
            documents=docs,
            query=query,
            doc_index=idx,
            k=None,
            description="fit 후 score — 유효 인덱스",
            expected={"type": "float", "no_exception": True},
        ))

    # 2) fit 후 top_k — 다양한 k 값
    for i in range(count // 5):
        n_docs = random.randint(5, 30)
        docs = _rand_docs(n_docs)
        k = random.randint(1, min(10, n_docs))
        query = _rand_query(random.randint(1, 4))
        cases.append(ScorerTestCase(
            id=f"TC-NORMAL-{len(cases)+1:05d}",
            category="normal",
            method="fit_top_k",
            documents=docs,
            query=query,
            doc_index=None,
            k=k,
            description=f"fit 후 top_k(k={k}) — 유효 쿼리",
            expected={
                "type": "list_of_tuples",
                "max_length": k,
                "no_exception": True,
                "sorted_desc": True,
            },
        ))

    # 3) 실제 Python 코드 스니펫으로 fit + top_k
    for i in range(count // 5):
        docs = random.sample(PYTHON_SNIPPETS, min(len(PYTHON_SNIPPETS), random.randint(3, 6)))
        k = random.randint(1, len(docs))
        query = random.choice(CODE_WORDS[:20])
        cases.append(ScorerTestCase(
            id=f"TC-NORMAL-{len(cases)+1:05d}",
            category="normal",
            method="fit_top_k",
            documents=docs,
            query=query,
            doc_index=None,
            k=k,
            description="Python 코드 스니펫으로 top_k",
            expected={
                "type": "list_of_tuples",
                "max_length": k,
                "no_exception": True,
                "sorted_desc": True,
            },
        ))

    # 4) camelCase 쿼리 토큰화
    camel_queries = [
        "getUserById", "fetchDataFromServer", "processInputData",
        "handleErrorResponse", "authenticateUser", "validateToken",
        "parseJsonResponse", "serializeToDict",
    ]
    for q in camel_queries:
        docs = _rand_docs(10)
        cases.append(ScorerTestCase(
            id=f"TC-NORMAL-{len(cases)+1:05d}",
            category="normal",
            method="fit_top_k",
            documents=docs,
            query=q,
            doc_index=None,
            k=5,
            description=f"camelCase 쿼리 top_k: {q}",
            expected={
                "type": "list_of_tuples",
                "no_exception": True,
                "sorted_desc": True,
            },
        ))

    # 5) snake_case 쿼리
    snake_queries = [
        "get_user_by_id", "fetch_data_from_server",
        "process_input_data", "handle_error",
    ]
    for q in snake_queries:
        docs = _rand_docs(10)
        cases.append(ScorerTestCase(
            id=f"TC-NORMAL-{len(cases)+1:05d}",
            category="normal",
            method="fit_top_k",
            documents=docs,
            query=q,
            doc_index=None,
            k=5,
            description=f"snake_case 쿼리 top_k: {q}",
            expected={
                "type": "list_of_tuples",
                "no_exception": True,
                "sorted_desc": True,
            },
        ))

    # 6) 한글 쿼리
    korean_queries = ["사용자 인증", "데이터 검색", "쿼리 처리"]
    for q in korean_queries:
        docs = [_rand_doc() + " " + random.choice(["사용자", "인증", "데이터"]) for _ in range(10)]
        cases.append(ScorerTestCase(
            id=f"TC-NORMAL-{len(cases)+1:05d}",
            category="normal",
            method="fit_top_k",
            documents=docs,
            query=q,
            doc_index=None,
            k=5,
            description=f"한글 쿼리 top_k: {q}",
            expected={
                "type": "list_of_tuples",
                "no_exception": True,
                "sorted_desc": True,
            },
        ))

    # 나머지 채우기
    while len(cases) < count:
        n_docs = random.randint(2, 50)
        docs = _rand_docs(n_docs)
        method = random.choice(["fit_score", "fit_top_k"])
        if method == "fit_score":
            idx = random.randint(0, n_docs - 1)
            cases.append(ScorerTestCase(
                id=f"TC-NORMAL-{len(cases)+1:05d}",
                category="normal",
                method=method,
                documents=docs,
                query=_rand_query(),
                doc_index=idx,
                k=None,
                description="랜덤 정상 fit+score",
                expected={"type": "float", "no_exception": True},
            ))
        else:
            k = random.randint(1, n_docs)
            cases.append(ScorerTestCase(
                id=f"TC-NORMAL-{len(cases)+1:05d}",
                category="normal",
                method=method,
                documents=docs,
                query=_rand_query(),
                doc_index=None,
                k=k,
                description="랜덤 정상 fit+top_k",
                expected={
                    "type": "list_of_tuples",
                    "max_length": k,
                    "no_exception": True,
                    "sorted_desc": True,
                },
            ))

    return cases[:count]


def _gen_boundary_cases(count: int) -> list[ScorerTestCase]:
    """경계값 케이스를 생성한다."""
    cases: list[ScorerTestCase] = []
    random.seed(20)

    # 1) 빈 코퍼스로 fit — score는 0.0 반환해야 함
    cases.append(ScorerTestCase(
        id=f"TC-BOUNDARY-{len(cases)+1:05d}",
        category="boundary",
        method="fit_score",
        documents=[],
        query="hello",
        doc_index=0,
        k=None,
        description="빈 코퍼스 fit 후 score",
        expected={"type": "float", "exact": 0.0, "no_exception": True},
    ))

    # 2) 빈 코퍼스로 fit — top_k는 빈 리스트 반환
    cases.append(ScorerTestCase(
        id=f"TC-BOUNDARY-{len(cases)+1:05d}",
        category="boundary",
        method="fit_top_k",
        documents=[],
        query="hello",
        doc_index=None,
        k=5,
        description="빈 코퍼스 fit 후 top_k",
        expected={"type": "empty_list", "no_exception": True},
    ))

    # 3) 빈 쿼리로 score — 0.0 반환
    docs = _rand_docs(5)
    cases.append(ScorerTestCase(
        id=f"TC-BOUNDARY-{len(cases)+1:05d}",
        category="boundary",
        method="fit_score",
        documents=docs,
        query="",
        doc_index=0,
        k=None,
        description="빈 쿼리 score",
        expected={"type": "float", "exact": 0.0, "no_exception": True},
    ))

    # 4) 빈 쿼리로 top_k — 빈 리스트 반환
    cases.append(ScorerTestCase(
        id=f"TC-BOUNDARY-{len(cases)+1:05d}",
        category="boundary",
        method="fit_top_k",
        documents=docs,
        query="",
        doc_index=None,
        k=5,
        description="빈 쿼리 top_k",
        expected={"type": "empty_list", "no_exception": True},
    ))

    # 5) 공백 쿼리 — 0.0 / 빈 리스트
    for q in ["   ", "\t", "\n", "  \n  "]:
        cases.append(ScorerTestCase(
            id=f"TC-BOUNDARY-{len(cases)+1:05d}",
            category="boundary",
            method="fit_score",
            documents=docs,
            query=q,
            doc_index=0,
            k=None,
            description=f"공백 쿼리 score (repr={repr(q)})",
            expected={"type": "float", "exact": 0.0, "no_exception": True},
        ))
        cases.append(ScorerTestCase(
            id=f"TC-BOUNDARY-{len(cases)+1:05d}",
            category="boundary",
            method="fit_top_k",
            documents=docs,
            query=q,
            doc_index=None,
            k=5,
            description=f"공백 쿼리 top_k (repr={repr(q)})",
            expected={"type": "empty_list", "no_exception": True},
        ))

    # 6) doc_index 경계: 0 (첫 번째), corpus_size-1 (마지막)
    docs = _rand_docs(10)
    for idx in [0, 9]:
        cases.append(ScorerTestCase(
            id=f"TC-BOUNDARY-{len(cases)+1:05d}",
            category="boundary",
            method="fit_score",
            documents=docs,
            query="search query",
            doc_index=idx,
            k=None,
            description=f"doc_index 경계값: {idx}",
            expected={"type": "float", "no_exception": True},
        ))

    # 7) doc_index 범위 초과 — 0.0 반환
    for idx in [-1, 10, 100, -100]:
        cases.append(ScorerTestCase(
            id=f"TC-BOUNDARY-{len(cases)+1:05d}",
            category="boundary",
            method="fit_score",
            documents=docs,
            query="search query",
            doc_index=idx,
            k=None,
            description=f"doc_index 범위 초과: {idx}",
            expected={"type": "float", "exact": 0.0, "no_exception": True},
        ))

    # 8) top_k = 1 (최소)
    cases.append(ScorerTestCase(
        id=f"TC-BOUNDARY-{len(cases)+1:05d}",
        category="boundary",
        method="fit_top_k",
        documents=_rand_docs(10),
        query="search query function",
        doc_index=None,
        k=1,
        description="top_k = 1 (최소값)",
        expected={"type": "list_of_tuples", "max_length": 1, "no_exception": True},
    ))

    # 9) top_k = 0 — 빈 리스트 반환
    cases.append(ScorerTestCase(
        id=f"TC-BOUNDARY-{len(cases)+1:05d}",
        category="boundary",
        method="fit_top_k",
        documents=_rand_docs(10),
        query="search query",
        doc_index=None,
        k=0,
        description="top_k = 0",
        expected={"type": "empty_list", "no_exception": True},
    ))

    # 10) top_k > corpus_size — corpus_size만큼만 반환
    n_docs = 5
    cases.append(ScorerTestCase(
        id=f"TC-BOUNDARY-{len(cases)+1:05d}",
        category="boundary",
        method="fit_top_k",
        documents=_rand_docs(n_docs),
        query="function class method",
        doc_index=None,
        k=100,  # corpus_size(5) 초과
        description="top_k > corpus_size",
        expected={
            "type": "list_of_tuples",
            "max_length": n_docs,
            "no_exception": True,
        },
    ))

    # 11) 문서 1개 코퍼스
    cases.append(ScorerTestCase(
        id=f"TC-BOUNDARY-{len(cases)+1:05d}",
        category="boundary",
        method="fit_score",
        documents=["single document with search terms"],
        query="search",
        doc_index=0,
        k=None,
        description="단일 문서 코퍼스 score",
        expected={"type": "float", "no_exception": True},
    ))

    # 12) 쿼리 단어가 코퍼스에 없음 — 0.0 반환 (BM25 IDF 특성)
    cases.append(ScorerTestCase(
        id=f"TC-BOUNDARY-{len(cases)+1:05d}",
        category="boundary",
        method="fit_top_k",
        documents=["hello world foo bar", "python code class function"],
        query="zzz_nonexistent_word_qqq",
        doc_index=None,
        k=5,
        description="코퍼스에 없는 단어 쿼리",
        expected={"type": "empty_list", "no_exception": True},
    ))

    # 13) fit 없이 score 호출 — 0.0 반환
    cases.append(ScorerTestCase(
        id=f"TC-BOUNDARY-{len(cases)+1:05d}",
        category="boundary",
        method="score",
        documents=None,  # fit 없음
        query="hello",
        doc_index=0,
        k=None,
        description="fit 없이 score 호출 — 0.0",
        expected={"type": "float", "exact": 0.0, "no_exception": True},
    ))

    # 14) fit 없이 top_k 호출 — 빈 리스트 반환
    cases.append(ScorerTestCase(
        id=f"TC-BOUNDARY-{len(cases)+1:05d}",
        category="boundary",
        method="top_k",
        documents=None,  # fit 없음
        query="hello",
        doc_index=None,
        k=5,
        description="fit 없이 top_k 호출 — 빈 리스트",
        expected={"type": "empty_list", "no_exception": True},
    ))

    # 15) top_k 음수 k — 빈 리스트
    for k_val in [-1, -10, -100]:
        cases.append(ScorerTestCase(
            id=f"TC-BOUNDARY-{len(cases)+1:05d}",
            category="boundary",
            method="fit_top_k",
            documents=_rand_docs(5),
            query="search query",
            doc_index=None,
            k=k_val,
            description=f"음수 k={k_val}",
            expected={"type": "empty_list", "no_exception": True},
        ))

    # 나머지 채우기
    while len(cases) < count:
        variant = random.randint(0, 4)
        if variant == 0:
            # 빈 문서 포함 코퍼스
            docs = [""] * random.randint(1, 5) + _rand_docs(random.randint(1, 5))
            cases.append(ScorerTestCase(
                id=f"TC-BOUNDARY-{len(cases)+1:05d}",
                category="boundary",
                method="fit_top_k",
                documents=docs,
                query=_rand_query(),
                doc_index=None,
                k=3,
                description="빈 문서 포함 코퍼스 top_k",
                expected={"type": "list_of_tuples", "no_exception": True},
            ))
        elif variant == 1:
            # 모든 문서가 동일
            docs = ["same document content"] * random.randint(3, 10)
            cases.append(ScorerTestCase(
                id=f"TC-BOUNDARY-{len(cases)+1:05d}",
                category="boundary",
                method="fit_top_k",
                documents=docs,
                query="same document",
                doc_index=None,
                k=5,
                description="중복 문서 코퍼스",
                expected={"type": "list_of_tuples", "no_exception": True},
            ))
        elif variant == 2:
            # k가 정확히 corpus_size
            n = random.randint(3, 10)
            cases.append(ScorerTestCase(
                id=f"TC-BOUNDARY-{len(cases)+1:05d}",
                category="boundary",
                method="fit_top_k",
                documents=_rand_docs(n),
                query=_rand_query(),
                doc_index=None,
                k=n,
                description=f"k = corpus_size = {n}",
                expected={"type": "list_of_tuples", "max_length": n, "no_exception": True},
            ))
        elif variant == 3:
            # doc_index = corpus_size - 1 (마지막)
            n = random.randint(2, 10)
            docs = _rand_docs(n)
            cases.append(ScorerTestCase(
                id=f"TC-BOUNDARY-{len(cases)+1:05d}",
                category="boundary",
                method="fit_score",
                documents=docs,
                query=_rand_query(),
                doc_index=n - 1,
                k=None,
                description=f"doc_index = corpus_size-1 = {n-1}",
                expected={"type": "float", "no_exception": True},
            ))
        else:
            # 특수문자만으로 이루어진 쿼리
            query = "!@#$%^&*()"
            docs = _rand_docs(5)
            cases.append(ScorerTestCase(
                id=f"TC-BOUNDARY-{len(cases)+1:05d}",
                category="boundary",
                method="fit_top_k",
                documents=docs,
                query=query,
                doc_index=None,
                k=5,
                description="특수문자만으로 이루어진 쿼리",
                expected={"type": "empty_list", "no_exception": True},
            ))

    return cases[:count]


def _gen_invalid_cases(count: int) -> list[ScorerTestCase]:
    """잘못된 입력 케이스를 생성한다."""
    cases: list[ScorerTestCase] = []
    random.seed(30)

    # 1) fit 전에 score 호출 — 0.0 반환 (예외 없음)
    for q in ["hello", "getUserById", "function class", ""]:
        cases.append(ScorerTestCase(
            id=f"TC-INVALID-{len(cases)+1:05d}",
            category="invalid",
            method="score",
            documents=None,
            query=q,
            doc_index=0,
            k=None,
            description=f"fit 전 score 호출 (query={repr(q[:20])})",
            expected={"type": "float", "exact": 0.0, "no_exception": True},
        ))

    # 2) fit 전에 top_k 호출 — 빈 리스트 (예외 없음)
    for q in ["hello", "search function", ""]:
        cases.append(ScorerTestCase(
            id=f"TC-INVALID-{len(cases)+1:05d}",
            category="invalid",
            method="top_k",
            documents=None,
            query=q,
            doc_index=None,
            k=5,
            description=f"fit 전 top_k 호출 (query={repr(q[:20])})",
            expected={"type": "empty_list", "no_exception": True},
        ))

    # 3) 범위 벗어난 doc_index — 0.0 반환
    docs = _rand_docs(5)
    invalid_indices = [-1, 5, 6, 100, -100, 999]
    for idx in invalid_indices:
        cases.append(ScorerTestCase(
            id=f"TC-INVALID-{len(cases)+1:05d}",
            category="invalid",
            method="fit_score",
            documents=docs,
            query="search query",
            doc_index=idx,
            k=None,
            description=f"범위 밖 doc_index={idx} (corpus=5)",
            expected={"type": "float", "exact": 0.0, "no_exception": True},
        ))

    # 4) 음수 k top_k — 빈 리스트
    docs = _rand_docs(10)
    for k_val in [-1, -5, -100]:
        cases.append(ScorerTestCase(
            id=f"TC-INVALID-{len(cases)+1:05d}",
            category="invalid",
            method="fit_top_k",
            documents=docs,
            query="search query",
            doc_index=None,
            k=k_val,
            description=f"음수 k={k_val} top_k",
            expected={"type": "empty_list", "no_exception": True},
        ))

    # 5) 특수문자만 있는 쿼리 — 토큰 없음 → 0.0/빈 리스트
    special_queries = [
        "!@#$%^&*()", "---===---", "...", "///", "\\\\\\",
        "\x00\x01\x02", "   \t\n   ",
    ]
    for q in special_queries:
        docs = _rand_docs(5)
        cases.append(ScorerTestCase(
            id=f"TC-INVALID-{len(cases)+1:05d}",
            category="invalid",
            method="fit_score",
            documents=docs,
            query=q,
            doc_index=0,
            k=None,
            description=f"특수문자 쿼리 score (repr={repr(q[:15])})",
            expected={"type": "float", "exact": 0.0, "no_exception": True},
        ))
        cases.append(ScorerTestCase(
            id=f"TC-INVALID-{len(cases)+1:05d}",
            category="invalid",
            method="fit_top_k",
            documents=docs,
            query=q,
            doc_index=None,
            k=5,
            description=f"특수문자 쿼리 top_k (repr={repr(q[:15])})",
            expected={"type": "empty_list", "no_exception": True},
        ))

    # 6) 빈 문서만 있는 코퍼스
    empty_docs = ["", "", ""]
    cases.append(ScorerTestCase(
        id=f"TC-INVALID-{len(cases)+1:05d}",
        category="invalid",
        method="fit_score",
        documents=empty_docs,
        query="hello world",
        doc_index=0,
        k=None,
        description="빈 문서만 있는 코퍼스 score",
        expected={"type": "float", "no_exception": True},
    ))
    cases.append(ScorerTestCase(
        id=f"TC-INVALID-{len(cases)+1:05d}",
        category="invalid",
        method="fit_top_k",
        documents=empty_docs,
        query="hello world",
        doc_index=None,
        k=5,
        description="빈 문서만 있는 코퍼스 top_k",
        expected={"type": "list_of_tuples", "no_exception": True},
    ))

    # 7) k=0 — 빈 리스트
    cases.append(ScorerTestCase(
        id=f"TC-INVALID-{len(cases)+1:05d}",
        category="invalid",
        method="fit_top_k",
        documents=_rand_docs(10),
        query="hello",
        doc_index=None,
        k=0,
        description="k=0 top_k",
        expected={"type": "empty_list", "no_exception": True},
    ))

    # 나머지 채우기
    while len(cases) < count:
        variant = random.randint(0, 3)
        if variant == 0:
            # 랜덤 범위 밖 인덱스
            n = random.randint(1, 10)
            idx = random.choice([-1, n, n + random.randint(1, 100)])
            cases.append(ScorerTestCase(
                id=f"TC-INVALID-{len(cases)+1:05d}",
                category="invalid",
                method="fit_score",
                documents=_rand_docs(n),
                query=_rand_query(),
                doc_index=idx,
                k=None,
                description=f"랜덤 범위 밖 인덱스 (n={n}, idx={idx})",
                expected={"type": "float", "exact": 0.0, "no_exception": True},
            ))
        elif variant == 1:
            # fit 전 호출
            method = random.choice(["score", "top_k"])
            cases.append(ScorerTestCase(
                id=f"TC-INVALID-{len(cases)+1:05d}",
                category="invalid",
                method=method,
                documents=None,
                query=_rand_query(),
                doc_index=0 if method == "score" else None,
                k=5 if method == "top_k" else None,
                description=f"fit 전 {method} 호출",
                expected={
                    "type": "float" if method == "score" else "empty_list",
                    "exact": 0.0 if method == "score" else None,
                    "no_exception": True,
                },
            ))
        elif variant == 2:
            # 숫자/특수문자만 있는 쿼리
            query = "".join(random.choices(string.punctuation, k=random.randint(3, 15)))
            cases.append(ScorerTestCase(
                id=f"TC-INVALID-{len(cases)+1:05d}",
                category="invalid",
                method="fit_top_k",
                documents=_rand_docs(5),
                query=query,
                doc_index=None,
                k=5,
                description="구두점만 있는 쿼리",
                expected={"type": "empty_list", "no_exception": True},
            ))
        else:
            # 음수 k
            k_val = random.randint(-100, -1)
            cases.append(ScorerTestCase(
                id=f"TC-INVALID-{len(cases)+1:05d}",
                category="invalid",
                method="fit_top_k",
                documents=_rand_docs(5),
                query=_rand_query(),
                doc_index=None,
                k=k_val,
                description=f"음수 k={k_val}",
                expected={"type": "empty_list", "no_exception": True},
            ))

    return cases[:count]


def _gen_stress_cases(count: int) -> list[ScorerTestCase]:
    """극단적 입력 스트레스 케이스를 생성한다."""
    cases: list[ScorerTestCase] = []
    random.seed(40)

    # 1) 대량 문서 (1,000건)
    for n_docs in [100, 500, 1000]:
        docs = _rand_docs(n_docs, words_per_doc=50)
        k = min(20, n_docs)
        cases.append(ScorerTestCase(
            id=f"TC-STRESS-{len(cases)+1:05d}",
            category="stress",
            method="fit_top_k",
            documents=docs,
            query="function class method search",
            doc_index=None,
            k=k,
            description=f"대량 문서 {n_docs}개 top_k",
            expected={"type": "list_of_tuples", "max_length": k, "no_exception": True},
        ))

    # 2) 매우 긴 문서
    for doc_len in [1000, 5000, 10000]:
        long_doc = " ".join(random.choices(CODE_WORDS, k=doc_len))
        docs = [long_doc] + _rand_docs(4)
        cases.append(ScorerTestCase(
            id=f"TC-STRESS-{len(cases)+1:05d}",
            category="stress",
            method="fit_top_k",
            documents=docs,
            query="function search query",
            doc_index=None,
            k=3,
            description=f"매우 긴 문서 ({doc_len} 단어)",
            expected={"type": "list_of_tuples", "no_exception": True},
        ))

    # 3) 매우 긴 쿼리
    for q_len in [100, 500, 1000]:
        long_query = " ".join(random.choices(CODE_WORDS, k=q_len))
        docs = _rand_docs(20)
        cases.append(ScorerTestCase(
            id=f"TC-STRESS-{len(cases)+1:05d}",
            category="stress",
            method="fit_top_k",
            documents=docs,
            query=long_query,
            doc_index=None,
            k=10,
            description=f"매우 긴 쿼리 ({q_len} 단어)",
            expected={"type": "list_of_tuples", "no_exception": True},
        ))

    # 4) fit 반복 호출 (재학습)
    # 여러 번 fit 후 마지막 top_k
    base_docs = _rand_docs(10)
    cases.append(ScorerTestCase(
        id=f"TC-STRESS-{len(cases)+1:05d}",
        category="stress",
        method="fit_top_k",
        documents=base_docs,
        query="search function",
        doc_index=None,
        k=5,
        description="재학습 시나리오 (fit 후 top_k)",
        expected={"type": "list_of_tuples", "no_exception": True},
    ))

    # 5) 모든 단어가 같은 대량 코퍼스 (IDF 극단값)
    for n in [50, 200]:
        docs = ["function function function"] * n
        cases.append(ScorerTestCase(
            id=f"TC-STRESS-{len(cases)+1:05d}",
            category="stress",
            method="fit_top_k",
            documents=docs,
            query="function",
            doc_index=None,
            k=10,
            description=f"동일 단어 {n}개 문서 (IDF 극단)",
            expected={"type": "list_of_tuples", "no_exception": True},
        ))

    # 6) 매우 큰 top_k 값
    docs = _rand_docs(100)
    for k_val in [1000, 10000, 100000]:
        cases.append(ScorerTestCase(
            id=f"TC-STRESS-{len(cases)+1:05d}",
            category="stress",
            method="fit_top_k",
            documents=docs,
            query="function search",
            doc_index=None,
            k=k_val,
            description=f"매우 큰 k={k_val} (corpus=100)",
            expected={"type": "list_of_tuples", "max_length": 100, "no_exception": True},
        ))

    # 7) 실제 코드 파일 수준 (긴 Python 스니펫)
    long_code = "\n".join([
        "def " + "func_" + str(i) + "(x, y):\n    return x + y"
        for i in range(100)
    ])
    docs = [long_code] + _rand_docs(9)
    cases.append(ScorerTestCase(
        id=f"TC-STRESS-{len(cases)+1:05d}",
        category="stress",
        method="fit_top_k",
        documents=docs,
        query="def function return",
        doc_index=None,
        k=5,
        description="실제 코드 파일 수준 문서",
        expected={"type": "list_of_tuples", "no_exception": True},
    ))

    # 나머지 채우기
    while len(cases) < count:
        n_docs = random.randint(100, 500)
        docs = _rand_docs(n_docs, words_per_doc=random.randint(20, 100))
        k = random.randint(1, min(50, n_docs))
        cases.append(ScorerTestCase(
            id=f"TC-STRESS-{len(cases)+1:05d}",
            category="stress",
            method="fit_top_k",
            documents=docs,
            query=_rand_query(random.randint(1, 10)),
            doc_index=None,
            k=k,
            description=f"랜덤 대량 문서 {n_docs}개 top_k(k={k})",
            expected={"type": "list_of_tuples", "max_length": k, "no_exception": True},
        ))

    return cases[:count]


def _gen_random_cases(count: int) -> list[ScorerTestCase]:
    """무작위 퍼징 케이스를 생성한다."""
    cases: list[ScorerTestCase] = []
    random.seed(50)

    def _rand_string(max_len: int = 200) -> str:
        length = random.randint(0, max_len)
        chars = string.printable + "한글テスト中文"
        return "".join(random.choices(chars, k=length))

    for i in range(count):
        tc_id = f"TC-RANDOM-{i+1:05d}"
        variant = random.random()

        if variant < 0.3:
            # 무작위 문서 + 무작위 쿼리로 top_k
            n_docs = random.randint(1, 50)
            docs = [_rand_string() for _ in range(n_docs)]
            k = random.randint(1, 20)
            cases.append(ScorerTestCase(
                id=tc_id,
                category="random",
                method="fit_top_k",
                documents=docs,
                query=_rand_string(100),
                doc_index=None,
                k=k,
                description="완전 무작위 퍼징 top_k",
                expected={"type": "list_of_tuples", "no_exception": True},
            ))
        elif variant < 0.5:
            # 무작위 문서 + 무작위 인덱스로 score
            n_docs = random.randint(1, 50)
            docs = [_rand_string() for _ in range(n_docs)]
            idx = random.randint(-10, n_docs + 10)
            cases.append(ScorerTestCase(
                id=tc_id,
                category="random",
                method="fit_score",
                documents=docs,
                query=_rand_string(100),
                doc_index=idx,
                k=None,
                description="완전 무작위 퍼징 score",
                expected={"type": "float", "no_exception": True},
            ))
        elif variant < 0.65:
            # fit 없이 호출
            method = random.choice(["score", "top_k"])
            cases.append(ScorerTestCase(
                id=tc_id,
                category="random",
                method=method,
                documents=None,
                query=_rand_string(50),
                doc_index=0 if method == "score" else None,
                k=random.randint(-5, 10) if method == "top_k" else None,
                description=f"fit 없이 랜덤 {method} 퍼징",
                expected={"type": "list", "no_exception": True},
            ))
        elif variant < 0.80:
            # 코드 스니펫 혼합
            docs = random.sample(PYTHON_SNIPPETS + NON_CODE_SNIPPETS, random.randint(2, min(6, len(PYTHON_SNIPPETS))))
            k = random.randint(1, len(docs))
            cases.append(ScorerTestCase(
                id=tc_id,
                category="random",
                method="fit_top_k",
                documents=docs,
                query=random.choice(CODE_WORDS),
                doc_index=None,
                k=k,
                description="코드 스니펫 혼합 퍼징",
                expected={"type": "list_of_tuples", "no_exception": True},
            ))
        else:
            # 극단적 랜덤
            n_docs = random.randint(0, 20)
            docs = [_rand_string() for _ in range(n_docs)] if n_docs > 0 else []
            k_val = random.randint(-100, 100)
            cases.append(ScorerTestCase(
                id=tc_id,
                category="random",
                method="fit_top_k",
                documents=docs,
                query=_rand_string(200),
                doc_index=None,
                k=k_val,
                description="극단적 무작위 퍼징",
                expected={"type": "list", "no_exception": True},
            ))

    return cases


# ---------------------------------------------------------------------------
# 메인 생성 함수
# ---------------------------------------------------------------------------

def generate_all_cases(total: int = 10000) -> list[ScorerTestCase]:
    """카테고리별 비율에 맞춰 전체 케이스를 생성한다."""
    counts = {
        "normal":   int(total * 0.30),
        "boundary": int(total * 0.20),
        "invalid":  int(total * 0.20),
        "stress":   int(total * 0.15),
        "random":   int(total * 0.15),
    }
    diff = total - sum(counts.values())
    counts["normal"] += diff

    print("카테고리별 생성 계획:")
    for cat, n in counts.items():
        print(f"  {cat}: {n}건")

    all_cases: list[ScorerTestCase] = []
    all_cases.extend(_gen_normal_cases(counts["normal"]))
    all_cases.extend(_gen_boundary_cases(counts["boundary"]))
    all_cases.extend(_gen_invalid_cases(counts["invalid"]))
    all_cases.extend(_gen_stress_cases(counts["stress"]))
    all_cases.extend(_gen_random_cases(counts["random"]))

    for i, tc in enumerate(all_cases):
        tc.id = f"TC-MODULE-{i+1:05d}"

    return all_cases


def _safe_dict(tc: ScorerTestCase) -> dict:
    """JSON 직렬화 안전한 딕셔너리로 변환한다."""
    d = asdict(tc)
    # 문자열 필드의 직렬화 불가 문자 처리
    for key in ["query"]:
        if d.get(key) is not None:
            try:
                json.dumps(d[key])
            except (UnicodeEncodeError, ValueError):
                d[key] = d[key].encode("utf-8", errors="replace").decode("utf-8")
    if d.get("documents"):
        safe_docs = []
        for doc in d["documents"]:
            try:
                json.dumps(doc)
                safe_docs.append(doc)
            except (UnicodeEncodeError, ValueError):
                safe_docs.append(doc.encode("utf-8", errors="replace").decode("utf-8"))
        d["documents"] = safe_docs
    return d


def save_cases_jsonl(cases: list[ScorerTestCase], output_path: Path) -> None:
    """테스트 케이스를 JSONL 형식으로 저장한다."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for tc in cases:
            f.write(json.dumps(_safe_dict(tc), ensure_ascii=False) + "\n")
    print(f"저장 완료: {output_path} ({len(cases)}건)")


def main() -> None:
    """CLI 진입점."""
    parser = argparse.ArgumentParser(description="BM25Scorer QC 테스트 케이스 생성기")
    parser.add_argument("--module", default="src/rag/scorer.py", help="대상 모듈 경로")
    parser.add_argument("--count", type=int, default=10000, help="생성할 케이스 수")
    parser.add_argument("--output", default="tests/qc/scorer/", help="출력 디렉토리")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_path = output_dir / "test_cases.jsonl"

    print(f"대상 모듈: {args.module}")
    print(f"케이스 수: {args.count:,}건")
    print(f"출력 경로: {output_path}")
    print()

    cases = generate_all_cases(args.count)
    save_cases_jsonl(cases, output_path)

    print(f"\n생성 완료: 총 {len(cases):,}건")


if __name__ == "__main__":
    main()
