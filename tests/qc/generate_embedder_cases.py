"""AnthropicEmbedder 모듈 QC 테스트 케이스 생성기.

AnthropicEmbedder의 embed(texts) 메서드를 대상으로
10,000개의 인풋/아웃풋 테스트 케이스를 자동 생성한다.

카테고리별 비율:
- normal:   3,000건 (30%)
- boundary: 2,000건 (20%)
- invalid:  2,000건 (20%)
- stress:   1,500건 (15%)
- random:   1,500건 (15%)

주의: embed()는 async + 실제 API 호출이므로 QC 실행기에서 httpx 모킹 처리.
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

# 샘플 텍스트 도메인
CODE_TEXTS = [
    "def get_user(user_id: int) -> User:\n    return db.query(user_id)",
    "class AuthService:\n    def authenticate(self, token: str) -> bool:\n        return verify_token(token)",
    "async def fetch_data(url: str) -> dict:\n    async with session.get(url) as resp:\n        return await resp.json()",
    "import os\nimport sys\nfrom pathlib import Path",
    "MAX_RETRIES = 3\nTIMEOUT = 30\nBASE_URL = os.getenv('API_URL')",
    "def bm25_score(query: str, doc: str) -> float:\n    tokens = tokenize(query)\n    return sum(idf[t] for t in tokens)",
    "사용자 인증 처리 함수입니다.",
    "データベース接続の初期化",
    "Hello world this is a test",
    "The quick brown fox jumps over the lazy dog",
]

NATURAL_TEXTS = [
    "Python programming language for beginners",
    "Machine learning and deep learning fundamentals",
    "Web development with React and TypeScript",
    "Database optimization techniques",
    "Cloud infrastructure and deployment",
    "Security best practices for web applications",
    "API design and RESTful services",
    "Unit testing and test-driven development",
    "Code review and refactoring strategies",
    "DevOps and continuous integration",
]

MULTILANG_TEXTS = [
    "안녕하세요 반갑습니다 한국어 텍스트",
    "日本語のテキストです",
    "中文文本示例",
    "العربية نص",
    "Привет мир текст",
    "Bonjour monde texte français",
    "Hola mundo texto español",
    "Ciao mondo testo italiano",
]


@dataclass
class EmbedderTestCase:
    """AnthropicEmbedder QC 테스트 케이스."""

    id: str
    category: str
    texts: list | None          # embed()에 전달할 텍스트 목록
    api_scenario: str           # "success" | "api_key_missing" | "http_4xx" | "http_5xx" | "network_error"
    description: str
    expected: dict


# ---------------------------------------------------------------------------
# 케이스 생성 헬퍼
# ---------------------------------------------------------------------------

def _rand_text(min_chars: int = 10, max_chars: int = 500) -> str:
    """무작위 텍스트를 생성한다."""
    length = random.randint(min_chars, max_chars)
    return "".join(random.choices(string.ascii_letters + string.digits + " \n", k=length))


def _rand_texts(count: int, min_chars: int = 10, max_chars: int = 200) -> list[str]:
    """무작위 텍스트 목록을 생성한다."""
    return [_rand_text(min_chars, max_chars) for _ in range(count)]


def _sample_texts(count: int) -> list[str]:
    """코드/자연어/다국어 샘플에서 무작위 선택한다."""
    pool = CODE_TEXTS + NATURAL_TEXTS + MULTILANG_TEXTS
    if count <= len(pool):
        return random.sample(pool, count)
    return [random.choice(pool) for _ in range(count)]


# ---------------------------------------------------------------------------
# 카테고리별 생성
# ---------------------------------------------------------------------------

def _gen_normal_cases(count: int) -> list[EmbedderTestCase]:
    """정상 입력 케이스를 생성한다."""
    cases: list[EmbedderTestCase] = []
    random.seed(10)

    # 1) 단일 텍스트 ~ 10개
    for _ in range(count // 6):
        n = random.randint(1, 10)
        texts = _sample_texts(n)
        cases.append(EmbedderTestCase(
            id=f"TC-NORMAL-{len(cases)+1:05d}",
            category="normal",
            texts=texts,
            api_scenario="success",
            description=f"정상 텍스트 {n}개",
            expected={
                "type": "list_of_vectors",
                "length": n,
                "no_exception": True,
            },
        ))

    # 2) 중간 크기 (11~50개)
    for _ in range(count // 6):
        n = random.randint(11, 50)
        texts = _rand_texts(n)
        cases.append(EmbedderTestCase(
            id=f"TC-NORMAL-{len(cases)+1:05d}",
            category="normal",
            texts=texts,
            api_scenario="success",
            description=f"중간 크기 텍스트 {n}개",
            expected={
                "type": "list_of_vectors",
                "length": n,
                "no_exception": True,
            },
        ))

    # 3) 코드 스니펫
    for _ in range(count // 8):
        n = random.randint(1, len(CODE_TEXTS))
        texts = random.sample(CODE_TEXTS, n)
        cases.append(EmbedderTestCase(
            id=f"TC-NORMAL-{len(cases)+1:05d}",
            category="normal",
            texts=texts,
            api_scenario="success",
            description=f"코드 스니펫 {n}개",
            expected={
                "type": "list_of_vectors",
                "length": n,
                "no_exception": True,
            },
        ))

    # 4) 다국어 텍스트
    for _ in range(count // 8):
        n = random.randint(1, len(MULTILANG_TEXTS))
        texts = random.sample(MULTILANG_TEXTS, n)
        cases.append(EmbedderTestCase(
            id=f"TC-NORMAL-{len(cases)+1:05d}",
            category="normal",
            texts=texts,
            api_scenario="success",
            description=f"다국어 텍스트 {n}개",
            expected={
                "type": "list_of_vectors",
                "length": n,
                "no_exception": True,
            },
        ))

    # 5) 캐시 히트 시나리오 (동일 텍스트 반복)
    for _ in range(count // 8):
        base = random.choice(CODE_TEXTS + NATURAL_TEXTS)
        n = random.randint(1, 5)
        texts = [base] * n  # 동일 텍스트 반복
        cases.append(EmbedderTestCase(
            id=f"TC-NORMAL-{len(cases)+1:05d}",
            category="normal",
            texts=texts,
            api_scenario="success",
            description=f"동일 텍스트 {n}개 (캐시 히트)",
            expected={
                "type": "list_of_vectors",
                "length": n,
                "no_exception": True,
            },
        ))

    # 6) API 키 없음 → 빈 리스트 반환
    for _ in range(count // 10):
        n = random.randint(1, 10)
        texts = _sample_texts(n)
        cases.append(EmbedderTestCase(
            id=f"TC-NORMAL-{len(cases)+1:05d}",
            category="normal",
            texts=texts,
            api_scenario="api_key_missing",
            description=f"API 키 없음 → graceful degradation",
            expected={
                "type": "empty_list",
                "no_exception": True,
            },
        ))

    # 나머지 채우기
    while len(cases) < count:
        n = random.randint(1, 50)
        texts = _rand_texts(n)
        cases.append(EmbedderTestCase(
            id=f"TC-NORMAL-{len(cases)+1:05d}",
            category="normal",
            texts=texts,
            api_scenario="success",
            description=f"랜덤 정상 텍스트 {n}개",
            expected={
                "type": "list_of_vectors",
                "length": n,
                "no_exception": True,
            },
        ))

    return cases[:count]


def _gen_boundary_cases(count: int) -> list[EmbedderTestCase]:
    """경계값 케이스를 생성한다."""
    cases: list[EmbedderTestCase] = []
    random.seed(20)

    # 1) 빈 리스트 → 즉시 [] 반환 (API 호출 없음)
    cases.append(EmbedderTestCase(
        id=f"TC-BOUNDARY-{len(cases)+1:05d}",
        category="boundary",
        texts=[],
        api_scenario="success",
        description="빈 리스트 embed([]) → []",
        expected={"type": "empty_list", "no_exception": True},
    ))

    # 2) 빈 문자열 1개
    cases.append(EmbedderTestCase(
        id=f"TC-BOUNDARY-{len(cases)+1:05d}",
        category="boundary",
        texts=[""],
        api_scenario="success",
        description='빈 문자열 1개 embed([""])',
        expected={"type": "list_of_vectors", "length": 1, "no_exception": True},
    ))

    # 3) 빈 문자열 여러 개
    for n in [2, 5, 10]:
        cases.append(EmbedderTestCase(
            id=f"TC-BOUNDARY-{len(cases)+1:05d}",
            category="boundary",
            texts=[""] * n,
            api_scenario="success",
            description=f"빈 문자열 {n}개",
            expected={"type": "list_of_vectors", "length": n, "no_exception": True},
        ))

    # 4) 공백만 있는 텍스트
    for ws in [" ", "   ", "\t", "\n", "  \n  "]:
        cases.append(EmbedderTestCase(
            id=f"TC-BOUNDARY-{len(cases)+1:05d}",
            category="boundary",
            texts=[ws],
            api_scenario="success",
            description=f"공백 텍스트 (repr={repr(ws[:10])})",
            expected={"type": "list_of_vectors", "length": 1, "no_exception": True},
        ))

    # 5) 정확히 BATCH_SIZE=96개 (배치 경계)
    cases.append(EmbedderTestCase(
        id=f"TC-BOUNDARY-{len(cases)+1:05d}",
        category="boundary",
        texts=_rand_texts(96),
        api_scenario="success",
        description="정확히 BATCH_SIZE=96개",
        expected={"type": "list_of_vectors", "length": 96, "no_exception": True},
    ))

    # 6) BATCH_SIZE+1=97개 (배치 분할 시작)
    cases.append(EmbedderTestCase(
        id=f"TC-BOUNDARY-{len(cases)+1:05d}",
        category="boundary",
        texts=_rand_texts(97),
        api_scenario="success",
        description="BATCH_SIZE+1=97개 (첫 배치 분할)",
        expected={"type": "list_of_vectors", "length": 97, "no_exception": True},
    ))

    # 7) BATCH_SIZE*2=192개 (정확히 2배치)
    cases.append(EmbedderTestCase(
        id=f"TC-BOUNDARY-{len(cases)+1:05d}",
        category="boundary",
        texts=_rand_texts(192),
        api_scenario="success",
        description="BATCH_SIZE*2=192개 (정확히 2배치)",
        expected={"type": "list_of_vectors", "length": 192, "no_exception": True},
    ))

    # 8) BATCH_SIZE*2+1=193개 (3배치 시작)
    cases.append(EmbedderTestCase(
        id=f"TC-BOUNDARY-{len(cases)+1:05d}",
        category="boundary",
        texts=_rand_texts(193),
        api_scenario="success",
        description="BATCH_SIZE*2+1=193개 (3배치)",
        expected={"type": "list_of_vectors", "length": 193, "no_exception": True},
    ))

    # 9) 매우 긴 단일 텍스트 (10,000자)
    long_text = "a" * 10000
    cases.append(EmbedderTestCase(
        id=f"TC-BOUNDARY-{len(cases)+1:05d}",
        category="boundary",
        texts=[long_text],
        api_scenario="success",
        description="매우 긴 텍스트 10,000자",
        expected={"type": "list_of_vectors", "length": 1, "no_exception": True},
    ))

    # 10) 단일 문자 텍스트
    for ch in ["a", "1", "가", "x"]:
        cases.append(EmbedderTestCase(
            id=f"TC-BOUNDARY-{len(cases)+1:05d}",
            category="boundary",
            texts=[ch],
            api_scenario="success",
            description=f"단일 문자 텍스트: {repr(ch)}",
            expected={"type": "list_of_vectors", "length": 1, "no_exception": True},
        ))

    # 11) API 4xx 오류 → 빈 리스트 (재시도 안 함)
    for _ in range(5):
        n = random.randint(1, 10)
        cases.append(EmbedderTestCase(
            id=f"TC-BOUNDARY-{len(cases)+1:05d}",
            category="boundary",
            texts=_rand_texts(n),
            api_scenario="http_4xx",
            description=f"HTTP 4xx 오류 → graceful degradation ({n}개)",
            expected={"type": "empty_list", "no_exception": True},
        ))

    # 12) API 5xx 오류 → 재시도 후 빈 리스트
    for _ in range(5):
        n = random.randint(1, 10)
        cases.append(EmbedderTestCase(
            id=f"TC-BOUNDARY-{len(cases)+1:05d}",
            category="boundary",
            texts=_rand_texts(n),
            api_scenario="http_5xx",
            description=f"HTTP 5xx 오류 → 재시도 후 빈 리스트 ({n}개)",
            expected={"type": "empty_list", "no_exception": True},
        ))

    # 13) 네트워크 오류 → 빈 리스트
    for _ in range(5):
        n = random.randint(1, 10)
        cases.append(EmbedderTestCase(
            id=f"TC-BOUNDARY-{len(cases)+1:05d}",
            category="boundary",
            texts=_rand_texts(n),
            api_scenario="network_error",
            description=f"네트워크 오류 → 빈 리스트 ({n}개)",
            expected={"type": "empty_list", "no_exception": True},
        ))

    # 나머지 채우기
    while len(cases) < count:
        variant = random.randint(0, 5)
        if variant == 0:
            # 빈 리스트
            cases.append(EmbedderTestCase(
                id=f"TC-BOUNDARY-{len(cases)+1:05d}",
                category="boundary",
                texts=[],
                api_scenario="success",
                description="빈 리스트 (반복)",
                expected={"type": "empty_list", "no_exception": True},
            ))
        elif variant == 1:
            # BATCH_SIZE 근처 값
            n = random.choice([95, 96, 97, 191, 192, 193])
            cases.append(EmbedderTestCase(
                id=f"TC-BOUNDARY-{len(cases)+1:05d}",
                category="boundary",
                texts=_rand_texts(n),
                api_scenario="success",
                description=f"배치 경계 근처 {n}개",
                expected={"type": "list_of_vectors", "length": n, "no_exception": True},
            ))
        elif variant == 2:
            # 1개 텍스트
            cases.append(EmbedderTestCase(
                id=f"TC-BOUNDARY-{len(cases)+1:05d}",
                category="boundary",
                texts=[random.choice(CODE_TEXTS + NATURAL_TEXTS)],
                api_scenario="success",
                description="단일 텍스트",
                expected={"type": "list_of_vectors", "length": 1, "no_exception": True},
            ))
        elif variant == 3:
            # API 키 없음
            n = random.randint(1, 5)
            cases.append(EmbedderTestCase(
                id=f"TC-BOUNDARY-{len(cases)+1:05d}",
                category="boundary",
                texts=_rand_texts(n),
                api_scenario="api_key_missing",
                description=f"API 키 없음 ({n}개)",
                expected={"type": "empty_list", "no_exception": True},
            ))
        elif variant == 4:
            # 긴 텍스트
            length = random.randint(1000, 10000)
            cases.append(EmbedderTestCase(
                id=f"TC-BOUNDARY-{len(cases)+1:05d}",
                category="boundary",
                texts=["x" * length],
                api_scenario="success",
                description=f"긴 텍스트 ({length}자)",
                expected={"type": "list_of_vectors", "length": 1, "no_exception": True},
            ))
        else:
            # 오류 시나리오
            scenario = random.choice(["http_4xx", "http_5xx", "network_error"])
            n = random.randint(1, 10)
            cases.append(EmbedderTestCase(
                id=f"TC-BOUNDARY-{len(cases)+1:05d}",
                category="boundary",
                texts=_rand_texts(n),
                api_scenario=scenario,
                description=f"{scenario} → 빈 리스트",
                expected={"type": "empty_list", "no_exception": True},
            ))

    return cases[:count]


def _gen_invalid_cases(count: int) -> list[EmbedderTestCase]:
    """잘못된 입력 케이스를 생성한다.

    embed()는 list[str]을 받지만 다양한 특이 입력에도
    예외 없이 처리해야 한다.
    """
    cases: list[EmbedderTestCase] = []
    random.seed(30)

    # 1) 특수문자만 있는 텍스트
    special_texts = [
        "!@#$%^&*()",
        "---===---",
        "...",
        "///\\\\\\",
        "\x00\x01\x02",
        "   \t\n   ",
        "💡🔥🎉",
        "∞∑∏√∆",
    ]
    for t in special_texts:
        cases.append(EmbedderTestCase(
            id=f"TC-INVALID-{len(cases)+1:05d}",
            category="invalid",
            texts=[t],
            api_scenario="success",
            description=f"특수문자 텍스트: {repr(t[:20])}",
            expected={"type": "list_of_vectors", "length": 1, "no_exception": True},
        ))

    # 2) 매우 긴 텍스트 (50,000자)
    for length in [10000, 30000, 50000]:
        cases.append(EmbedderTestCase(
            id=f"TC-INVALID-{len(cases)+1:05d}",
            category="invalid",
            texts=["x" * length],
            api_scenario="success",
            description=f"극도로 긴 텍스트 ({length}자)",
            expected={"type": "list_of_vectors", "length": 1, "no_exception": True},
        ))

    # 3) null 바이트 포함 텍스트
    for t in ["hello\x00world", "text\x00", "\x00text", "a\x00b\x00c"]:
        cases.append(EmbedderTestCase(
            id=f"TC-INVALID-{len(cases)+1:05d}",
            category="invalid",
            texts=[t],
            api_scenario="success",
            description=f"null 바이트 포함: {repr(t)}",
            expected={"type": "list_of_vectors", "length": 1, "no_exception": True},
        ))

    # 4) 혼합 빈/비빈 텍스트
    for combo in [
        ["", "hello", ""],
        ["text", "", "more text"],
        ["", "", "not empty"],
        ["a", "", "b", "", "c"],
    ]:
        cases.append(EmbedderTestCase(
            id=f"TC-INVALID-{len(cases)+1:05d}",
            category="invalid",
            texts=combo,
            api_scenario="success",
            description=f"빈/비빈 혼합 텍스트 {len(combo)}개",
            expected={"type": "list_of_vectors", "length": len(combo), "no_exception": True},
        ))

    # 5) 유니코드 다양한 범주
    unicode_texts = [
        "한국어 텍스트 테스트",
        "日本語テキスト",
        "中文文本",
        "Ελληνικά κείμενα",
        "العربية النص",
        "ру́сский текст",
        "emoji 🎯🚀💻",
        "math: ∫∑∏∆∇",
    ]
    for t in unicode_texts:
        cases.append(EmbedderTestCase(
            id=f"TC-INVALID-{len(cases)+1:05d}",
            category="invalid",
            texts=[t],
            api_scenario="success",
            description=f"유니코드 텍스트: {repr(t[:20])}",
            expected={"type": "list_of_vectors", "length": 1, "no_exception": True},
        ))

    # 6) 반복 패턴 (캐시 동작 검증)
    for n in [1, 3, 10, 50]:
        t = "repeated text for cache test"
        cases.append(EmbedderTestCase(
            id=f"TC-INVALID-{len(cases)+1:05d}",
            category="invalid",
            texts=[t] * n,
            api_scenario="success",
            description=f"동일 텍스트 {n}번 반복 (캐시 히트 검증)",
            expected={"type": "list_of_vectors", "length": n, "no_exception": True},
        ))

    # 나머지 채우기
    while len(cases) < count:
        variant = random.randint(0, 4)
        if variant == 0:
            # 랜덤 특수문자 텍스트
            t = "".join(random.choices(string.punctuation, k=random.randint(1, 50)))
            cases.append(EmbedderTestCase(
                id=f"TC-INVALID-{len(cases)+1:05d}",
                category="invalid",
                texts=[t],
                api_scenario="success",
                description="랜덤 특수문자 텍스트",
                expected={"type": "list_of_vectors", "length": 1, "no_exception": True},
            ))
        elif variant == 1:
            # 랜덤 긴 텍스트
            length = random.randint(5000, 20000)
            t = "".join(random.choices(string.printable, k=length))
            cases.append(EmbedderTestCase(
                id=f"TC-INVALID-{len(cases)+1:05d}",
                category="invalid",
                texts=[t],
                api_scenario="success",
                description=f"랜덤 긴 텍스트 ({length}자)",
                expected={"type": "list_of_vectors", "length": 1, "no_exception": True},
            ))
        elif variant == 2:
            # 혼합 유니코드
            t = "".join(random.choices(
                string.printable + "한글テスト中文العربية",
                k=random.randint(1, 200)
            ))
            cases.append(EmbedderTestCase(
                id=f"TC-INVALID-{len(cases)+1:05d}",
                category="invalid",
                texts=[t],
                api_scenario="success",
                description="혼합 유니코드 텍스트",
                expected={"type": "list_of_vectors", "length": 1, "no_exception": True},
            ))
        elif variant == 3:
            # API 오류 시나리오
            scenario = random.choice(["api_key_missing", "http_4xx", "http_5xx", "network_error"])
            n = random.randint(1, 20)
            cases.append(EmbedderTestCase(
                id=f"TC-INVALID-{len(cases)+1:05d}",
                category="invalid",
                texts=_rand_texts(n),
                api_scenario=scenario,
                description=f"{scenario} ({n}개)",
                expected={"type": "empty_list", "no_exception": True},
            ))
        else:
            # 제어 문자 포함
            ctrl = "".join(chr(random.randint(1, 31)) for _ in range(5))
            t = f"text{ctrl}more"
            cases.append(EmbedderTestCase(
                id=f"TC-INVALID-{len(cases)+1:05d}",
                category="invalid",
                texts=[t],
                api_scenario="success",
                description="제어 문자 포함 텍스트",
                expected={"type": "list_of_vectors", "length": 1, "no_exception": True},
            ))

    return cases[:count]


def _gen_stress_cases(count: int) -> list[EmbedderTestCase]:
    """극단적 입력 스트레스 케이스를 생성한다."""
    cases: list[EmbedderTestCase] = []
    random.seed(40)

    # 1) 대량 텍스트 (100~1000개, 다중 배치)
    for n in [100, 200, 300, 500]:
        cases.append(EmbedderTestCase(
            id=f"TC-STRESS-{len(cases)+1:05d}",
            category="stress",
            texts=_rand_texts(n),
            api_scenario="success",
            description=f"대량 텍스트 {n}개 ({n // 96 + 1}배치)",
            expected={"type": "list_of_vectors", "length": n, "no_exception": True},
        ))

    # 2) 1,000개 텍스트 (10+ 배치)
    cases.append(EmbedderTestCase(
        id=f"TC-STRESS-{len(cases)+1:05d}",
        category="stress",
        texts=_rand_texts(1000),
        api_scenario="success",
        description="1,000개 텍스트 (11배치)",
        expected={"type": "list_of_vectors", "length": 1000, "no_exception": True},
    ))

    # 3) 각 텍스트가 매우 긴 경우 (96개 × 1,000자)
    cases.append(EmbedderTestCase(
        id=f"TC-STRESS-{len(cases)+1:05d}",
        category="stress",
        texts=["x" * 1000 for _ in range(96)],
        api_scenario="success",
        description="96개 × 1,000자 텍스트",
        expected={"type": "list_of_vectors", "length": 96, "no_exception": True},
    ))

    # 4) 각 텍스트가 5,000자 (50개)
    cases.append(EmbedderTestCase(
        id=f"TC-STRESS-{len(cases)+1:05d}",
        category="stress",
        texts=["y" * 5000 for _ in range(50)],
        api_scenario="success",
        description="50개 × 5,000자 텍스트",
        expected={"type": "list_of_vectors", "length": 50, "no_exception": True},
    ))

    # 5) 반복 fit+embed (캐시 재사용)
    texts = _rand_texts(20)
    for _ in range(10):
        cases.append(EmbedderTestCase(
            id=f"TC-STRESS-{len(cases)+1:05d}",
            category="stress",
            texts=texts[:],
            api_scenario="success",
            description="동일 텍스트 세트 반복 (캐시 재사용)",
            expected={"type": "list_of_vectors", "length": 20, "no_exception": True},
        ))

    # 6) 모든 텍스트가 동일 (캐시 극단)
    for n in [96, 192, 500]:
        t = "identical text for cache stress test"
        cases.append(EmbedderTestCase(
            id=f"TC-STRESS-{len(cases)+1:05d}",
            category="stress",
            texts=[t] * n,
            api_scenario="success",
            description=f"동일 텍스트 {n}개 (캐시 극단)",
            expected={"type": "list_of_vectors", "length": n, "no_exception": True},
        ))

    # 7) 5xx 오류 후 성공 (재시도 성공 시나리오 — 여기선 모킹으로 단순 5xx 처리)
    for n in [10, 50]:
        cases.append(EmbedderTestCase(
            id=f"TC-STRESS-{len(cases)+1:05d}",
            category="stress",
            texts=_rand_texts(n),
            api_scenario="http_5xx",
            description=f"5xx 오류 스트레스 ({n}개)",
            expected={"type": "empty_list", "no_exception": True},
        ))

    # 나머지 채우기
    while len(cases) < count:
        n = random.randint(100, 500)
        cases.append(EmbedderTestCase(
            id=f"TC-STRESS-{len(cases)+1:05d}",
            category="stress",
            texts=_rand_texts(n),
            api_scenario="success",
            description=f"랜덤 대량 텍스트 {n}개",
            expected={"type": "list_of_vectors", "length": n, "no_exception": True},
        ))

    return cases[:count]


def _gen_random_cases(count: int) -> list[EmbedderTestCase]:
    """무작위 퍼징 케이스를 생성한다."""
    cases: list[EmbedderTestCase] = []
    random.seed(50)

    scenarios = ["success", "api_key_missing", "http_4xx", "http_5xx", "network_error"]
    scenario_weights = [0.6, 0.1, 0.1, 0.1, 0.1]

    for i in range(count):
        tc_id = f"TC-RANDOM-{i+1:05d}"
        scenario = random.choices(scenarios, weights=scenario_weights)[0]
        variant = random.random()

        if variant < 0.3:
            # 완전 무작위 텍스트
            n = random.randint(0, 100)
            texts = [] if n == 0 else [
                "".join(random.choices(string.printable + "한글テスト", k=random.randint(0, 300)))
                for _ in range(n)
            ]
            expected_type = "empty_list" if (n == 0 or scenario != "success") else "list_of_vectors"
            cases.append(EmbedderTestCase(
                id=tc_id,
                category="random",
                texts=texts,
                api_scenario=scenario,
                description=f"완전 무작위 ({n}개, {scenario})",
                expected={
                    "type": expected_type,
                    "length": n if expected_type == "list_of_vectors" else None,
                    "no_exception": True,
                },
            ))
        elif variant < 0.5:
            # 랜덤 크기 코드/자연어 혼합
            pool = CODE_TEXTS + NATURAL_TEXTS + MULTILANG_TEXTS
            n = random.randint(1, 30)
            texts = [random.choice(pool) for _ in range(n)]
            expected_type = "empty_list" if scenario != "success" else "list_of_vectors"
            cases.append(EmbedderTestCase(
                id=tc_id,
                category="random",
                texts=texts,
                api_scenario=scenario,
                description=f"랜덤 혼합 텍스트 ({n}개, {scenario})",
                expected={
                    "type": expected_type,
                    "length": n if expected_type == "list_of_vectors" else None,
                    "no_exception": True,
                },
            ))
        elif variant < 0.65:
            # 빈 리스트 퍼징
            cases.append(EmbedderTestCase(
                id=tc_id,
                category="random",
                texts=[],
                api_scenario=scenario,
                description=f"빈 리스트 퍼징 ({scenario})",
                expected={"type": "empty_list", "no_exception": True},
            ))
        elif variant < 0.80:
            # 특수문자 집중 퍼징
            n = random.randint(1, 20)
            texts = [
                "".join(random.choices(string.punctuation + string.whitespace, k=random.randint(1, 100)))
                for _ in range(n)
            ]
            expected_type = "empty_list" if scenario != "success" else "list_of_vectors"
            cases.append(EmbedderTestCase(
                id=tc_id,
                category="random",
                texts=texts,
                api_scenario=scenario,
                description=f"특수문자 집중 퍼징 ({n}개)",
                expected={
                    "type": expected_type,
                    "length": n if expected_type == "list_of_vectors" else None,
                    "no_exception": True,
                },
            ))
        else:
            # 대량 무작위
            n = random.randint(50, 200)
            texts = _rand_texts(n, min_chars=1, max_chars=1000)
            expected_type = "empty_list" if scenario != "success" else "list_of_vectors"
            cases.append(EmbedderTestCase(
                id=tc_id,
                category="random",
                texts=texts,
                api_scenario=scenario,
                description=f"대량 무작위 퍼징 ({n}개, {scenario})",
                expected={
                    "type": expected_type,
                    "length": n if expected_type == "list_of_vectors" else None,
                    "no_exception": True,
                },
            ))

    return cases


# ---------------------------------------------------------------------------
# 메인 생성 함수
# ---------------------------------------------------------------------------

def generate_all_cases(total: int = 10000) -> list[EmbedderTestCase]:
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

    all_cases: list[EmbedderTestCase] = []
    all_cases.extend(_gen_normal_cases(counts["normal"]))
    all_cases.extend(_gen_boundary_cases(counts["boundary"]))
    all_cases.extend(_gen_invalid_cases(counts["invalid"]))
    all_cases.extend(_gen_stress_cases(counts["stress"]))
    all_cases.extend(_gen_random_cases(counts["random"]))

    for i, tc in enumerate(all_cases):
        tc.id = f"TC-MODULE-{i+1:05d}"

    return all_cases


def _safe_dict(tc: EmbedderTestCase) -> dict:
    """JSON 직렬화 안전한 딕셔너리로 변환한다."""
    d = asdict(tc)
    if d.get("texts"):
        safe_texts = []
        for t in d["texts"]:
            if t is None:
                safe_texts.append(None)
                continue
            try:
                json.dumps(t)
                safe_texts.append(t)
            except (UnicodeEncodeError, ValueError):
                safe_texts.append(
                    t.encode("utf-8", errors="replace").decode("utf-8")
                )
        d["texts"] = safe_texts
    return d


def save_cases_jsonl(cases: list[EmbedderTestCase], output_path: Path) -> None:
    """테스트 케이스를 JSONL 형식으로 저장한다."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for tc in cases:
            f.write(json.dumps(_safe_dict(tc), ensure_ascii=False) + "\n")
    print(f"저장 완료: {output_path} ({len(cases)}건)")


def main() -> None:
    """CLI 진입점."""
    parser = argparse.ArgumentParser(description="AnthropicEmbedder QC 테스트 케이스 생성기")
    parser.add_argument("--module", default="src/rag/embedder.py")
    parser.add_argument("--count", type=int, default=10000)
    parser.add_argument("--output", default="tests/qc/embedder/")
    args = parser.parse_args()

    output_path = Path(args.output) / "test_cases.jsonl"
    print(f"대상 모듈: {args.module}")
    print(f"케이스 수: {args.count:,}건")
    print(f"출력 경로: {output_path}")
    print()

    cases = generate_all_cases(args.count)
    save_cases_jsonl(cases, output_path)
    print(f"\n생성 완료: 총 {len(cases):,}건")


if __name__ == "__main__":
    main()
