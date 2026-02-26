"""벡터 저장소 모듈.

코드 청크와 임베딩 벡터를 저장하고 코사인 유사도 기반 검색을 제공한다.
lancedb 설치 여부에 따라 NumpyStore(인메모리) 또는 LanceDBStore(디스크)를 자동 선택한다.

VectorStoreProtocol은 이 모듈 내에 정의하며, 모든 구현체가 준수한다.
"""

from __future__ import annotations

import importlib.util
from typing import Protocol, runtime_checkable

import numpy as np

from src.core.domain import CodeChunk
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

# LanceDB 캐시 디렉토리
_LANCEDB_CACHE_DIR = ".rag_cache/lancedb"
_LANCEDB_TABLE = "chunks"


@runtime_checkable
class VectorStoreProtocol(Protocol):
    """벡터 저장소 계약.

    코드 청크와 임베딩 벡터를 저장하고 유사도 검색을 제공하는 구현체가 준수한다.
    """

    def add(self, chunks: list[CodeChunk], embeddings: list[list[float]]) -> None:
        """청크와 임베딩을 저장소에 추가한다.

        Args:
            chunks: 저장할 코드 청크 목록
            embeddings: 각 청크에 대응하는 임베딩 벡터 목록 (chunks와 동일 길이)
        """
        ...

    def search(
        self, query_embedding: list[float], top_k: int
    ) -> list[tuple[CodeChunk, float]]:
        """쿼리 임베딩과 코사인 유사도가 높은 청크를 반환한다.

        Args:
            query_embedding: 검색 쿼리의 임베딩 벡터
            top_k: 반환할 최대 결과 수

        Returns:
            (CodeChunk, 유사도) 튜플 목록 (유사도 내림차순 정렬)
        """
        ...

    def remove(self, file_path: str) -> None:
        """특정 파일 경로의 모든 청크를 삭제한다.

        Args:
            file_path: 삭제할 청크의 파일 경로
        """
        ...

    def clear(self) -> None:
        """저장소의 모든 청크와 벡터를 삭제한다."""
        ...


