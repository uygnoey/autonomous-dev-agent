"""ASTChunker 유닛 테스트.

테스트 대상: src/rag/chunker.py — ASTChunker 클래스
커버리지 목표: 90% 이상

테스트 케이스:
1. Python 함수 추출 정확도
2. 클래스 + 메서드 분리
3. 비Python 폴백
4. MIN_LINES 경계 케이스
5. MAX_LINES 경계 케이스
6. SyntaxError 파일 처리
7. 빈 파일 처리
8. 데코레이터 포함 확인
9. 모듈 레벨 코드 추출
"""

import pytest

from src.core.domain import CodeChunk
from src.rag.chunker import ASTChunker


@pytest.fixture
def chunker() -> ASTChunker:
    """ASTChunker 인스턴스를 제공하는 픽스처."""
    return ASTChunker()


class TestPythonFunctionExtraction:
    """Python 함수 추출 정확도 테스트."""

    def test_python_function_extraction(self, chunker: ASTChunker) -> None:
        """Python 함수가 정확히 추출되는지 검증."""
        # Arrange
        content = '''\
def hello():
    """인사 함수."""
    x = 1
    y = 2
    return "world"

async def async_func():
    """비동기 함수."""
    x = 1
    y = 2
    return None
'''
        # Act
        chunks = chunker.chunk("test.py", content)

        # Assert: function 청크가 2개 생성되어야 함
        function_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(function_chunks) == 2

        names = {c.name for c in function_chunks}
        assert "hello" in names
        assert "async_func" in names

        # 각 청크의 메타데이터 검증
        for chunk in function_chunks:
            assert chunk.chunk_type == "function"
            assert isinstance(chunk.start_line, int)
            assert isinstance(chunk.end_line, int)
            assert chunk.start_line <= chunk.end_line
            assert chunk.file_path == "test.py"

    def test_function_chunk_line_numbers_are_correct(self, chunker: ASTChunker) -> None:
        """함수 청크의 start_line, end_line이 정확한지 검증."""
        # Arrange
        content = '''\
x = 1

def target_func():
    a = 1
    b = 2
    c = 3
    return a + b + c
'''
        # Act
        chunks = chunker.chunk("test.py", content)

        # Assert
        func_chunks = [c for c in chunks if c.name == "target_func"]
        assert len(func_chunks) == 1

        func = func_chunks[0]
        # start_line=3 (def target_func: 줄), end_line=7
        assert func.start_line == 3
        assert func.end_line == 7


class TestClassAndMethodSeparation:
    """클래스 + 메서드 분리 테스트."""

    def test_class_and_method_separation(self, chunker: ASTChunker) -> None:
        """클래스 전체 청크 + 개별 메서드 청크가 모두 생성되는지 검증.

        메서드는 MIN_LINES(5) 이상이어야 별도 청크로 추출된다.
        """
        # Arrange — 각 메서드를 5줄 이상으로 작성
        content = '''\
class MyClass:
    def method1(self):
        x = 1
        y = 2
        z = 3
        return x + y + z

    def method2(self):
        a = 1
        b = 2
        c = 3
        return a * b * c
'''
        # Act
        chunks = chunker.chunk("test.py", content)

        # Assert: class 청크 1개 + method 청크 2개
        class_chunks = [c for c in chunks if c.chunk_type == "class"]
        method_chunks = [c for c in chunks if c.chunk_type == "method"]

        assert len(class_chunks) == 1
        assert len(method_chunks) == 2

        assert class_chunks[0].name == "MyClass"

        method_names = {c.name for c in method_chunks}
        assert "method1" in method_names
        assert "method2" in method_names

    def test_class_chunk_covers_entire_class(self, chunker: ASTChunker) -> None:
        """클래스 청크가 클래스 전체를 포함하는지 검증."""
        # Arrange
        content = '''\
class Container:
    x = 1

    def compute(self):
        a = 1
        b = 2
        c = 3
        return a + b + c
'''
        # Act
        chunks = chunker.chunk("test.py", content)

        # Assert
        class_chunks = [c for c in chunks if c.chunk_type == "class"]
        assert len(class_chunks) == 1

        cls = class_chunks[0]
        assert cls.start_line == 1
        assert "class Container" in cls.content
        assert "def compute" in cls.content


