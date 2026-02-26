"""증분 인덱싱 모듈.

최초 전체 인덱싱 이후 mtime 기반 변경 파일만 재인덱싱하여
전체 재인덱싱 대비 속도를 향상시킨다.

모든 RAG 컴포넌트(chunker, scorer, embedder, vector_store, hybrid_search)를
의존성 주입으로 조합하며, 모듈 레벨 싱글톤으로 executor에서의 재생성을 방지한다.
"""

from __future__ import annotations

import asyncio
import json
import pickle
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from src.core.domain import CodeChunk
from src.core.interfaces import ChunkerProtocol
from src.rag.embedder import AnthropicEmbedder
from src.rag.hybrid_search import HybridSearcher
from src.rag.scorer import BM25Scorer
from src.rag.vector_store import VectorStoreProtocol, create_vector_store
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

# 인덱싱 대상에서 제외할 디렉토리
IGNORED_DIRS: frozenset[str] = frozenset({
    "__pycache__", ".git", "node_modules", ".venv", "venv",
    "dist", "build", ".rag_cache",
})

# 인덱싱 지원 확장자
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".java",
    ".rs", ".yaml", ".yml", ".md",
})

# 바이너리 파일 확장자 (읽기 시도하지 않음)
BINARY_EXTENSIONS: frozenset[str] = frozenset({
    ".pyc", ".so", ".dll", ".exe", ".bin",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg",
    ".pdf", ".zip", ".tar", ".gz", ".whl",
    ".db", ".sqlite", ".pkl",
})

# 캐시 파일명
_FILE_INDEX = "file_index.json"
_BM25_INDEX = "bm25_index.pkl"


class _FileIndexEntry(TypedDict):
    """file_index.json의 개별 파일 항목."""

    mtime: float
    chunk_count: int
    last_indexed: str


