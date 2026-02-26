"""모듈 QC 테스트 케이스 생성기.

ASTChunker의 chunk() 메서드를 대상으로
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
import textwrap
from dataclasses import asdict, dataclass
from pathlib import Path

# 재현 가능한 시드
random.seed(42)

# 지원 확장자
PYTHON_EXT = ".py"
NON_PYTHON_EXTS = [".js", ".ts", ".tsx", ".jsx", ".yaml", ".yml", ".md", ".go", ".java", ".rs"]
UNKNOWN_EXTS = [".txt", ".csv", ".html", ".css", ".xml", ".rb", ".php"]

# ASTChunker 상수
MIN_LINES = 5
MAX_LINES = 100
BLOCK_SIZE = 50
OVERLAP = 10


@dataclass
class TestCase:
    """QC 테스트 케이스 구조체."""

    id: str
    category: str
    file_path: str
    content: str
    description: str
    expected: dict


# ---------------------------------------------------------------------------
# Python 코드 생성 헬퍼
# ---------------------------------------------------------------------------

def _make_function(name: str, line_count: int) -> str:
    """지정 줄 수의 Python 함수 코드를 생성한다."""
    body_lines = line_count - 1  # def 라인 제외
    body = "\n".join(f"    var_{i} = {i}" for i in range(max(1, body_lines - 1)))
    return f"def {name}():\n{body}\n    return var_0\n"


def _make_class(name: str, method_count: int, method_lines: int) -> str:
    """지정 메서드 수와 줄 수의 Python 클래스 코드를 생성한다."""
    lines = [f"class {name}:"]
    for i in range(method_count):
        lines.append(f"    def method_{i}(self):")
        for j in range(method_lines - 2):
            lines.append(f"        v{i}_{j} = {j}")
        lines.append(f"        return 0")
    return "\n".join(lines) + "\n"


def _make_python_module(func_count: int = 3, func_lines: int = 6) -> str:
    """여러 함수와 모듈 레벨 코드를 포함한 Python 파일을 생성한다."""
    parts = ["import os\nimport sys\n\nMODULE_VAR = 42\n"]
    for i in range(func_count):
        parts.append(_make_function(f"func_{i}", func_lines))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 카테고리별 케이스 생성 함수
# ---------------------------------------------------------------------------

def _gen_normal_cases(count: int) -> list[TestCase]:
    """정상 입력 케이스를 생성한다."""
    cases = []

    # 1) 다양한 Python 함수/클래스 조합
    templates = [
        # (description, file_path, content_factory)
        (
            "단일 함수",
            "normal.py",
            lambda: _make_function("hello_world", random.randint(5, 20)),
        ),
        (
            "여러 함수",
            "multi_func.py",
            lambda: _make_python_module(func_count=random.randint(2, 5), func_lines=random.randint(5, 15)),
        ),
        (
            "클래스 + 메서드",
            "cls.py",
            lambda: _make_class("MyClass", random.randint(2, 5), random.randint(5, 10)),
        ),
        (
            "비Python JS 파일",
            "app.js",
            lambda: "\n".join(f"const line{i} = {i};" for i in range(random.randint(10, 100))),
        ),
        (
            "비Python TS 파일",
            "app.ts",
            lambda: "\n".join(f"let x{i}: number = {i};" for i in range(random.randint(10, 80))),
        ),
        (
            "비Python YAML 파일",
            "config.yaml",
            lambda: "\n".join(f"key_{i}: value_{i}" for i in range(random.randint(10, 60))),
        ),
        (
            "async 함수",
            "async.py",
            lambda: f"async def async_func():\n" + "\n".join(f"    v{i} = {i}" for i in range(5)) + "\n    return v0\n",
        ),
        (
            "데코레이터 함수",
            "decorated.py",
            lambda: f"@property\ndef decorated():\n    x = 1\n    y = 2\n    z = 3\n    return x + y + z\n",
        ),
        (
            "import만 있는 파일",
            "imports.py",
            lambda: "import os\nimport sys\nfrom pathlib import Path\n",
        ),
        (
            "모듈 레벨 상수",
            "constants.py",
            lambda: "\n".join(f"CONST_{i} = {i}" for i in range(random.randint(5, 20))) + "\n",
        ),
    ]

    per_template = count // len(templates)
    remainder = count % len(templates)

    for idx, (desc, fp, factory) in enumerate(templates):
        n = per_template + (1 if idx < remainder else 0)
        for i in range(n):
            tc_id = f"TC-NORMAL-{len(cases) + 1:05d}"
            content = factory()
            cases.append(
                TestCase(
                    id=tc_id,
                    category="normal",
                    file_path=fp,
                    content=content,
                    description=desc,
                    expected={
                        "type": "list",
                        "min_length": 0,
                        "no_exception": True,
                    },
                )
            )
    return cases[:count]


def _gen_boundary_cases(count: int) -> list[TestCase]:
    """경계값 케이스를 생성한다."""
    cases = []

    # 1) 빈 파일
    for ext in [".py", ".js", ".ts"]:
        cases.append(TestCase(
            id=f"TC-BOUNDARY-{len(cases) + 1:05d}",
            category="boundary",
            file_path=f"empty{ext}",
            content="",
            description=f"빈 파일 ({ext})",
            expected={"type": "empty_list"},
        ))

    # 2) 공백만 있는 파일
    for ws in ["   ", "\n", "\n\n", "\t", "  \n  "]:
        cases.append(TestCase(
            id=f"TC-BOUNDARY-{len(cases) + 1:05d}",
            category="boundary",
            file_path="whitespace.py",
            content=ws,
            description="공백만 있는 파일",
            expected={"type": "empty_list"},
        ))

    # 3) 1줄짜리 파일
    cases.append(TestCase(
        id=f"TC-BOUNDARY-{len(cases) + 1:05d}",
        category="boundary",
        file_path="single.py",
        content="x = 1\n",
        description="1줄 Python 파일",
        expected={"type": "list", "min_length": 0, "no_exception": True},
    ))

    # 4) MIN_LINES 경계 (4줄: 미만이어야 함)
    for n in range(1, MIN_LINES):
        func_body = "\n".join(f"    v{i} = {i}" for i in range(n - 1))
        content = f"def tiny_{n}():\n{func_body}\n"
        cases.append(TestCase(
            id=f"TC-BOUNDARY-{len(cases) + 1:05d}",
            category="boundary",
            file_path="tiny.py",
            content=content,
            description=f"MIN_LINES 미만 함수 ({n}줄)",
            expected={
                "type": "list",
                "no_exception": True,
                "no_function_chunk_named": f"tiny_{n}",
            },
        ))

    # 5) MIN_LINES 정확히 5줄
    content_5 = "def exactly_five():\n    a = 1\n    b = 2\n    c = 3\n    return a + b + c\n"
    cases.append(TestCase(
        id=f"TC-BOUNDARY-{len(cases) + 1:05d}",
        category="boundary",
        file_path="exact.py",
        content=content_5,
        description="정확히 MIN_LINES(5) 줄 함수",
        expected={
            "type": "list",
            "no_exception": True,
            "has_function_chunk_named": "exactly_five",
        },
    ))

    # 6) MAX_LINES 경계 (100줄 클래스)
    # 정확히 100줄 클래스 (class 청크 생성돼야 함)
    methods_100 = "\n".join(
        f"    def m{i}(self):\n        v{i} = {i}\n        return v{i}"
        for i in range(16)
    )
    content_100 = f"class Boundary100:\n{methods_100}\n"
    cases.append(TestCase(
        id=f"TC-BOUNDARY-{len(cases) + 1:05d}",
        category="boundary",
        file_path="boundary100.py",
        content=content_100,
        description="MAX_LINES 이하 클래스 (class 청크 있어야 함)",
        expected={
            "type": "list",
            "no_exception": True,
        },
    ))

    # 7) MAX_LINES + 1 줄 클래스 (class 청크 없어야 함)
    methods_101 = "\n".join(
        f"    def m{i}(self):\n        v{i}1 = {i}\n        v{i}2 = {i}\n        v{i}3 = {i}\n        return v{i}1"
        for i in range(17)
    )
    content_101 = f"class BigClass:\n{methods_101}\n"
    cases.append(TestCase(
        id=f"TC-BOUNDARY-{len(cases) + 1:05d}",
        category="boundary",
        file_path="big.py",
        content=content_101,
        description="MAX_LINES 초과 클래스 (class 청크 없어야 함)",
        expected={
            "type": "list",
            "no_exception": True,
        },
    ))

    # 8) 정확히 BLOCK_SIZE(50)줄 비Python 파일
    content_50 = "\n".join(f"line {i}" for i in range(50))
    cases.append(TestCase(
        id=f"TC-BOUNDARY-{len(cases) + 1:05d}",
        category="boundary",
        file_path="fifty.js",
        content=content_50,
        description="정확히 BLOCK_SIZE(50)줄 비Python 파일",
        expected={"type": "list", "no_exception": True},
    ))

    # 9) 다양한 비Python 확장자 (빈 파일)
    for ext in NON_PYTHON_EXTS:
        cases.append(TestCase(
            id=f"TC-BOUNDARY-{len(cases) + 1:05d}",
            category="boundary",
            file_path=f"empty{ext}",
            content="",
            description=f"빈 비Python 파일 ({ext})",
            expected={"type": "empty_list"},
        ))

    # 나머지를 채울 랜덤 경계 케이스
    random.seed(100)
    while len(cases) < count:
        variant = random.randint(0, 4)
        if variant == 0:
            # 1줄 비Python
            ext = random.choice(NON_PYTHON_EXTS)
            cases.append(TestCase(
                id=f"TC-BOUNDARY-{len(cases) + 1:05d}",
                category="boundary",
                file_path=f"single{ext}",
                content="const x = 1;",
                description=f"1줄 비Python 파일 ({ext})",
                expected={"type": "list", "no_exception": True},
            ))
        elif variant == 1:
            # MIN_LINES 경계 근처 함수
            n = random.choice([MIN_LINES - 1, MIN_LINES, MIN_LINES + 1])
            body = "\n".join(f"    v{i} = {i}" for i in range(n - 1))
            content = f"def boundary_func():\n{body}\n"
            cases.append(TestCase(
                id=f"TC-BOUNDARY-{len(cases) + 1:05d}",
                category="boundary",
                file_path="boundary.py",
                content=content,
                description=f"MIN_LINES 경계 함수 ({n}줄)",
                expected={"type": "list", "no_exception": True},
            ))
        elif variant == 2:
            # 빈 클래스
            cases.append(TestCase(
                id=f"TC-BOUNDARY-{len(cases) + 1:05d}",
                category="boundary",
                file_path="empty_class.py",
                content="class Empty:\n    pass\n",
                description="빈 클래스 (pass만)",
                expected={"type": "list", "no_exception": True},
            ))
        elif variant == 3:
            # 함수 없는 Python 파일
            lines = random.randint(1, 10)
            content = "\n".join(f"x_{i} = {i}" for i in range(lines)) + "\n"
            cases.append(TestCase(
                id=f"TC-BOUNDARY-{len(cases) + 1:05d}",
                category="boundary",
                file_path="no_func.py",
                content=content,
                description="함수 없는 Python 파일",
                expected={"type": "list", "no_exception": True},
            ))
        else:
            # 알 수 없는 확장자 (폴백 처리)
            ext = random.choice(UNKNOWN_EXTS)
            content = "\n".join(f"data line {i}" for i in range(random.randint(5, 30)))
            cases.append(TestCase(
                id=f"TC-BOUNDARY-{len(cases) + 1:05d}",
                category="boundary",
                file_path=f"unknown{ext}",
                content=content,
                description=f"알 수 없는 확장자 ({ext}) 파일",
                expected={"type": "list", "no_exception": True},
            ))

    return cases[:count]


def _gen_invalid_cases(count: int) -> list[TestCase]:
    """잘못된 입력 케이스를 생성한다."""
    cases = []
    random.seed(200)

    # 1) SyntaxError Python 파일들
    syntax_errors = [
        ("구문 오류 - 괄호 미닫힘", "bad.py", "def broken(\n    pass\n"),
        ("구문 오류 - 잘못된 indent", "indent.py", "def func():\npass\n"),
        ("구문 오류 - 예약어 오용", "keyword.py", "class = 1\n"),
        ("구문 오류 - 불완전한 표현식", "expr.py", "x = 1 +\n"),
        ("구문 오류 - 닫히지 않은 문자열", "str.py", 'x = "hello\n'),
        ("구문 오류 - 불완전한 함수", "func.py", "def hello( syntax error here\n"),
        ("구문 오류 - 복합 오류", "complex.py", "def f(:\n    pass\n"),
        ("구문 오류 - if without colon", "if.py", "if True\n    pass\n"),
        ("구문 오류 - print 구문 (Py2)", "py2.py", "print 'hello'\n"),
    ]

    for desc, fp, content in syntax_errors:
        cases.append(TestCase(
            id=f"TC-INVALID-{len(cases) + 1:05d}",
            category="invalid",
            file_path=fp,
            content=content,
            description=desc,
            expected={
                "type": "list",
                "no_exception": True,  # SyntaxError → 폴백, 예외 없음
                "chunk_type": "block",
            },
        ))

    # 2) 잘못된 인코딩 (바이너리 혼합)
    # surrogate 문자는 JSON 직렬화 불가이므로 제외, 대신 다른 특이 케이스 사용
    invalid_encodings = [
        ("null 바이트 포함", "null.py", "x = 1\x00\ny = 2\n"),
        ("제어 문자 포함", "ctrl.py", "x = 1\x01\x02\x03\n"),
        ("유니코드 한글 혼합", "unicode.py", "# 한글 주석\nx = '안녕하세요'\n"),
    ]
    for desc, fp, content in invalid_encodings:
        # JSON 직렬화 가능한 내용만 포함
        try:
            json.dumps(content)
        except (UnicodeEncodeError, ValueError):
            content = content.encode("utf-8", errors="replace").decode("utf-8")
        cases.append(TestCase(
            id=f"TC-INVALID-{len(cases) + 1:05d}",
            category="invalid",
            file_path=fp,
            content=content,
            description=desc,
            expected={"type": "list", "no_exception": True},
        ))

    # 3) 비어있지 않지만 유효하지 않은 Python 코드들
    weird_codes = [
        ("점만 있는 파일", "dots.py", "...\n"),
        ("주석만 있는 파일", "comments.py", "# 이것은 주석\n# 또 주석\n"),
        ("docstring만 있는 파일", "docstring.py", '"""이건 모듈 docstring"""\n'),
        ("패스만 있는 파일", "pass_only.py", "pass\n"),
        ("세미콜론 줄", "semicolons.py", "x = 1; y = 2; z = 3\n"),
        ("중첩 함수", "nested.py", "def outer():\n    def inner():\n        pass\n    return inner\n"),
        ("람다만 있는 파일", "lambda.py", "f = lambda x: x + 1\ng = lambda x, y: x * y\n"),
    ]
    for desc, fp, content in weird_codes:
        cases.append(TestCase(
            id=f"TC-INVALID-{len(cases) + 1:05d}",
            category="invalid",
            file_path=fp,
            content=content,
            description=desc,
            expected={"type": "list", "no_exception": True},
        ))

    # 나머지 채우기: 랜덤 SyntaxError 변형
    error_templates = [
        "def {name}(\n    pass\n",
        "class {name}\n    pass\n",
        "{name} = (\n",
        "if {name}\n    pass\n",
        "def {name}(x y):\n    pass\n",
    ]

    while len(cases) < count:
        template = random.choice(error_templates)
        name = "".join(random.choices(string.ascii_lowercase, k=random.randint(3, 8)))
        content = template.format(name=name)
        cases.append(TestCase(
            id=f"TC-INVALID-{len(cases) + 1:05d}",
            category="invalid",
            file_path=f"syntax_{len(cases)}.py",
            content=content,
            description="자동 생성 SyntaxError 케이스",
            expected={"type": "list", "no_exception": True, "chunk_type": "block"},
        ))

    return cases[:count]


def _gen_stress_cases(count: int) -> list[TestCase]:
    """극단적 입력 스트레스 케이스를 생성한다."""
    cases = []
    random.seed(300)

    # 1) 대형 Python 파일 (10,000줄)
    def _large_python(line_count: int) -> str:
        funcs = []
        lines_per_func = 10
        func_count = line_count // lines_per_func
        for i in range(func_count):
            body = "\n".join(f"    v{j} = {j}" for j in range(lines_per_func - 2))
            funcs.append(f"def func_{i}():\n{body}\n    return 0")
        return "\n\n".join(funcs) + "\n"

    for size in [1000, 5000, 10000]:
        cases.append(TestCase(
            id=f"TC-STRESS-{len(cases) + 1:05d}",
            category="stress",
            file_path=f"large_{size}.py",
            content=_large_python(size),
            description=f"대형 Python 파일 ({size}줄)",
            expected={"type": "list", "no_exception": True},
        ))

    # 2) 깊은 중첩 클래스
    for depth in [3, 5, 8]:
        parts = []
        indent = ""
        for i in range(depth):
            parts.append(f"{indent}class Nested_{i}:")
            indent += "    "
        parts.append(f"{indent}x = 1")
        content = "\n".join(parts) + "\n"
        cases.append(TestCase(
            id=f"TC-STRESS-{len(cases) + 1:05d}",
            category="stress",
            file_path="nested_class.py",
            content=content,
            description=f"깊은 중첩 클래스 ({depth}단계)",
            expected={"type": "list", "no_exception": True},
        ))

    # 3) 매우 긴 단일 함수
    for line_count in [200, 500, 1000]:
        body = "\n".join(f"    v{i} = {i}" for i in range(line_count - 2))
        content = f"def huge_func():\n{body}\n    return 0\n"
        cases.append(TestCase(
            id=f"TC-STRESS-{len(cases) + 1:05d}",
            category="stress",
            file_path="huge_func.py",
            content=content,
            description=f"매우 긴 단일 함수 ({line_count}줄)",
            expected={"type": "list", "no_exception": True},
        ))

    # 4) 비Python 대형 파일
    for size in [5000, 20000]:
        ext = random.choice(NON_PYTHON_EXTS)
        content = "\n".join(f"data_{i} = value_{i};" for i in range(size))
        cases.append(TestCase(
            id=f"TC-STRESS-{len(cases) + 1:05d}",
            category="stress",
            file_path=f"large{ext}",
            content=content,
            description=f"대형 비Python 파일 ({size}줄, {ext})",
            expected={"type": "list", "no_exception": True},
        ))

    # 5) 매우 긴 줄
    long_line = "x = " + "a + " * 1000 + "0"
    cases.append(TestCase(
        id=f"TC-STRESS-{len(cases) + 1:05d}",
        category="stress",
        file_path="long_line.py",
        content=long_line + "\n",
        description="매우 긴 단일 줄 (4,000+ 문자)",
        expected={"type": "list", "no_exception": True},
    ))

    # 6) 많은 데코레이터
    decorators = "\n".join(f"@decorator_{i}" for i in range(50))
    content = f"{decorators}\ndef decorated():\n    x = 1\n    y = 2\n    z = 3\n    return x + y + z\n"
    cases.append(TestCase(
        id=f"TC-STRESS-{len(cases) + 1:05d}",
        category="stress",
        file_path="many_decorators.py",
        content=content,
        description="50개 데코레이터가 있는 함수",
        expected={"type": "list", "no_exception": True},
    ))

    # 7) 많은 클래스 (100개)
    classes = "\n\n".join(
        f"class Class_{i}:\n    x = {i}\n    def method(self):\n        a = 1\n        b = 2\n        return a + b"
        for i in range(100)
    )
    cases.append(TestCase(
        id=f"TC-STRESS-{len(cases) + 1:05d}",
        category="stress",
        file_path="many_classes.py",
        content=classes + "\n",
        description="100개 클래스를 포함한 파일",
        expected={"type": "list", "no_exception": True},
    ))

    # 나머지 채우기
    while len(cases) < count:
        size = random.randint(500, 3000)
        if random.random() < 0.5:
            content = _large_python(size)
            fp = "large_random.py"
        else:
            ext = random.choice(NON_PYTHON_EXTS)
            content = "\n".join(f"item_{i} = {i};" for i in range(size))
            fp = f"large_random{ext}"
        cases.append(TestCase(
            id=f"TC-STRESS-{len(cases) + 1:05d}",
            category="stress",
            file_path=fp,
            content=content,
            description=f"랜덤 대형 파일 ({size}줄)",
            expected={"type": "list", "no_exception": True},
        ))

    return cases[:count]


def _gen_random_cases(count: int) -> list[TestCase]:
    """무작위 퍼징 케이스를 생성한다."""
    cases = []
    random.seed(400)

    def _random_python() -> str:
        """랜덤 Python 코드를 생성한다."""
        parts = []
        for _ in range(random.randint(1, 10)):
            kind = random.choice(["func", "class", "assign", "import"])
            if kind == "func":
                n = "".join(random.choices(string.ascii_lowercase, k=5))
                lines = random.randint(1, 15)
                body = "\n".join(f"    v{i} = {random.randint(0, 100)}" for i in range(lines))
                parts.append(f"def {n}():\n{body}\n    return 0\n")
            elif kind == "class":
                n = "".join(random.choices(string.ascii_uppercase, k=1) + random.choices(string.ascii_lowercase, k=4))
                parts.append(f"class {n}:\n    x = {random.randint(0, 100)}\n")
            elif kind == "assign":
                n = "".join(random.choices(string.ascii_lowercase, k=3))
                parts.append(f"{n} = {random.randint(0, 1000)}\n")
            else:
                mod = random.choice(["os", "sys", "json", "re", "math"])
                parts.append(f"import {mod}\n")
        return "\n".join(parts)

    def _random_non_python() -> tuple[str, str]:
        """랜덤 비Python 콘텐츠와 확장자를 반환한다."""
        ext = random.choice(NON_PYTHON_EXTS + UNKNOWN_EXTS)
        lines = random.randint(1, 200)
        content = "\n".join(
            "".join(random.choices(string.printable.replace("\n", ""), k=random.randint(5, 80)))
            for _ in range(lines)
        )
        return ext, content

    for i in range(count):
        tc_id = f"TC-RANDOM-{i + 1:05d}"
        variant = random.random()

        if variant < 0.4:
            # 랜덤 Python
            content = _random_python()
            cases.append(TestCase(
                id=tc_id,
                category="random",
                file_path="random.py",
                content=content,
                description="무작위 Python 코드 퍼징",
                expected={"type": "list", "no_exception": True},
            ))
        elif variant < 0.6:
            # 랜덤 비Python
            ext, content = _random_non_python()
            cases.append(TestCase(
                id=tc_id,
                category="random",
                file_path=f"random{ext}",
                content=content,
                description=f"무작위 비Python 퍼징 ({ext})",
                expected={"type": "list", "no_exception": True},
            ))
        elif variant < 0.75:
            # 랜덤 SyntaxError Python
            garbage = "".join(random.choices(string.printable.replace("\n", ""), k=random.randint(5, 50)))
            content = f"def {garbage}(\n    pass\n"
            cases.append(TestCase(
                id=tc_id,
                category="random",
                file_path="random_syntax.py",
                content=content,
                description="무작위 SyntaxError Python 퍼징",
                expected={"type": "list", "no_exception": True},
            ))
        elif variant < 0.85:
            # 랜덤 특수 문자 혼합
            content = "".join(
                random.choices(
                    string.printable + "한글テスト中文العربية",
                    k=random.randint(10, 500)
                )
            )
            cases.append(TestCase(
                id=tc_id,
                category="random",
                file_path="random_unicode.py",
                content=content,
                description="무작위 유니코드 혼합 퍼징",
                expected={"type": "list", "no_exception": True},
            ))
        else:
            # 완전 무작위 콘텐츠
            ext = random.choice([".py"] + NON_PYTHON_EXTS + UNKNOWN_EXTS)
            content = "".join(
                random.choices(string.printable, k=random.randint(0, 1000))
            )
            cases.append(TestCase(
                id=tc_id,
                category="random",
                file_path=f"random{ext}",
                content=content,
                description="완전 무작위 퍼징",
                expected={"type": "list", "no_exception": True},
            ))

    return cases


# ---------------------------------------------------------------------------
# 메인 생성 함수
# ---------------------------------------------------------------------------

def generate_all_cases(total: int = 10000) -> list[TestCase]:
    """카테고리별 비율에 맞춰 전체 케이스를 생성한다."""
    counts = {
        "normal":   int(total * 0.30),
        "boundary": int(total * 0.20),
        "invalid":  int(total * 0.20),
        "stress":   int(total * 0.15),
        "random":   int(total * 0.15),
    }
    # 반올림 오차 보정
    diff = total - sum(counts.values())
    counts["normal"] += diff

    print(f"카테고리별 생성 계획:")
    for cat, n in counts.items():
        print(f"  {cat}: {n}건")

    all_cases: list[TestCase] = []
    all_cases.extend(_gen_normal_cases(counts["normal"]))
    all_cases.extend(_gen_boundary_cases(counts["boundary"]))
    all_cases.extend(_gen_invalid_cases(counts["invalid"]))
    all_cases.extend(_gen_stress_cases(counts["stress"]))
    all_cases.extend(_gen_random_cases(counts["random"]))

    # ID 재할당 (전체 순서로)
    for i, tc in enumerate(all_cases):
        tc.id = f"TC-MODULE-{i + 1:05d}"

    return all_cases


def _safe_dict(tc: TestCase) -> dict:
    """TestCase를 JSON 직렬화 안전한 딕셔너리로 변환한다.

    surrogate 문자 등 직렬화 불가 문자를 replacement character로 대체한다.
    """
    d = asdict(tc)
    # content 필드를 안전하게 인코딩
    if "content" in d:
        try:
            json.dumps(d["content"])
        except (UnicodeEncodeError, ValueError):
            d["content"] = d["content"].encode("utf-8", errors="replace").decode("utf-8")
    return d


def save_cases_jsonl(cases: list[TestCase], output_path: Path) -> None:
    """테스트 케이스를 JSONL 형식으로 저장한다."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for tc in cases:
            f.write(json.dumps(_safe_dict(tc), ensure_ascii=False) + "\n")
    print(f"저장 완료: {output_path} ({len(cases)}건)")


def main() -> None:
    """CLI 진입점."""
    parser = argparse.ArgumentParser(description="ASTChunker QC 테스트 케이스 생성기")
    parser.add_argument("--module", default="src/rag/chunker.py", help="대상 모듈 경로")
    parser.add_argument("--count", type=int, default=10000, help="생성할 케이스 수")
    parser.add_argument("--output", default="tests/qc/chunker/", help="출력 디렉토리")
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
