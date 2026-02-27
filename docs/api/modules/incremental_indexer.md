# IncrementalIndexer API

**파일**: `src/rag/incremental_indexer.py`

증분 인덱싱 모듈. 최초 전체 인덱싱 이후 mtime 기반 변경 파일만 재인덱싱하여 전체 재인덱싱 대비 속도를 향상시킵니다. 모든 RAG 컴포넌트를 의존성 주입으로 조합하며, 모듈 레벨 싱글톤으로 매번 재생성을 방지합니다.

## 클래스

### `IncrementalIndexer`

mtime 기반 증분 인덱서.

#### 생성자

```python
def __init__(
    self,
    chunker: ChunkerProtocol,
    scorer: BM25Scorer,
    store: VectorStoreProtocol,
    embedder: AnthropicEmbedder,
    project_path: str,
    cache_dir: str = ".rag_cache",
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> None
```

**파라미터**

| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| `chunker` | `ChunkerProtocol` | — | 파일을 CodeChunk로 분할하는 청커 |
| `scorer` | `BM25Scorer` | — | BM25 스코어러 |
| `store` | `VectorStoreProtocol` | — | 벡터 저장소 |
| `embedder` | `AnthropicEmbedder` | — | 텍스트 임베딩기 |
| `project_path` | `str` | — | 인덱싱할 프로젝트 루트 경로 |
| `cache_dir` | `str` | `".rag_cache"` | 캐시 파일 저장 디렉토리 |
| `include_patterns` | `list[str] \| None` | `None` | 추가 포함 glob 패턴 목록 (None이면 기본값 사용) |
| `exclude_patterns` | `list[str] \| None` | `None` | 추가 제외 glob 패턴 목록 |

#### 속성

##### `all_chunks -> list[CodeChunk]`

현재 인덱싱된 전체 청크 목록을 반환합니다.

```python
@property
def all_chunks(self) -> list[CodeChunk]
```

#### 메서드

##### `index() -> int`

프로젝트 전체를 인덱싱합니다.

```python
def index(self) -> int
```

최초 1회 또는 캐시 손상 시 호출합니다. 기존 store와 청크 목록을 초기화하고 전체 파일을 재인덱싱합니다.

**반환값**: `int` — 인덱싱된 청크 수.

---

##### `update() -> dict[str, int]`

변경된 파일만 증분 인덱싱합니다.

```python
def update(self) -> dict[str, int]
```

mtime을 비교하여 신규·수정·삭제 파일을 감지하고 최소한의 재인덱싱만 수행합니다.

**반환값**: `dict[str, int]` — `{"added": n, "updated": n, "removed": n}` 처리 파일 수.

---

##### `search(query, top_k) -> list[CodeChunk]`

HybridSearcher에 위임하여 쿼리에 관련된 청크를 반환합니다.

```python
async def search(self, query: str, top_k: int) -> list[CodeChunk]
```

**파라미터**

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `query` | `str` | 검색 쿼리 문자열 |
| `top_k` | `int` | 반환할 최대 결과 수 |

**반환값**: `list[CodeChunk]` — 관련성 높은 순으로 정렬된 청크 목록.

## 파일 필터링 규칙

### 필터링 우선순위

`_collect_files()` 메서드는 다음 5단계 순서로 파일을 필터링합니다:

1. `IGNORED_DIRS` 하드코딩 제외
2. `BINARY_EXTENSIONS` 제외
3. `.gitignore` 패턴 매칭 제외 (`pathspec` 라이브러리 사용 가능 시)
4. 사용자 정의 `exclude_patterns` 제외
5. `SUPPORTED_EXTENSIONS` 또는 `include_patterns`에 매칭되는 파일만 포함

### .gitignore 필터링

`pathspec` 라이브러리가 설치되어 있으면 프로젝트 루트의 `.gitignore`를 자동으로 파싱하여, 해당 패턴과 일치하는 파일을 인덱싱에서 제외합니다.

- `pathspec`이 없거나 `.gitignore` 파일이 없으면 이 단계를 건너뜁니다.
- 경로는 프로젝트 루트 기준 상대 경로로 비교합니다.

### 사용자 정의 패턴 (`include_patterns` / `exclude_patterns`)

`RAGSettings.include_patterns`와 `RAGSettings.exclude_patterns` (또는 생성자 파라미터)로 glob 패턴을 추가할 수 있습니다.

