"""CodebaseIndexer 유닛 테스트."""

from pathlib import Path

import pytest

from src.rag.indexer import CodebaseIndexer


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """테스트용 임시 프로젝트 구조 생성."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text(
        "def hello():\n    return 'Hello, World!'\n\ndef add(a, b):\n    return a + b\n"
    )
    (tmp_path / "src" / "utils.py").write_text(
        "import os\n\ndef get_env(key: str) -> str:\n    return os.environ.get(key, '')\n"
    )
    (tmp_path / "README.md").write_text("# Test Project\n")  # 무시되어야 함
    return tmp_path


class TestCodebaseIndexer:
    def test_index_returns_chunk_count(self, tmp_project: Path):
        indexer = CodebaseIndexer(str(tmp_project))
        count = indexer.index()
        assert count > 0

    def test_index_ignores_non_code_files(self, tmp_project: Path):
        indexer = CodebaseIndexer(str(tmp_project))
        indexer.index()
        # .md 파일은 인덱싱되지 않아야 함
        all_paths = [c.file_path for c in indexer._chunks]
        assert not any(p.endswith(".md") for p in all_paths)

    def test_search_returns_relevant_chunks(self, tmp_project: Path):
        indexer = CodebaseIndexer(str(tmp_project))
        indexer.index()

        results = indexer.search("hello")
        assert len(results) > 0
        assert any("hello" in chunk.content.lower() for chunk in results)

    def test_search_returns_empty_for_no_match(self, tmp_project: Path):
        indexer = CodebaseIndexer(str(tmp_project))
        indexer.index()

        results = indexer.search("zzz_no_such_thing_xyz_12345")
        assert results == []

    def test_search_limits_results_by_top_k(self, tmp_project: Path):
        # 더 많은 파일 추가
        for i in range(10):
            (tmp_project / "src" / f"module_{i}.py").write_text(
                f"def func_{i}():\n    return {i}\n"
            )

        indexer = CodebaseIndexer(str(tmp_project))
        indexer.index()

        results = indexer.search("def func", top_k=3)
        assert len(results) <= 3

    def test_chunk_contains_file_path(self, tmp_project: Path):
        indexer = CodebaseIndexer(str(tmp_project))
        indexer.index()

        results = indexer.search("add")
        assert all(hasattr(chunk, "file_path") for chunk in results)
        assert all(chunk.file_path for chunk in results)

    def test_index_ignores_venv_directory(self, tmp_project: Path):
        # .venv 디렉토리는 인덱싱에서 제외되어야 함
        (tmp_path := tmp_project / ".venv" / "lib").mkdir(parents=True)
        (tmp_path / "dummy.py").write_text("secret = 'should not be indexed'")

        indexer = CodebaseIndexer(str(tmp_project))
        indexer.index()

        all_paths = [c.file_path for c in indexer._chunks]
        assert not any(".venv" in p for p in all_paths)

    def test_chunk_str_representation(self, tmp_project: Path):
        indexer = CodebaseIndexer(str(tmp_project))
        indexer.index()
        chunk = indexer._chunks[0]
        chunk_str = str(chunk)
        assert chunk.file_path in chunk_str
        assert str(chunk.start_line) in chunk_str