class TestNonPythonFallback:
    """비Python 파일 폴백 테스트."""

    def test_non_python_fallback_produces_block_chunks(self, chunker: ASTChunker) -> None:
        """비Python 파일이 block 청크로 분할되는지 검증."""
        # Arrange — 100줄 JS 내용
        content = "\n".join([f"const line{i} = {i};" for i in range(100)])

        # Act
        chunks = chunker.chunk("test.js", content)

        # Assert
        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.chunk_type == "block"
            assert chunk.name is None

    def test_non_python_fallback_50_line_blocks(self, chunker: ASTChunker) -> None:
        """비Python 파일이 50줄 블록 + 10줄 오버랩으로 분할되는지 검증."""
        # Arrange — 정확히 100줄
        content = "\n".join([f"line {i}" for i in range(100)])

        # Act
        chunks = chunker.chunk("test.js", content)

        # Assert: 첫 번째 청크는 1~50줄, 두 번째는 41~90줄(오버랩), 세 번째는 81~100줄
        assert chunks[0].start_line == 1
        assert chunks[0].end_line == 50

        # 두 번째 청크: step = BLOCK_SIZE - OVERLAP = 40, 두 번째 시작 = 41
        assert chunks[1].start_line == 41

    def test_typescript_file_uses_fallback(self, chunker: ASTChunker) -> None:
        """TypeScript 파일도 블록 폴백이 적용되는지 검증."""
        # Arrange
        content = "\n".join([f"const x{i}: number = {i};" for i in range(60)])

        # Act
        chunks = chunker.chunk("test.ts", content)

        # Assert
        assert len(chunks) > 0
        assert all(c.chunk_type == "block" for c in chunks)


class TestMinLinesBoundary:
    """MIN_LINES(5) 경계 케이스 테스트."""

    def test_tiny_function_not_extracted_as_separate_chunk(self, chunker: ASTChunker) -> None:
        """5줄 미만 함수가 별도 청크로 추출되지 않는지 검증."""
        # Arrange — tiny: 2줄 (MIN_LINES=5 미만)
        content = '''\
def tiny():
    pass

def normal_func():
    x = 1
    y = 2
    z = 3
    return x + y + z
'''
        # Act
        chunks = chunker.chunk("test.py", content)

        # Assert: tiny는 별도 function 청크 없음
        function_chunks = [c for c in chunks if c.chunk_type == "function"]
        names = {c.name for c in function_chunks}
        assert "tiny" not in names

        # normal_func는 별도 청크 있음 (5줄 이상)
        assert "normal_func" in names

    def test_function_at_min_lines_boundary_is_extracted(self, chunker: ASTChunker) -> None:
        """정확히 MIN_LINES(5)줄 함수가 추출되는지 검증."""
        # Arrange — 정확히 5줄 함수
        content = '''\
def exactly_five():
    a = 1
    b = 2
    c = 3
    return a + b + c
'''
        # Act
        chunks = chunker.chunk("test.py", content)

        # Assert: 5줄 함수는 추출됨
        function_chunks = [c for c in chunks if c.chunk_type == "function"]
        names = {c.name for c in function_chunks}
        assert "exactly_five" in names

    def test_tiny_function_included_in_module_chunk(self, chunker: ASTChunker) -> None:
        """MIN_LINES 미만 함수의 코드가 module 청크에 포함되는지 검증."""
        # Arrange
        content = '''\
def tiny():
    pass
x = 1
'''
        # Act
        chunks = chunker.chunk("test.py", content)

        # Assert: module 청크에 tiny 함수 코드가 포함됨
        module_chunks = [c for c in chunks if c.chunk_type == "module"]
        all_module_content = "\n".join(c.content for c in module_chunks)
        assert "def tiny" in all_module_content or "tiny" in all_module_content


