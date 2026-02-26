"""AST 기반 코드 청크 분할기.

Python 파일은 ast 모듈로 함수·클래스·메서드 경계를 추출하여 의미 단위로 분할한다.
비Python 파일은 50줄 고정 크기 + 10줄 오버랩 폴백을 사용한다.
SyntaxError 발생 시에도 폴백으로 graceful 처리한다.
"""

from __future__ import annotations

import ast
from typing import Literal

from src.core.domain import CodeChunk
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

# chunk_type 허용 리터럴 타입
ChunkType = Literal["function", "class", "method", "module", "block"]

# 지원 확장자
_PYTHON_SUFFIX = ".py"
_FALLBACK_SUFFIXES = {".js", ".ts", ".tsx", ".jsx", ".yaml", ".yml", ".md", ".go", ".java", ".rs"}


class ASTChunker:
    """AST 기반 코드 청크 분할기.

    ChunkerProtocol(src/core/interfaces.py)을 구조적으로 준수한다.

    Python 파일: ast 모듈로 함수/클래스 경계를 추출하여 의미 단위 청크 생성.
    비Python 파일: 50줄 고정 크기 + 10줄 오버랩 블록 청크 생성.
    """

    MIN_LINES: int = 5    # 5줄 미만 함수는 module 청크에 병합
    MAX_LINES: int = 100  # 100줄 초과 ClassDef는 메서드별 서브청킹
    BLOCK_SIZE: int = 50  # 비Python 파일 블록 크기
    OVERLAP: int = 10     # 비Python 파일 오버랩 줄 수

    def chunk(self, file_path: str, content: str) -> list[CodeChunk]:
        """파일 내용을 CodeChunk 리스트로 분할한다.

        Args:
            file_path: 파일 경로 (메타데이터 용도, 1-indexed 라인 기준)
            content: 파일 전체 텍스트 내용

        Returns:
            분할된 CodeChunk 목록. 빈 파일이면 빈 리스트 반환.
        """
        if not content or not content.strip():
            return []

        if file_path.endswith(_PYTHON_SUFFIX):
            return self._chunk_python(file_path, content)

        return self._chunk_fallback(file_path, content, chunk_type="block")

    # ------------------------------------------------------------------
    # Python 파일 처리
    # ------------------------------------------------------------------

    def _chunk_python(self, file_path: str, content: str) -> list[CodeChunk]:
        """Python 파일을 AST로 파싱하여 청크를 생성한다.

        SyntaxError 발생 시 고정 크기 폴백을 사용한다.

        Args:
            file_path: 파일 경로
            content: 파일 텍스트

        Returns:
            CodeChunk 목록
        """
        try:
            tree = ast.parse(content)
        except SyntaxError:
            logger.warning(
                f"SyntaxError: AST 파싱 실패, 고정 크기 폴백 적용 ({file_path})"
            )
            return self._chunk_fallback(file_path, content, chunk_type="block")

        lines = content.splitlines()
        return self._extract_chunks(file_path, lines, tree)

    def _extract_chunks(
        self,
        file_path: str,
        lines: list[str],
        tree: ast.Module,
    ) -> list[CodeChunk]:
        """AST 트리에서 함수·클래스·모듈 청크를 추출한다.

        처리 순서:
        1. 최상위 FunctionDef/AsyncFunctionDef → "function" 청크
        2. 최상위 ClassDef → "class" 청크 (크기 초과 시 서브청킹)
           ClassDef 내부 메서드 → 별도 "method" 청크
        3. 함수/클래스에 속하지 않는 나머지 코드 → "module" 청크

        Args:
            file_path: 파일 경로
            lines: 파일 줄 목록 (0-indexed)
            tree: 파싱된 AST 모듈

        Returns:
            CodeChunk 목록
        """
        chunks: list[CodeChunk] = []

        # 최상위 노드 처리 (함수, 클래스)
        # 함수/클래스가 점유하는 줄 집합을 추적하여 module 청크 생성 시 제외
        occupied_lines: set[int] = set()

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_chunks = self._process_function(
                    file_path, lines, node, chunk_type="function"
                )
                chunks.extend(func_chunks)
                if func_chunks:
                    # MIN_LINES 이상인 경우만 점유 표시 (병합된 경우 제외)
                    start = _decorator_start(node)
                    end = _end_lineno(node)
                    occupied_lines.update(range(start - 1, end))

            elif isinstance(node, ast.ClassDef):
                class_chunks = self._process_class(file_path, lines, node)
                chunks.extend(class_chunks)
                start = _decorator_start(node)
                end = _end_lineno(node)
                occupied_lines.update(range(start - 1, end))

        # 함수/클래스에 속하지 않는 줄 → module 청크
        module_chunks = self._extract_module_chunks(
            file_path, lines, occupied_lines
        )
        chunks.extend(module_chunks)

        return chunks

    def _process_function(
        self,
        file_path: str,
        lines: list[str],
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        chunk_type: ChunkType,
    ) -> list[CodeChunk]:
        """함수/메서드 노드를 CodeChunk로 변환한다.

        MIN_LINES 미만이면 빈 리스트를 반환하여 상위에서 module 청크에 포함되도록 한다.

        Args:
            file_path: 파일 경로
            lines: 파일 줄 목록
            node: 함수/메서드 AST 노드
            chunk_type: "function" 또는 "method"

        Returns:
            CodeChunk 목록 (0~1개)
        """
        start_line = _decorator_start(node)     # 1-indexed
        end_line = _end_lineno(node)
        line_count = end_line - start_line + 1

        # MIN_LINES 미만이면 module 청크에 병합되도록 빈 리스트 반환
        if line_count < self.MIN_LINES:
            return []

        content = _extract_lines(lines, start_line, end_line)
        return [
            CodeChunk(
                file_path=file_path,
                content=content,
                start_line=start_line,
                end_line=end_line,
                chunk_type=chunk_type,
                name=node.name,
            )
        ]

    def _process_class(
        self,
        file_path: str,
        lines: list[str],
        node: ast.ClassDef,
    ) -> list[CodeChunk]:
        """ClassDef 노드를 처리한다.

        클래스 전체 청크 1개를 생성하고,
        내부 메서드마다 별도 "method" 청크를 추가로 생성한다.
        클래스가 MAX_LINES를 초과하면 클래스 전체 청크 대신 메서드 청크만 반환한다.

        Args:
            file_path: 파일 경로
            lines: 파일 줄 목록
            node: ClassDef AST 노드

        Returns:
            CodeChunk 목록
        """
        chunks: list[CodeChunk] = []
        start_line = _decorator_start(node)       # 1-indexed
        end_line = _end_lineno(node)
        line_count = end_line - start_line + 1

        # 클래스 전체 청크 (MAX_LINES 이하일 때만 생성)
        if line_count <= self.MAX_LINES:
            class_content = _extract_lines(lines, start_line, end_line)
            chunks.append(
                CodeChunk(
                    file_path=file_path,
                    content=class_content,
                    start_line=start_line,
                    end_line=end_line,
                    chunk_type="class",
                    name=node.name,
                )
            )

        # 내부 메서드 청크 (항상 생성)
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_chunks = self._process_function(
                    file_path, lines, child, chunk_type="method"
                )
                chunks.extend(method_chunks)

        return chunks

    def _extract_module_chunks(
        self,
        file_path: str,
        lines: list[str],
        occupied_lines: set[int],
    ) -> list[CodeChunk]:
        """함수·클래스에 속하지 않는 모듈 레벨 코드를 청크로 추출한다.

        연속된 비점유 줄 블록을 하나의 "module" 청크로 묶는다.
        공백/빈 줄만으로 이루어진 블록은 생성하지 않는다.

        Args:
            file_path: 파일 경로
            lines: 파일 줄 목록 (0-indexed)
            occupied_lines: 함수·클래스가 점유한 줄 인덱스 집합 (0-indexed)

        Returns:
            module CodeChunk 목록
        """
        chunks: list[CodeChunk] = []
        start_idx: int | None = None

        def _flush(end_idx: int) -> None:
            """현재까지 수집된 모듈 레벨 줄을 청크로 플러시한다."""
            nonlocal start_idx
            if start_idx is None:
                return
            block_lines = lines[start_idx:end_idx]
            if any(ln.strip() for ln in block_lines):
                content = "\n".join(block_lines)
                chunks.append(
                    CodeChunk(
                        file_path=file_path,
                        content=content,
                        start_line=start_idx + 1,    # 1-indexed
                        end_line=end_idx,
                        chunk_type="module",
                        name=None,
                    )
                )
            start_idx = None

        for idx, _ in enumerate(lines):
            if idx in occupied_lines:
                _flush(idx)
            else:
                if start_idx is None:
                    start_idx = idx

        # 마지막 블록 처리
        _flush(len(lines))

        return chunks

    # ------------------------------------------------------------------
    # 비Python 폴백 처리
    # ------------------------------------------------------------------

    def _chunk_fallback(
        self,
        file_path: str,
        content: str,
        chunk_type: ChunkType,
    ) -> list[CodeChunk]:
        """고정 크기 블록으로 파일을 분할한다.

        BLOCK_SIZE(50줄) 단위로 분할하고 OVERLAP(10줄) 오버랩을 적용한다.

        Args:
            file_path: 파일 경로
            content: 파일 텍스트
            chunk_type: 청크 타입 ("block")

        Returns:
            CodeChunk 목록
        """
        lines = content.splitlines()
        if not lines:
            return []

        chunks: list[CodeChunk] = []
        total = len(lines)
        step = self.BLOCK_SIZE - self.OVERLAP  # 슬라이딩 스텝

        start = 0
        while start < total:
            end = min(start + self.BLOCK_SIZE, total)
            block_content = "\n".join(lines[start:end])

            if block_content.strip():
                chunks.append(
                    CodeChunk(
                        file_path=file_path,
                        content=block_content,
                        start_line=start + 1,    # 1-indexed
                        end_line=end,
                        chunk_type=chunk_type,
                        name=None,
                    )
                )

            if end == total:
                break
            start += step

        return chunks


