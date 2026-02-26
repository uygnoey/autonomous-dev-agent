# VectorStore API

**파일**: `src/rag/vector_store.py`

벡터 저장소 모듈. 코드 청크와 임베딩 벡터를 저장하고 코사인 유사도 기반 검색을 제공합니다. lancedb 설치 여부에 따라 `NumpyStore`(인메모리) 또는 `LanceDBStore`(디스크)를 자동 선택합니다.

## 인터페이스

### `VectorStoreProtocol`

`@runtime_checkable` Protocol. 모든 벡터 저장소 구현체가 준수하는 계약.

```python
@runtime_checkable
class VectorStoreProtocol(Protocol):
    def add(self, chunks: list[CodeChunk], embeddings: list[list[float]]) -> None: ...
    def search(self, query_embedding: list[float], top_k: int) -> list[tuple[CodeChunk, float]]: ...
    def remove(self, file_path: str) -> None: ...
    def clear(self) -> None: ...
```

#### `add(chunks, embeddings) -> None`

청크와 임베딩을 저장소에 추가합니다.

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `chunks` | `list[CodeChunk]` | 저장할 코드 청크 목록 |
| `embeddings` | `list[list[float]]` | 각 청크에 대응하는 임베딩 벡터 목록 |

`chunks`와 `embeddings`의 길이가 다르면 `ValueError`를 발생시킵니다.

#### `search(query_embedding, top_k) -> list[tuple[CodeChunk, float]]`

쿼리 임베딩과 코사인 유사도가 높은 청크를 반환합니다.

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `query_embedding` | `list[float]` | 검색 쿼리의 임베딩 벡터 |
| `top_k` | `int` | 반환할 최대 결과 수 |

**반환값**: `list[tuple[CodeChunk, float]]` — `(청크, 유사도)` 튜플 목록 (유사도 내림차순).

#### `remove(file_path) -> None`

특정 파일 경로의 모든 청크를 삭제합니다. 증분 인덱싱에서 파일 수정/삭제 시 사용.

#### `clear() -> None`

저장소의 모든 청크와 벡터를 삭제합니다.

---

## 구현체

### `NumpyStore`

numpy 기반 인메모리 벡터 저장소. lancedb 미설치 시 기본 구현체로 사용됩니다.

**코사인 유사도 계산:**

```
sim(a, b) = dot(a, b) / (||a|| * ||b||)
```

numpy의 `dot`, `linalg.norm`으로 구현. zero 벡터(norm=0)는 유사도 0으로 처리.

#### 추가 속성

##### `size -> int`

저장된 청크 수를 반환합니다.

```python
@property
def size(self) -> int
```

---

### `LanceDBStore`

lancedb 기반 디스크 벡터 저장소. ANN(Approximate Nearest Neighbor) 검색으로 대형 프로젝트를 지원합니다.

**저장 위치**: `.rag_cache/lancedb/`

**생성자**

```python
def __init__(self, cache_dir: str = ".rag_cache/lancedb") -> None
```

lancedb 미설치 시 `ImportError`가 발생하므로 직접 인스턴스화하지 않습니다. `create_vector_store()` 팩토리를 통해 사용합니다.

**유사도 변환**: lancedb는 cosine distance를 반환하므로 `similarity = 1.0 - distance`로 변환합니다.

---

## 팩토리 함수

### `create_vector_store() -> NumpyStore | LanceDBStore`

lancedb 설치 여부에 따라 벡터 저장소 구현체를 자동 선택합니다.

```python
def create_vector_store() -> NumpyStore | LanceDBStore
```

**선택 로직:**

1. `lancedb` 패키지가 설치되어 있으면 `LanceDBStore` 반환
2. `LanceDBStore` 초기화 실패 시 `NumpyStore`로 폴백
3. `lancedb` 없으면 `NumpyStore` 반환

**사용 예시**

```python
from src.rag.vector_store import create_vector_store
from src.core.domain import CodeChunk

store = create_vector_store()

# 청크 추가
chunks = [CodeChunk(file_path="main.py", content="def main(): ...",
                    start_line=1, end_line=3, chunk_type="function", name="main")]
embeddings = [[0.1, 0.2, 0.3, ...]]  # 1024차원 벡터

store.add(chunks, embeddings)

# 검색
query_vec = [0.15, 0.25, 0.35, ...]
results = store.search(query_vec, top_k=5)
for chunk, similarity in results:
    print(f"{chunk.file_path}:{chunk.start_line} (similarity={similarity:.4f})")

# 파일 삭제
store.remove("main.py")
```

## NumpyStore vs LanceDBStore 비교

| 항목 | NumpyStore | LanceDBStore |
|------|-----------|-------------|
| 설치 요구사항 | numpy (기본 의존성) | lancedb (`uv sync --extra rag`) |
| 저장 방식 | 인메모리 | 디스크 (`.rag_cache/lancedb/`) |
| 검색 방식 | 전체 스캔 (브루트 포스) | ANN (Approximate Nearest Neighbor) |
| 대규모 적합성 | 소형~중형 프로젝트 | 대형 프로젝트 |
| 프로세스 재시작 | 데이터 소실 | 데이터 유지 |