class TestMaxLinesBoundary:
    """MAX_LINES(100) 경계 케이스 테스트."""

    def test_large_class_does_not_produce_class_chunk(self, chunker: ASTChunker) -> None:
        """100줄 초과 클래스는 class 청크 대신 method 청크만 반환하는지 검증."""
        # Arrange — 101줄 클래스 생성 (클래스 선언 1줄 + 메서드들)
        method_lines = "\n".join(
            [
                "    def method_a(self):",
                "        a1 = 1",
                "        a2 = 2",
                "        a3 = 3",
                "        a4 = 4",
                "        return a1 + a2 + a3 + a4",
            ]
        )
        # 각 메서드 6줄 × 17개 = 102줄 + 클래스 선언 1줄 = 103줄
        methods = "\n\n".join(
            [
                f"    def method_{i}(self):\n        v{i}1 = 1\n        v{i}2 = 2\n        v{i}3 = 3\n        return v{i}1 + v{i}2 + v{i}3"
                for i in range(17)
            ]
        )
        content = f"class BigClass:\n{methods}\n"

        # Act
        chunks = chunker.chunk("test.py", content)

        # Assert: class 청크 없음, method 청크만 있음
        class_chunks = [c for c in chunks if c.chunk_type == "class"]
        method_chunks = [c for c in chunks if c.chunk_type == "method"]

        assert len(class_chunks) == 0
        assert len(method_chunks) > 0

    def test_class_at_max_lines_boundary_has_class_chunk(self, chunker: ASTChunker) -> None:
        """정확히 MAX_LINES(100)줄 이하 클래스는 class 청크가 생성되는지 검증."""
        # Arrange — 작은 클래스 (MAX_LINES 이하)
        content = '''\
class SmallClass:
    def method_one(self):
        x = 1
        y = 2
        z = 3
        return x + y + z
'''
        # Act
        chunks = chunker.chunk("test.py", content)

        # Assert: class 청크 있음
        class_chunks = [c for c in chunks if c.chunk_type == "class"]
        assert len(class_chunks) == 1
        assert class_chunks[0].name == "SmallClass"


class TestSyntaxErrorFallback:
    """SyntaxError 파일 처리 테스트."""

    def test_syntax_error_fallback(self, chunker: ASTChunker) -> None:
        """파싱 실패 시 고정 크기 폴백이 작동하는지 검증."""
        # Arrange
        content = "def broken( syntax error"

        # Act
        chunks = chunker.chunk("bad.py", content)

        # Assert: 빈 리스트가 아니어야 함
        assert len(chunks) > 0
        assert all(c.chunk_type == "block" for c in chunks)

    def test_syntax_error_fallback_has_content(self, chunker: ASTChunker) -> None:
        """SyntaxError 폴백 청크가 원본 내용을 포함하는지 검증."""
        # Arrange
        content = "def broken( syntax error\nsome more content here"

        # Act
        chunks = chunker.chunk("bad.py", content)

        # Assert: 원본 내용이 청크에 포함됨
        all_content = "\n".join(c.content for c in chunks)
        assert "broken" in all_content


class TestEmptyFile:
    """빈 파일 처리 테스트."""

    def test_empty_file_returns_empty_list(self, chunker: ASTChunker) -> None:
        """빈 파일이 빈 리스트를 반환하는지 검증."""
        # Arrange & Act
        chunks = chunker.chunk("empty.py", "")

        # Assert
        assert chunks == []

    def test_whitespace_only_file_returns_empty_list(self, chunker: ASTChunker) -> None:
        """공백만 있는 파일이 빈 리스트를 반환하는지 검증."""
        # Arrange & Act
        chunks = chunker.chunk("whitespace.py", "   \n  \n  ")

        # Assert
        assert chunks == []

    def test_empty_non_python_file_returns_empty_list(self, chunker: ASTChunker) -> None:
        """빈 비Python 파일도 빈 리스트를 반환하는지 검증."""
        # Arrange & Act
        chunks = chunker.chunk("empty.js", "")

        # Assert
        assert chunks == []


class TestDecoratorInclusion:
    """데코레이터 포함 테스트."""

    def test_decorator_included_in_function_chunk(self, chunker: ASTChunker) -> None:
        """데코레이터가 함수 청크에 포함되는지 검증."""
        # Arrange
        content = '''\
@decorator
@another_decorator
def decorated_func():
    x = 1
    y = 2
    return x + y
'''
        # Act
        chunks = chunker.chunk("test.py", content)

        # Assert
        function_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(function_chunks) == 1

        func = function_chunks[0]
        # start_line이 @decorator 줄(1줄)이어야 함
        assert func.start_line == 1
        assert "@decorator" in func.content
        assert "@another_decorator" in func.content

    def test_decorated_class_start_line_is_decorator(self, chunker: ASTChunker) -> None:
        """데코레이터가 있는 클래스의 start_line이 데코레이터 줄인지 검증."""
        # Arrange
        content = '''\
@class_decorator
class DecoratedClass:
    def method(self):
        x = 1
        y = 2
        return x + y
'''
        # Act
        chunks = chunker.chunk("test.py", content)

        # Assert
        class_chunks = [c for c in chunks if c.chunk_type == "class"]
        assert len(class_chunks) == 1

        cls = class_chunks[0]
        assert cls.start_line == 1
        assert "@class_decorator" in cls.content