class NumpyStore:
    """numpy 기반 인메모리 벡터 저장소.

    코사인 유사도(dot / (||a|| * ||b||))로 검색한다.
    lancedb 미설치 시 기본 구현체로 사용된다.

    VectorStoreProtocol을 구조적으로 준수한다.
    """

    def __init__(self) -> None:
        self._chunks: list[CodeChunk] = []
        self._vectors: list[list[float]] = []

    def add(self, chunks: list[CodeChunk], embeddings: list[list[float]]) -> None:
        """청크와 임베딩을 인메모리에 추가한다.

        Args:
            chunks: 저장할 코드 청크 목록
            embeddings: 각 청크에 대응하는 임베딩 벡터 목록

        Raises:
            ValueError: chunks와 embeddings 길이가 다를 때
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"chunks({len(chunks)})와 embeddings({len(embeddings)}) 길이가 다릅니다."
            )
        self._chunks.extend(chunks)
        self._vectors.extend(embeddings)

    def search(
        self, query_embedding: list[float], top_k: int
    ) -> list[tuple[CodeChunk, float]]:
        """코사인 유사도로 상위 top_k 청크를 반환한다.

        빈 스토어이거나 top_k <= 0이면 빈 리스트를 반환한다.
        zero 벡터(norm=0)는 유사도 0으로 처리한다.

        Args:
            query_embedding: 검색 쿼리의 임베딩 벡터
            top_k: 반환할 최대 결과 수

        Returns:
            (CodeChunk, 유사도) 튜플 목록 (유사도 내림차순 정렬)
        """
        if not self._vectors or top_k <= 0:
            return []

        query = np.array(query_embedding, dtype=np.float64)
        query_norm = float(np.linalg.norm(query))
        if query_norm == 0.0:
            return []

        matrix = np.array(self._vectors, dtype=np.float64)  # (N, D)
        norms = np.linalg.norm(matrix, axis=1)              # (N,)

        # norm이 0인 벡터는 유사도 0으로 처리
        with np.errstate(invalid="ignore", divide="ignore"):
            sims = np.dot(matrix, query) / (norms * query_norm)

        sims = np.nan_to_num(sims, nan=0.0)

        # top_k 인덱스 추출 (내림차순)
        k = min(top_k, len(self._chunks))
        top_indices = np.argpartition(sims, -k)[-k:]
        top_indices = top_indices[np.argsort(sims[top_indices])[::-1]]

        return [(self._chunks[int(i)], float(sims[int(i)])) for i in top_indices]

    def remove(self, file_path: str) -> None:
        """파일 경로에 해당하는 모든 청크를 삭제한다.

        역순 삭제로 인덱스 이동 문제를 방지한다.

        Args:
            file_path: 삭제할 청크의 파일 경로
        """
        to_remove = [i for i, c in enumerate(self._chunks) if c.file_path == file_path]
        for idx in reversed(to_remove):
            del self._chunks[idx]
            del self._vectors[idx]

    def clear(self) -> None:
        """인메모리 저장소를 초기화한다."""
        self._chunks.clear()
        self._vectors.clear()

    @property
    def size(self) -> int:
        """저장된 청크 수를 반환한다."""
        return len(self._chunks)


class LanceDBStore:
    """lancedb 기반 디스크 벡터 저장소.

    ANN(Approximate Nearest Neighbor) 검색으로 대형 프로젝트를 지원한다.
    .rag_cache/lancedb/ 디렉토리에 저장한다.

    VectorStoreProtocol을 구조적으로 준수한다.
    lancedb 미설치 시 ImportError가 발생하므로 직접 인스턴스화하지 않는다.
    create_vector_store() 팩토리를 통해 사용한다.
    """

    def __init__(self, cache_dir: str = _LANCEDB_CACHE_DIR) -> None:
        """
        Args:
            cache_dir: lancedb 데이터베이스 디렉토리 경로

        Raises:
            ImportError: lancedb 미설치 시
        """
        import lancedb

        self._db = lancedb.connect(cache_dir)
        self._table_name = _LANCEDB_TABLE
        self._table = None  # 첫 add() 호출 시 생성

        # 기존 테이블 로드
        if self._table_name in self._db.table_names():
            self._table = self._db.open_table(self._table_name)

        # CodeChunk 복원을 위한 인메모리 매핑
        # lancedb는 Python 객체를 직접 저장하지 않으므로 별도 보관
        self._chunk_map: dict[str, CodeChunk] = {}

    def add(self, chunks: list[CodeChunk], embeddings: list[list[float]]) -> None:
        """청크와 임베딩을 lancedb에 추가한다.

        Args:
            chunks: 저장할 코드 청크 목록
            embeddings: 각 청크에 대응하는 임베딩 벡터 목록

        Raises:
            ValueError: chunks와 embeddings 길이가 다를 때
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"chunks({len(chunks)})와 embeddings({len(embeddings)}) 길이가 다릅니다."
            )
        if not chunks:
            return

        rows = []
        for chunk, vec in zip(chunks, embeddings, strict=True):
            chunk_id = _chunk_id(chunk)
            self._chunk_map[chunk_id] = chunk
            rows.append({"id": chunk_id, "vector": vec})

        if self._table is None:
            self._table = self._db.create_table(self._table_name, data=rows)
        else:
            self._table.add(rows)

    def search(
        self, query_embedding: list[float], top_k: int
    ) -> list[tuple[CodeChunk, float]]:
        """lancedb ANN 검색으로 상위 top_k 청크를 반환한다.

        Args:
            query_embedding: 검색 쿼리의 임베딩 벡터
            top_k: 반환할 최대 결과 수

        Returns:
            (CodeChunk, 유사도) 튜플 목록 (유사도 내림차순 정렬)
        """
        if self._table is None or top_k <= 0:
            return []

        results = (
            self._table.search(query_embedding)
            .limit(top_k)
            .to_pandas()
        )

        output: list[tuple[CodeChunk, float]] = []
        for _, row in results.iterrows():
            chunk_id = row["id"]
            if chunk_id in self._chunk_map:
                # lancedb는 거리(distance)를 반환하므로 유사도로 변환
                # cosine distance = 1 - cosine similarity
                distance = float(row.get("_distance", 0.0))
                similarity = 1.0 - distance
                output.append((self._chunk_map[chunk_id], similarity))

        return output

    def remove(self, file_path: str) -> None:
        """파일 경로에 해당하는 모든 청크를 lancedb에서 삭제한다.

        Args:
            file_path: 삭제할 청크의 파일 경로
        """
        if self._table is None:
            return

        # chunk_map에서 해당 file_path 청크 ID 수집
        ids_to_remove = [
            chunk_id
            for chunk_id, chunk in self._chunk_map.items()
            if chunk.file_path == file_path
        ]
        if not ids_to_remove:
            return

        # lancedb DELETE 쿼리 (id IN (...) 형식)
        id_list = ", ".join(f"'{cid}'" for cid in ids_to_remove)
        self._table.delete(f"id IN ({id_list})")

        for cid in ids_to_remove:
            del self._chunk_map[cid]

    def clear(self) -> None:
        """lancedb 테이블을 삭제하고 chunk_map을 초기화한다."""
        if self._table is not None and self._table_name in self._db.table_names():
            self._db.drop_table(self._table_name)
        self._table = None
        self._chunk_map.clear()


def create_vector_store() -> NumpyStore | LanceDBStore:
    """lancedb 설치 여부에 따라 벡터 저장소 구현체를 자동 선택한다.

    lancedb가 설치되어 있으면 LanceDBStore(디스크 기반 ANN 검색)를 반환하고,
    없으면 NumpyStore(인메모리 코사인 유사도 검색)를 반환한다.

    Returns:
        NumpyStore 또는 LanceDBStore 인스턴스
    """
    if importlib.util.find_spec("lancedb") is not None:
        try:
            store = LanceDBStore()
            logger.info("VectorStore: lancedb 감지, LanceDBStore 사용")
            return store
        except Exception as exc:
            logger.warning(f"VectorStore: LanceDBStore 초기화 실패 ({exc}), NumpyStore로 폴백")

    logger.info("VectorStore: lancedb 없음, NumpyStore 사용")
    return NumpyStore()


# ------------------------------------------------------------------
# 모듈 레벨 헬퍼
# ------------------------------------------------------------------


def _chunk_id(chunk: CodeChunk) -> str:
    """CodeChunk의 고유 ID를 생성한다.

    file_path + start_line 조합으로 청크를 고유하게 식별한다.

    Args:
        chunk: 대상 코드 청크

    Returns:
        고유 ID 문자열
    """
    return f"{chunk.file_path}:{chunk.start_line}"
