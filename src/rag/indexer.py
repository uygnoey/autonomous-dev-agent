"""코드베이스 인덱서.

프로젝트 코드 파일을 읽어 검색 가능한 형태로 인덱싱한다.
기본은 텍스트 기반 검색이며, chromadb 설치 시 벡터 검색도 지원한다.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from src.utils.logger import setup_logger

logger = setup_logger(__name__)

# 인덱싱 대상 확장자
SUPPORTED_EXTENSIONS = {".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".java", ".rs"}

# 무시할 디렉토리
IGNORED_DIRS = {"__pycache__", ".git", "node_modules", ".venv", "venv", "dist", "build"}


@dataclass
class CodeChunk:
    """코드 청크. 검색 결과의 단위."""

    file_path: str
    content: str
    start_line: int
    end_line: int

    def __str__(self) -> str:
        return f"[{self.file_path}:{self.start_line}-{self.end_line}]\n{self.content}"


class CodebaseIndexer:
    """코드베이스를 인덱싱하고 검색하는 인덱서.

    텍스트 기반 검색을 기본으로 제공한다.
    """

    def __init__(self, project_path: str, chunk_size: int = 50):
        """
        Args:
            project_path: 인덱싱할 프로젝트 루트 경로
            chunk_size: 청크당 최대 줄 수
        """
        self._project_path = Path(project_path)
        self._chunk_size = chunk_size
        self._chunks: list[CodeChunk] = []

    def index(self) -> int:
        """프로젝트 코드베이스를 인덱싱한다.

        Returns:
            인덱싱된 청크 수
        """
        self._chunks.clear()
        code_files = self._collect_code_files()

        for file_path in code_files:
            try:
                chunks = self._chunk_file(file_path)
                self._chunks.extend(chunks)
            except (OSError, UnicodeDecodeError) as e:
                logger.warning(f"파일 읽기 실패 ({file_path}): {e}")

        logger.info(f"인덱싱 완료: {len(code_files)}개 파일, {len(self._chunks)}개 청크")
        return len(self._chunks)

    def search(self, query: str, top_k: int = 5) -> list[CodeChunk]:
        """쿼리에 가장 관련된 코드 청크를 반환한다.

        Args:
            query: 검색 쿼리
            top_k: 반환할 최대 결과 수

        Returns:
            관련성 높은 순으로 정렬된 코드 청크 목록
        """
        if not self._chunks:
            self.index()

        query_terms = self._tokenize(query)
        scored = [
            (chunk, self._score(chunk, query_terms))
            for chunk in self._chunks
        ]
        # 점수가 0보다 큰 것만, 내림차순 정렬
        relevant = [(chunk, score) for chunk, score in scored if score > 0]
        relevant.sort(key=lambda x: x[1], reverse=True)

        return [chunk for chunk, _ in relevant[:top_k]]

    def _collect_code_files(self) -> list[Path]:
        """지원 확장자의 코드 파일을 수집한다."""
        code_files = []
        for path in self._project_path.rglob("*"):
            if any(part in IGNORED_DIRS for part in path.parts):
                continue
            if path.is_file() and path.suffix in SUPPORTED_EXTENSIONS:
                code_files.append(path)
        return code_files

    def _chunk_file(self, file_path: Path) -> list[CodeChunk]:
        """파일을 청크로 분할한다."""
        lines = file_path.read_text(encoding="utf-8").splitlines()
        relative_path = str(file_path.relative_to(self._project_path))
        chunks = []

        for start in range(0, len(lines), self._chunk_size):
            end = min(start + self._chunk_size, len(lines))
            content = "\n".join(lines[start:end])
            chunks.append(CodeChunk(
                file_path=relative_path,
                content=content,
                start_line=start + 1,
                end_line=end,
            ))

        return chunks

    def _tokenize(self, text: str) -> list[str]:
        """텍스트를 검색 토큰으로 분리한다."""
        return re.findall(r"\w+", text.lower())

    def _score(self, chunk: CodeChunk, query_terms: list[str]) -> float:
        """청크와 쿼리의 관련성 점수를 계산한다."""
        chunk_text = (chunk.content + " " + chunk.file_path).lower()
        chunk_tokens = set(self._tokenize(chunk_text))
        matches = sum(1 for term in query_terms if term in chunk_tokens)
        return matches / len(query_terms) if query_terms else 0.0