class TestModuleLevelCode:
    """모듈 레벨 코드 추출 테스트."""

    def test_module_level_code_extracted(self, chunker: ASTChunker) -> None:
        """함수/클래스 외부 코드가 module 청크로 추출되는지 검증."""
        # Arrange
        content = '''\
import os

x = 1
y = 2

def func():
    a = 1
    b = 2
    c = 3
    return a + b + c

z = 3
'''
        # Act
        chunks = chunker.chunk("test.py", content)

        # Assert: module 청크 존재
        module_chunks = [c for c in chunks if c.chunk_type == "module"]
        assert len(module_chunks) > 0

        all_module_content = "\n".join(c.content for c in module_chunks)
        # import, x, y 포함
        assert "import os" in all_module_content
        assert "x = 1" in all_module_content
        assert "y = 2" in all_module_content

    def test_module_chunk_does_not_include_function_lines(self, chunker: ASTChunker) -> None:
        """module 청크가 함수 본문을 포함하지 않는지 검증."""
        # Arrange
        content = '''\
CONSTANT = 42

def big_function():
    a = 1
    b = 2
    c = 3
    return a + b + c
'''
        # Act
        chunks = chunker.chunk("test.py", content)

        # Assert
        module_chunks = [c for c in chunks if c.chunk_type == "module"]
        assert len(module_chunks) > 0

        # module 청크에 CONSTANT 포함
        all_module_content = "\n".join(c.content for c in module_chunks)
        assert "CONSTANT = 42" in all_module_content

        # function 청크는 별도로 존재
        function_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(function_chunks) == 1
        assert function_chunks[0].name == "big_function"

    def test_imports_only_file_produces_module_chunk(self, chunker: ASTChunker) -> None:
        """import만 있는 파일이 module 청크를 생성하는지 검증."""
        # Arrange
        content = '''\
import os
import sys
from pathlib import Path
'''
        # Act
        chunks = chunker.chunk("test.py", content)

        # Assert
        module_chunks = [c for c in chunks if c.chunk_type == "module"]
        assert len(module_chunks) > 0
        all_module_content = "\n".join(c.content for c in module_chunks)
        assert "import os" in all_module_content


class TestCodeChunkProperties:
    """CodeChunk 속성 검증 테스트."""

    def test_chunk_has_all_required_fields(self, chunker: ASTChunker) -> None:
        """생성된 청크가 모든 필수 필드를 가지는지 검증."""
        # Arrange
        content = '''\
def sample_func():
    x = 1
    y = 2
    z = 3
    return x + y + z
'''
        # Act
        chunks = chunker.chunk("test.py", content)

        # Assert
        assert len(chunks) > 0
        for chunk in chunks:
            assert isinstance(chunk, CodeChunk)
            assert chunk.file_path == "test.py"
            assert isinstance(chunk.content, str)
            assert len(chunk.content) > 0
            assert isinstance(chunk.start_line, int)
            assert isinstance(chunk.end_line, int)
            assert chunk.start_line >= 1
            assert chunk.end_line >= chunk.start_line
            assert chunk.chunk_type in {"function", "class", "method", "module", "block"}

    def test_chunk_content_matches_source_lines(self, chunker: ASTChunker) -> None:
        """청크의 content가 실제 소스 라인과 일치하는지 검증."""
        # Arrange
        content = '''\
def verify_content():
    first_line = 1
    second_line = 2
    third_line = 3
    return first_line + second_line + third_line
'''
        # Act
        chunks = chunker.chunk("test.py", content)

        # Assert
        function_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(function_chunks) == 1

        func = function_chunks[0]
        assert "def verify_content" in func.content
        assert "first_line = 1" in func.content
        assert "return first_line" in func.content

    def test_async_function_extracted_as_function_type(self, chunker: ASTChunker) -> None:
        """async 함수가 function 타입으로 추출되는지 검증."""
        # Arrange
        content = '''\
async def async_handler():
    x = 1
    y = 2
    z = 3
    return x + y + z
'''
        # Act
        chunks = chunker.chunk("test.py", content)

        # Assert
        function_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(function_chunks) == 1
        assert function_chunks[0].name == "async_handler"