```yaml
# config/default.yaml 또는 환경변수 ADEV_RAG__INCLUDE_PATTERNS / ADEV_RAG__EXCLUDE_PATTERNS
rag:
  include_patterns: []        # 추가 포함 패턴 (기본 동작: SUPPORTED_EXTENSIONS만 허용)
  exclude_patterns:           # 추가 제외 패턴 (.gitignore와 무관하게 적용)
    - "tests/fixtures/**"
    - "docs/**"
```

| 설정 | 동작 |
|------|------|
| `include_patterns` | 빈 리스트이면 `SUPPORTED_EXTENSIONS`만 허용 |
| `exclude_patterns` | .gitignore와 무관하게 항상 적용 |

### 제외 디렉토리 (`IGNORED_DIRS`)

```python
IGNORED_DIRS = frozenset({
    "__pycache__", ".git", "node_modules", ".venv", "venv",
    "dist", "build", ".rag_cache",
})
```

### 지원 확장자 (`SUPPORTED_EXTENSIONS`)

```python
SUPPORTED_EXTENSIONS = frozenset({
    ".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".java",
    ".rs", ".yaml", ".yml", ".md",
})
```

### 바이너리 확장자 (`BINARY_EXTENSIONS`)

읽기 시도하지 않는 파일:

```python
BINARY_EXTENSIONS = frozenset({
    ".pyc", ".so", ".dll", ".exe", ".bin",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg",
    ".pdf", ".zip", ".tar", ".gz", ".whl",
    ".db", ".sqlite", ".pkl",
})
```

## 캐시 구조

**디렉토리**: `{project_path}/.rag_cache/`

```
.rag_cache/
├── file_index.json    # 파일별 mtime, 청크 수, 인덱싱 시각
├── bm25_index.pkl     # BM25Okapi 직렬화 (pickle)
└── embeddings.json    # SHA256 → 임베딩 벡터 캐시
```

**`file_index.json` 구조**:

```json
{
  "src/rag/chunker.py": {
    "mtime": 1735000000.0,
    "chunk_count": 8,
    "last_indexed": "2026-02-26T12:00:00+00:00"
  }
}
```

## 싱글톤 패턴

### `get_indexer(project_path) -> IncrementalIndexer`

모듈 레벨 싱글톤 인덱서를 반환합니다.

```python
def get_indexer(project_path: str) -> IncrementalIndexer
```

최초 호출 시 기본 컴포넌트(`ASTChunker`, `BM25Scorer`, `create_vector_store()`, `AnthropicEmbedder()`)로 인스턴스를 생성합니다. `RAGSettings.include_patterns`와 `RAGSettings.exclude_patterns`를 읽어 인덱서에 전달합니다. 이후 호출 시 동일 인스턴스를 반환합니다.

### `reset_indexer() -> None`

싱글톤 인스턴스를 초기화합니다. 테스트 환경에서 격리를 위해 사용합니다.

```python
def reset_indexer() -> None
```

## 사용 예시

```python
import asyncio
from src.rag.incremental_indexer import get_indexer, reset_indexer

async def main():
    indexer = get_indexer("/path/to/project")

    # 최초 전체 인덱싱
    chunk_count = indexer.index()
    print(f"인덱싱된 청크: {chunk_count}개")

    # 검색
    results = await indexer.search("BM25 scoring", top_k=5)
    for chunk in results:
        print(f"{chunk.file_path}:{chunk.start_line} [{chunk.chunk_type}]")

    # 코드 수정 후 증분 업데이트
    counts = indexer.update()
    print(f"변경: 추가={counts['added']}, 수정={counts['updated']}, 삭제={counts['removed']}")

asyncio.run(main())

# 테스트 격리
reset_indexer()
```

## 증분 인덱싱 동작

### 변경 감지 로직

```python
current_files = {path: path.stat().st_mtime for path in collect_files()}
cached_index = load_file_index()

new_files      = [p for p in current if p not in cached]
modified_files = [p for p in current if p in cached and current[p] != cached[p]["mtime"]]
deleted_files  = [p for p in cached if p not in current]
```

### 처리 순서

1. 삭제된 파일: `store.remove(file_path)` + 청크 목록에서 제거
2. 수정된 파일: 기존 청크 제거 → 재청킹 → 재임베딩 → store 추가
3. 신규 파일: 청킹 → 임베딩 → store 추가
4. 변경 있으면: BM25 전체 재학습 + 캐시 저장