class IncrementalIndexer:
    """mtime 기반 증분 인덱서.

    최초 index() 호출 시 전체 인덱싱을 수행하고,
    이후 update() 호출 시 변경된 파일만 재인덱싱한다.

    의존성 주입으로 모든 컴포넌트를 외부에서 받아 테스트 용이성을 보장한다.
    """

    def __init__(
        self,
        chunker: ChunkerProtocol,
        scorer: BM25Scorer,
        store: VectorStoreProtocol,
        embedder: AnthropicEmbedder,
        project_path: str,
        cache_dir: str = ".rag_cache",
    ) -> None:
        """
        Args:
            chunker: 파일을 CodeChunk로 분할하는 청커
            scorer: BM25 스코어러
            store: 벡터 저장소
            embedder: 텍스트 임베딩기
            project_path: 인덱싱할 프로젝트 루트 경로
            cache_dir: 캐시 파일 저장 디렉토리 (기본 ".rag_cache")
        """
        self._chunker = chunker
        self._scorer = scorer
        self._store = store
        self._embedder = embedder
        self._project_path = Path(project_path)
        self._cache_dir = self._project_path / cache_dir

        # 인덱싱된 전체 청크 목록 (search에서 활용)
        self._all_chunks: list[CodeChunk] = []

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def index(self) -> int:
        """프로젝트 전체를 인덱싱한다.

        최초 1회 또는 캐시 손상 시 호출한다.
        기존 store와 청크 목록을 초기화하고 전체 파일을 재인덱싱한다.

        Returns:
            인덱싱된 청크 수
        """
        self._store.clear()
        self._all_chunks.clear()

        files = self._collect_files()
        logger.info(f"IncrementalIndexer.index: {len(files)}개 파일 전체 인덱싱 시작")

        file_index: dict[str, _FileIndexEntry] = {}
        all_chunks: list[CodeChunk] = []

        for file_path in files:
            chunks = self._chunk_file(file_path)
            if chunks:
                all_chunks.extend(chunks)
                file_index[str(file_path)] = _FileIndexEntry(
                    mtime=file_path.stat().st_mtime,
                    chunk_count=len(chunks),
                    last_indexed=datetime.now(UTC).isoformat(),
                )

        if all_chunks:
            self._fit_and_embed(all_chunks)

        self._all_chunks = all_chunks
        self._save_file_index(file_index)
        self._save_bm25_index()

        logger.info(
            f"IncrementalIndexer.index 완료: "
            f"{len(files)}개 파일, {len(all_chunks)}개 청크"
        )
        return len(all_chunks)

    def update(self) -> dict[str, int]:
        """변경된 파일만 증분 인덱싱한다.

        mtime을 비교하여 신규·수정·삭제 파일을 감지하고
        최소한의 재인덱싱만 수행한다.

        Returns:
            {"added": n, "updated": n, "removed": n} 처리 파일 수
        """
        new_files, modified_files, deleted_files = self._detect_changes()
        counts: dict[str, int] = {"added": 0, "updated": 0, "removed": 0}

        if not (new_files or modified_files or deleted_files):
            logger.debug("IncrementalIndexer.update: 변경 없음")
            return counts

        file_index = self._load_file_index()

        # 삭제된 파일 처리
        for file_path in deleted_files:
            self._store.remove(str(file_path))
            self._all_chunks = [
                c for c in self._all_chunks if c.file_path != str(file_path)
            ]
            file_index.pop(str(file_path), None)
            counts["removed"] += 1
            logger.debug(f"IncrementalIndexer.update: 삭제 처리 {file_path}")

        # 수정된 파일 처리
        for file_path in modified_files:
            self._store.remove(str(file_path))
            self._all_chunks = [
                c for c in self._all_chunks if c.file_path != str(file_path)
            ]
            new_chunks = self._chunk_file(file_path)
            if new_chunks:
                self._reembed_and_add(new_chunks)
                self._all_chunks.extend(new_chunks)
                file_index[str(file_path)] = _FileIndexEntry(
                    mtime=file_path.stat().st_mtime,
                    chunk_count=len(new_chunks),
                    last_indexed=datetime.now(UTC).isoformat(),
                )
            counts["updated"] += 1
            logger.debug(f"IncrementalIndexer.update: 수정 처리 {file_path}")

        # 신규 파일 처리
        for file_path in new_files:
            new_chunks = self._chunk_file(file_path)
            if new_chunks:
                self._reembed_and_add(new_chunks)
                self._all_chunks.extend(new_chunks)
                file_index[str(file_path)] = _FileIndexEntry(
                    mtime=file_path.stat().st_mtime,
                    chunk_count=len(new_chunks),
                    last_indexed=datetime.now(UTC).isoformat(),
                )
            counts["added"] += 1
            logger.debug(f"IncrementalIndexer.update: 신규 처리 {file_path}")

        # 변경이 있으면 BM25 재학습
        if new_files or modified_files or deleted_files:
            texts = [c.content for c in self._all_chunks]
            self._scorer.fit(texts)
            self._save_file_index(file_index)
            self._save_bm25_index()

        logger.info(
            f"IncrementalIndexer.update 완료: "
            f"added={counts['added']}, updated={counts['updated']}, "
            f"removed={counts['removed']}"
        )
        return counts

    async def search(self, query: str, top_k: int) -> list[CodeChunk]:
        """HybridSearcher에 위임하여 쿼리에 관련된 청크를 반환한다.

        Args:
            query: 검색 쿼리 문자열
            top_k: 반환할 최대 결과 수

        Returns:
            관련성 높은 순으로 정렬된 CodeChunk 목록
        """
        if not self._all_chunks:
            return []

        searcher = HybridSearcher(
            scorer=self._scorer,
            store=self._store,
            embedder=self._embedder,
        )
        results = await searcher.search(query, top_k, self._all_chunks)
        return [chunk for chunk, _ in results]

    @property
    def all_chunks(self) -> list[CodeChunk]:
        """현재 인덱싱된 전체 청크 목록을 반환한다."""
        return self._all_chunks

    # ------------------------------------------------------------------
    # 변경 감지
    # ------------------------------------------------------------------

    def _detect_changes(self) -> tuple[list[Path], list[Path], list[Path]]:
        """mtime 비교로 신규·수정·삭제 파일을 감지한다.

        Returns:
            (new_files, modified_files, deleted_files) 튜플
        """
        current: dict[Path, float] = {
            p: p.stat().st_mtime for p in self._collect_files()
        }
        cached = self._load_file_index()

        current_str = {str(p) for p in current}

        new = [p for p in current if str(p) not in cached]
        modified = [
            p for p in current
            if str(p) in cached and current[p] != cached[str(p)]["mtime"]
        ]
        deleted = [
            Path(p) for p in cached
            if p not in current_str
        ]
        return new, modified, deleted

    # ------------------------------------------------------------------
    # 파일 수집 및 청킹
    # ------------------------------------------------------------------

    def _collect_files(self) -> list[Path]:
        """지원 확장자의 파일을 수집한다.

        IGNORED_DIRS에 속하거나 BINARY_EXTENSIONS인 파일은 제외한다.

        Returns:
            인덱싱 대상 파일 경로 목록
        """
        files: list[Path] = []
        for path in self._project_path.rglob("*"):
            if any(part in IGNORED_DIRS for part in path.parts):
                continue
            if not path.is_file():
                continue
            if path.suffix in BINARY_EXTENSIONS:
                continue
            if path.suffix in SUPPORTED_EXTENSIONS:
                files.append(path)
        return files

    def _chunk_file(self, file_path: Path) -> list[CodeChunk]:
        """단일 파일을 청킹한다.

        읽기 실패(OSError, UnicodeDecodeError)나 바이너리 파일은
        경고 로그 후 빈 리스트를 반환한다.

        Args:
            file_path: 청킹할 파일 경로

        Returns:
            CodeChunk 목록. 실패 시 빈 리스트.
        """
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning(f"파일 읽기 실패 ({file_path}): {exc}")
            return []

        relative = str(file_path.relative_to(self._project_path))
        chunks = self._chunker.chunk(relative, content)
        return chunks

    # ------------------------------------------------------------------
    # 인덱싱 헬퍼
    # ------------------------------------------------------------------

    def _run_embed(self, texts: list[str]) -> list[list[float]]:
        """asyncio.run()으로 embed() 코루틴을 동기적으로 실행한다.

        이미 실행 중인 이벤트 루프가 있는 환경(테스트 등)에서는
        새 루프를 생성하여 실행한다.

        Args:
            texts: 임베딩할 텍스트 목록

        Returns:
            임베딩 벡터 목록. 실패 시 빈 리스트.
        """
        try:
            return asyncio.run(self._embedder.embed(texts))
        except RuntimeError:
            # 이미 실행 중인 이벤트 루프가 있을 때 (테스트 환경 등)
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self._embedder.embed(texts))
            finally:
                loop.close()

    def _embed_and_store(
        self, chunks: list[CodeChunk], log_prefix: str = ""
    ) -> None:
        """청크를 임베딩하여 벡터 저장소에 추가한다.

        임베딩 수가 청크 수와 다르면 가능한 만큼만 추가하고 경고를 남긴다.

        Args:
            chunks: 임베딩 및 저장할 청크 목록
            log_prefix: 경고 메시지에 붙일 접두어 (파일명 등)
        """
        texts = [c.content for c in chunks]
        embeddings = self._run_embed(texts)

        if embeddings and len(embeddings) == len(chunks):
            self._store.add(chunks, embeddings)
        elif embeddings:
            count = min(len(embeddings), len(chunks))
            self._store.add(chunks[:count], embeddings[:count])
            logger.warning(
                f"{log_prefix}임베딩 수({len(embeddings)})가 "
                f"청크 수({len(chunks)})와 다름. {count}개만 벡터 저장소에 추가."
            )
        else:
            logger.warning(
                f"{log_prefix}임베딩 실패. 벡터 저장소에 추가하지 않음 (BM25-only 모드)."
            )

    def _fit_and_embed(self, chunks: list[CodeChunk]) -> None:
        """전체 청크로 BM25 학습 및 임베딩 후 스토어에 추가한다.

        index() 전용. 전체 청크를 한 번에 처리한다.

        Args:
            chunks: 인덱싱할 전체 청크 목록
        """
        texts = [c.content for c in chunks]
        self._scorer.fit(texts)
        self._embed_and_store(chunks)

    def _reembed_and_add(self, chunks: list[CodeChunk]) -> None:
        """개별 파일 청크를 임베딩하여 스토어에 추가한다.

        update() 전용. 변경 파일 청크만 처리한다.

        Args:
            chunks: 재인덱싱할 청크 목록
        """
        prefix = f"({chunks[0].file_path}) " if chunks else ""
        self._embed_and_store(chunks, log_prefix=prefix)

    # ------------------------------------------------------------------
    # 캐시 관리
    # ------------------------------------------------------------------

    def _load_file_index(self) -> dict[str, _FileIndexEntry]:
        """file_index.json을 로드한다.

        파일이 없거나 손상되면 빈 딕셔너리를 반환한다.

        Returns:
            {file_path: _FileIndexEntry} 딕셔너리
        """
        index_path = self._cache_dir / _FILE_INDEX
        if not index_path.exists():
            return {}
        try:
            data: dict[str, _FileIndexEntry] = json.loads(
                index_path.read_text(encoding="utf-8")
            )
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"file_index.json 로드 실패 ({exc}), 빈 인덱스로 시작")
            return {}

    def _save_file_index(self, index: dict[str, _FileIndexEntry]) -> None:
        """file_index.json을 저장한다.

        Args:
            index: 저장할 파일 인덱스 딕셔너리
        """
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        index_path = self._cache_dir / _FILE_INDEX
        try:
            index_path.write_text(
                json.dumps(index, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning(f"file_index.json 저장 실패: {exc}")

    def _save_bm25_index(self) -> None:
        """BM25Okapi 인덱스를 pickle로 직렬화하여 저장한다."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        pkl_path = self._cache_dir / _BM25_INDEX
        try:
            with pkl_path.open("wb") as f:
                pickle.dump(self._scorer, f)
        except (OSError, pickle.PicklingError) as exc:
            logger.warning(f"bm25_index.pkl 저장 실패: {exc}")

    def _load_bm25_index(self) -> bool:
        """pickle에서 BM25 인덱스를 복원한다.

        Returns:
            복원 성공 여부
        """
        pkl_path = self._cache_dir / _BM25_INDEX
        if not pkl_path.exists():
            return False
        try:
            with pkl_path.open("rb") as f:
                scorer = pickle.load(f)
            # 복원된 scorer의 내부 상태를 현재 scorer에 적용
            self._scorer._bm25 = scorer._bm25
            self._scorer._corpus_size = scorer._corpus_size
            return True
        except (OSError, pickle.UnpicklingError, AttributeError) as exc:
            logger.warning(f"bm25_index.pkl 로드 실패 ({exc}), 재학습 필요")
            return False


# ------------------------------------------------------------------
# 싱글톤 패턴
# ------------------------------------------------------------------

_indexer_instance: IncrementalIndexer | None = None


def get_indexer(project_path: str) -> IncrementalIndexer:
    """모듈 레벨 싱글톤 인덱서를 반환한다.

    executor._build_options()에서 매번 재생성 없이 동일 인스턴스를 재사용한다.
    최초 호출 시 _build_indexer()로 인스턴스를 생성한다.

    Args:
        project_path: 인덱싱할 프로젝트 루트 경로

    Returns:
        IncrementalIndexer 싱글톤 인스턴스
    """
    global _indexer_instance
    if _indexer_instance is None:
        _indexer_instance = _build_indexer(project_path)
    return _indexer_instance


def reset_indexer() -> None:
    """싱글톤 인스턴스를 초기화한다.

    테스트 환경에서 격리를 위해 사용한다.
    """
    global _indexer_instance
    _indexer_instance = None


def _build_indexer(project_path: str) -> IncrementalIndexer:
    """기본 컴포넌트 조합으로 IncrementalIndexer를 생성한다.

    Args:
        project_path: 인덱싱할 프로젝트 루트 경로

    Returns:
        의존성이 주입된 IncrementalIndexer 인스턴스
    """
    from src.rag.chunker import ASTChunker

    chunker = ASTChunker()
    scorer = BM25Scorer()
    store = create_vector_store()
    embedder = AnthropicEmbedder()

    return IncrementalIndexer(
        chunker=chunker,
        scorer=scorer,
        store=store,
        embedder=embedder,
        project_path=project_path,
    )