# ------------------------------------------------------------------
# 모듈 레벨 헬퍼 함수
# ------------------------------------------------------------------


def _end_lineno(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> int:
    """AST 노드의 마지막 줄 번호를 반환한다.

    ast.parse()로 생성된 노드는 항상 end_lineno를 가지지만
    mypy는 Optional[int]로 추론한다. assert로 None 가드를 삽입한다.

    Args:
        node: 함수, 비동기 함수, 또는 클래스 AST 노드

    Returns:
        마지막 줄 번호 (1-indexed)
    """
    assert node.end_lineno is not None, "end_lineno는 ast.parse() 결과에서 항상 존재해야 합니다."
    return node.end_lineno


def _decorator_start(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> int:
    """데코레이터가 있으면 첫 데코레이터 줄 번호를, 없으면 노드 줄 번호를 반환한다.

    데코레이터를 함수/클래스 청크에 포함시켜 컨텍스트를 보존한다.

    Args:
        node: 함수, 비동기 함수, 또는 클래스 AST 노드

    Returns:
        시작 줄 번호 (1-indexed)
    """
    if node.decorator_list:
        return node.decorator_list[0].lineno
    return node.lineno


def _extract_lines(lines: list[str], start_line: int, end_line: int) -> str:
    """1-indexed 라인 범위로 줄 목록에서 텍스트를 추출한다.

    Args:
        lines: 파일 줄 목록 (0-indexed)
        start_line: 시작 줄 번호 (1-indexed, 포함)
        end_line: 끝 줄 번호 (1-indexed, 포함)

    Returns:
        줄바꿈으로 결합된 텍스트
    """
    return "\n".join(lines[start_line - 1 : end_line])
