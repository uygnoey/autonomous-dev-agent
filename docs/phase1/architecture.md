# Phase 1: RAG 시스템 아키텍처

## 1. 개요

### 현재 문제

| 문제 | 현재 구현 | 영향 |
|------|-----------|------|
| Boolean BoW 스코어링 | `indexer.py:_score()` — 단어 존재 여부만 체크 (0 or 1) | 희귀 토큰 가중치 없음, IDF 없음, 관련성 낮은 파일이 상위에 오는 현상 |
| 전체 재인덱싱 | `indexer.py:index()` — 매번 `_chunks.clear()` 후 전체 파일 읽기 | O(n), 대형 프로젝트에서 에이전트 실행 전 수 초~수십 초 지연 |
| 고정 크기 청크 | `_chunk_file()` — 50줄 슬라이싱 | 함수/클래스 경계 무시, 의미 단위 분리 불가, 컨텍스트 손실 |
| 단일 렉시컬 검색 | 벡터 검색 없음 | 의미적으로 유사하지만 키워드가 다른 코드 검색 불가 |
| MCP 도구 2개 | `search_code`, `reindex_codebase` 만 존재 | 심볼 검색, 구조 조회, 유사 패턴 검색 불가 |

### 목표

- **정확도 향상**: BM25 IDF 가중치 + 벡터 시맨틱 검색 결합
- **속도 향상**: 변경된 파일만 재인덱싱 (증분 인덱싱)
- **맥락 보존**: AST 경계 기반 청크 (함수, 클래스 단위)
- **도구 확장**: 심볼 검색 · 구조 조회 · 유사 패턴 검색 3종 추가

### 핵심 개선사항

```
Boolean BoW (0/1) → BM25 TF-IDF + 벡터 코사인 유사도 하이브리드
전체 재인덱싱 O(n) → mtime 기반 증분 인덱싱 O(변경분)
50줄 고정 청크 → AST 경계 청크 (함수·클래스·메서드·모듈)
2개 MCP 도구 → 5개 MCP 도구
```

---

## 2. 시스템 아키텍처

### 전체 구조도

```
┌─────────────────────────────────────────────────────────────────┐
│  MCP Layer  (src/rag/mcp_server.py)                             │
│  search_code · reindex_codebase · search_by_symbol              │
│  get_file_structure · get_similar_patterns                      │
└───────────────────────┬─────────────────────────────────────────┘
                        │ 호출
┌───────────────────────▼─────────────────────────────────────────┐
│  IncrementalIndexer  (src/rag/incremental_indexer.py)           │
│  index(project_path) · update() · search(query, top_k)          │
└──────┬────────────────┬──────────────────────────────┬──────────┘
       │                │                              │
┌──────▼──────┐  ┌──────▼──────┐             ┌────────▼──────────┐
│ ASTChunker  │  │ HybridSearcher              │ .rag_cache/       │
│ (chunker.py)│  │ (hybrid_search.py)          │  file_index.json  │
└──────┬──────┘  └──────┬───────┘             │  bm25_index.pkl   │
       │                │                     │  embeddings.json  │
       │         ┌──────┴──────────┐          └───────────────────┘
       │         │                 │
┌──────▼──────┐  ▼                 ▼
│ CodeChunk   │ BM25Scorer    VectorStore
│ (domain.py) │ (scorer.py)   (vector_store.py)
└─────────────┘      ▲              ▲
                     │              │
               AnthropicEmbedder ──┘
               (embedder.py)
```

### 모듈 구성

| 모듈 | 파일 | 역할 |
|------|------|------|
| ASTChunker | `src/rag/chunker.py` | Python AST 파싱 → CodeChunk 생성 |
| BM25Scorer | `src/rag/scorer.py` | rank-bm25 기반 IDF 스코어링 |
| AnthropicEmbedder | `src/rag/embedder.py` | Anthropic API 임베딩 + 캐시 |
| VectorStore | `src/rag/vector_store.py` | 벡터 저장 + 코사인 유사도 검색 |
| HybridSearcher | `src/rag/hybrid_search.py` | BM25 + 벡터 가중 결합 |
| IncrementalIndexer | `src/rag/incremental_indexer.py` | mtime 기반 증분 인덱싱 + 싱글톤 |
| MCP Server | `src/rag/mcp_server.py` | 에이전트에게 노출하는 MCP 도구 5종 |

### 데이터 흐름

#### 최초 인덱싱

```
project_path
    → IncrementalIndexer.index()
    → 파일 목록 수집 (gitignore 필터)
    → ASTChunker.chunk(file, content) → list[CodeChunk]
    → BM25Scorer.fit(all_texts)
    → AnthropicEmbedder.embed(all_texts) → list[list[float]]
    → VectorStore.add(chunks, embeddings)
    → .rag_cache/ 저장 (file_index.json, bm25_index.pkl, embeddings.json)
```

#### 증분 업데이트

```
IncrementalIndexer.update()
    → .rag_cache/file_index.json 로드
    → 현재 파일 목록 mtime 비교
    → 변경 파일만: VectorStore.remove(file) → ASTChunker.chunk → re-embed
    → 삭제 파일: VectorStore.remove(file) + 인덱스 정리
    → BM25Scorer 재학습 (변경 후 전체 문서로)
    → 캐시 저장
```

#### 검색

```
query
    → HybridSearcher.search(query, top_k)
    → BM25Scorer.score(query) → top_k*2 후보 + 정규화
    → AnthropicEmbedder.embed([query])
    → VectorStore.search(query_embedding) → top_k*2 후보 + 정규화
    → 가중 결합: 0.6 * bm25 + 0.4 * vector
    → 중복 제거 → top_k 반환
```

---

## 3. 모듈별 설계

### 3.1 ASTChunker

**책임**
- Python 파일을 AST로 파싱하여 함수·클래스·메서드·모듈 단위 청크 생성
- 비Python 파일은 고정 크기(50줄, 10줄 오버랩) 폴백
- SyntaxError 발생 시에도 폴백으로 graceful 처리

**인터페이스**
```python
class ASTChunker:
    """ChunkerProtocol 구현체 (src/core/interfaces.py:ChunkerProtocol)"""

    MIN_LINES: int = 5   # 5줄 미만은 상위 청크에 포함
    MAX_LINES: int = 100  # 100줄 초과 시 메서드별 서브청킹

    def chunk(self, file_path: str, content: str) -> list[CodeChunk]: ...
```

**구현 전략**

```
Python 파일 처리:
  ast.parse(content) → ast.walk()
  → FunctionDef / AsyncFunctionDef / ClassDef 노드 탐지
  → node.lineno ~ node.end_lineno 추출
  → 데코레이터: node.decorator_list[0].lineno 부터 시작
  → ClassDef 내부 메서드: 클래스 청크 + 메서드 청크 모두 생성
  → chunk_type 매핑:
      FunctionDef/AsyncFunctionDef → "function"
      ClassDef → "class"
      ClassDef 내부 FunctionDef → "method"
  → 나머지 코드 (import, 모듈 레벨 코드) → "module" 청크

크기 제어:
  end - start < MIN_LINES → 상위 "module" 청크에 병합
  end - start > MAX_LINES (ClassDef) → 메서드별 서브청킹

비Python 폴백:
  50줄 슬라이싱 + 10줄 오버랩
  chunk_type="block", name=None
```

**CodeChunk 생성 규칙**
```python
CodeChunk(
    file_path=relative_path,
    content=lines[start:end],
    start_line=start + 1,   # 1-indexed
    end_line=end,
    chunk_type="function",  # function|class|method|module|block
    name="function_name",   # 함수명/클래스명, 없으면 None
)
```

---

### 3.2 BM25Scorer

**책임**
- `rank-bm25` 라이브러리의 `BM25Okapi` 래핑
- 코드 특화 토큰화 (camelCase, snake_case 분리)
- 쿼리에 대한 top_k 청크 반환

**인터페이스**
```python
class BM25Scorer:
    """ScorerProtocol 구현체"""

    def fit(self, documents: list[str]) -> None:
        """BM25 인덱스 학습. 문서 코퍼스 변경 시 재호출 필요."""

    def score(self, query: str, doc_index: int) -> float:
        """단일 문서 스코어 반환 (ScorerProtocol 호환)."""

    def top_k(self, query: str, k: int) -> list[tuple[int, float]]:
        """(doc_index, score) top_k 목록 반환. HybridSearcher가 사용."""
```

**토큰화 전략**
```
입력: "getUserById camelCase"
→ 소문자 변환: "getuserbyid camelcase"
→ camelCase 분리: "get", "user", "by", "id", "camel", "case"
→ snake_case 분리: 이미 처리됨
→ 특수문자 제거: re.sub(r"[^a-z0-9가-힣\s]", " ", ...)
→ 공백 기준 토큰화
```

**파라미터**
```python
BM25Okapi(tokenized_corpus, k1=1.5, b=0.75)
# k1=1.5: 단어 빈도 포화점 (기본 1.5)
# b=0.75: 문서 길이 정규화 (기본 0.75)
# config에서 ADEV_RAG__BM25_K1, ADEV_RAG__BM25_B로 오버라이드 가능
```

---

### 3.3 AnthropicEmbedder

**책임**
- Anthropic voyage-3 임베딩 API 호출
- SHA256 기반 캐시로 중복 API 호출 방지
- API 실패 시 graceful degradation (벡터 검색 비활성화)

**인터페이스**
```python
class AnthropicEmbedder:
    """EmbeddingProtocol 구현체"""

    BATCH_SIZE: int = 96  # Anthropic API 배치 제한

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """EmbeddingProtocol 구현. 실패 시 빈 리스트 반환."""

    @property
    def is_available(self) -> bool:
        """임베딩 가능 여부 (API 키 존재 + 최근 호출 성공)."""
```

**캐시 구조** (`.rag_cache/embeddings.json`)
```json
{
  "sha256_of_text_1": [0.1, 0.2, ...],
  "sha256_of_text_2": [0.3, 0.4, ...]
}
```

**API 호출 흐름**
```
texts → SHA256 해시 계산
→ 캐시 히트: 즉시 반환
→ 캐시 미스: API 배치 호출 (최대 96개씩)
    anthropic.Anthropic().embeddings.create(
        model="voyage-3",
        input=batch_texts,
    )
→ 결과 캐시 저장
→ API 실패: 3회 지수 백오프 재시도
    → 여전히 실패: is_available=False, 빈 벡터 반환
```

---

### 3.4 VectorStore

**책임**
- 임베딩 벡터 저장 및 코사인 유사도 검색
- 파일 단위 삭제 지원 (증분 인덱싱용)
- lancedb 설치 여부에 따라 구현체 자동 선택

**인터페이스**
```python
class VectorStoreProtocol(Protocol):
    def add(self, chunks: list[CodeChunk], embeddings: list[list[float]]) -> None: ...
    def search(self, query_embedding: list[float], top_k: int) -> list[tuple[CodeChunk, float]]: ...
    def remove(self, file_path: str) -> None: ...
    def clear(self) -> None: ...
```

**NumpyStore (기본 구현)**
```python
class NumpyStore:
    """lancedb 없을 때 numpy 코사인 유사도 사용. 인메모리."""

    # 코사인 유사도
    # sim(a, b) = dot(a, b) / (||a|| * ||b||)
    # numpy.dot + linalg.norm 사용
```

**LanceDBStore (선택 구현)**
```python
class LanceDBStore:
    """lancedb 설치 시 ANN 검색. 대형 프로젝트 권장."""
    # .rag_cache/lancedb/ 에 저장
```

**팩토리**
```python
def create_vector_store() -> VectorStoreProtocol:
    """lancedb 설치 여부로 구현체 자동 선택."""
    try:
        import lancedb  # noqa: F401
        return LanceDBStore(...)
    except ImportError:
        return NumpyStore()
```

---

### 3.5 HybridSearcher

**책임**
- BM25 렉시컬 검색 + 벡터 시맨틱 검색 가중 결합
- 각 결과 min-max 정규화 후 합산
- 벡터 검색 불가 시 BM25-only 모드 자동 전환

**인터페이스**
```python
class HybridSearcher:
    def __init__(
        self,
        scorer: BM25Scorer,
        store: VectorStoreProtocol,
        embedder: AnthropicEmbedder,
        bm25_weight: float = 0.6,
        vector_weight: float = 0.4,
    ): ...

    async def search(
        self, query: str, top_k: int, chunks: list[CodeChunk]
    ) -> list[tuple[CodeChunk, float]]: ...
```

**검색 알고리즘**
```
1. BM25 over-fetch: top_k * 2 개 후보
2. 벡터 over-fetch: top_k * 2 개 후보 (embedder.is_available 시)
3. 정규화:
   bm25_norm[i] = (score[i] - min) / (max - min + ε)
   vec_norm[i]  = (score[i] - min) / (max - min + ε)
4. 통합 딕셔너리 구성 (chunk_id → 합산 스코어)
5. 중복 제거: 동일 file_path + start_line → 높은 스코어 유지
6. 내림차순 정렬 → top_k 반환
```

**Graceful Degradation**
```
use_vector_search=False → BM25 전용 (bm25_weight=1.0)
embedder.is_available=False → BM25 전용 자동 전환
BM25+벡터 결과 합집합이 top_k 미만 → 각각 top_k/2씩 병합
```

---

### 3.6 IncrementalIndexer

**책임**
- 최초 전체 인덱싱 + 이후 증분 업데이트
- mtime 기반 변경 파일 감지
- 의존성 주입으로 모든 컴포넌트 조합
- 싱글톤 패턴으로 executor에서 매번 재생성 방지

**인터페이스**
```python
class IncrementalIndexer:
    def __init__(
        self,
        chunker: ChunkerProtocol,
        scorer: BM25Scorer,
        store: VectorStoreProtocol,
        embedder: AnthropicEmbedder,
        project_path: str,
        cache_dir: str = ".rag_cache",
    ): ...

    def index(self) -> int:
        """전체 인덱싱. 최초 1회 또는 캐시 손상 시 호출."""

    def update(self) -> dict[str, int]:
        """증분 인덱싱. 반환값: {"added": n, "updated": n, "removed": n}"""

    async def search(self, query: str, top_k: int) -> list[CodeChunk]:
        """HybridSearcher에 위임."""
```

**캐시 구조** (`.rag_cache/`)
```
.rag_cache/
├── file_index.json    # {file_path: {mtime, chunk_count, last_indexed}}
├── bm25_index.pkl     # BM25Okapi 직렬화 (pickle)
└── embeddings.json    # {sha256: [float...]}
```

**mtime 기반 변경 감지**
```python
def _detect_changes(self) -> tuple[list[Path], list[Path], list[Path]]:
    """(new_files, modified_files, deleted_files) 반환."""
    current = {p: p.stat().st_mtime for p in self._collect_files()}
    cached = self._load_file_index()

    new = [p for p in current if str(p) not in cached]
    modified = [
        p for p in current
        if str(p) in cached and current[p] != cached[str(p)]["mtime"]
    ]
    deleted = [
        Path(p) for p in cached
        if p not in {str(f) for f in current}
    ]
    return new, modified, deleted
```

**파일 필터링**
```python
IGNORED_DIRS = {"__pycache__", ".git", "node_modules", ".venv", "venv", "dist", "build", ".rag_cache"}
SUPPORTED_EXTENSIONS = {".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".java", ".rs", ".yaml", ".md"}
BINARY_EXTENSIONS = {".pyc", ".so", ".dll", ".exe", ".bin", ".jpg", ".png", ...}
```

**싱글톤 패턴**
```python
# src/rag/incremental_indexer.py
_indexer_instance: IncrementalIndexer | None = None

def get_indexer(project_path: str) -> IncrementalIndexer:
    """모듈 레벨 싱글톤. executor._build_options()에서 사용."""
    global _indexer_instance
    if _indexer_instance is None:
        _indexer_instance = _build_indexer(project_path)
    return _indexer_instance
```

---

### 3.7 MCP Server

**책임**
- IncrementalIndexer를 통해 5종 도구를 에이전트에 노출
- 기존 `search_code`, `reindex_codebase` 유지 (하위 호환)
- 신규 3종 추가

**도구 목록**

| 도구명 | 인자 | 설명 |
|--------|------|------|
| `search_code` | query, top_k=5 | BM25+벡터 하이브리드 검색 (기존 개선) |
| `reindex_codebase` | - | IncrementalIndexer.update() 호출 (기존 개선) |
| `search_by_symbol` | name, mode="contains" | CodeChunk.name 기반 심볼 검색 |
| `get_file_structure` | path=None, depth=3 | 프로젝트 디렉토리 트리 반환 |
| `get_similar_patterns` | code_snippet, top_k=5 | 임베딩 기반 유사 코드 검색 |

**search_by_symbol 상세**
```python
# mode: "exact" | "prefix" | "contains"
# 예: name="get_user", mode="prefix" → get_user, get_user_by_id, get_user_list
async def search_by_symbol(args: dict) -> dict:
    name = args["name"]
    mode = args.get("mode", "contains")
    matches = [
        c for c in indexer.all_chunks
        if c.name and _match(c.name, name, mode)
    ]
    return _format_results(matches)
```

**get_file_structure 상세**
```python
async def get_file_structure(args: dict) -> dict:
    root = Path(args.get("path", project_path))
    depth = args.get("depth", 3)
    tree = _build_tree(root, depth, IGNORED_DIRS)
    return _text_response(tree)
```

**get_similar_patterns 상세**
```python
async def get_similar_patterns(args: dict) -> dict:
    snippet = args["code_snippet"]
    top_k = args.get("top_k", 5)
    # 임베딩 → 벡터 스토어 유사도 검색
    embedding = await indexer.embedder.embed([snippet])
    results = indexer.store.search(embedding[0], top_k)
    return _format_results([c for c, _ in results])
```

---

## 4. 통합 및 테스트 전략

### 모듈별 단위 테스트 (QC)

| 모듈 | 테스트 파일 | 핵심 케이스 |
|------|-------------|-------------|
| ASTChunker | `tests/test_chunker.py` | Python 함수 추출, 클래스+메서드 분리, 비Python 폴백, MIN/MAX 경계, SyntaxError, 빈 파일, 데코레이터, 모듈 레벨 코드 |
| BM25Scorer | `tests/test_scorer.py` | 기본 스코어링, IDF 희귀 단어 가중치, 빈 쿼리/문서, top_k 제한, camelCase 토큰화 |
| AnthropicEmbedder | `tests/test_embedder.py` | API mock 호출, 배치 분할, 캐시 히트/미스, graceful degradation, SDK 폴백 |
| VectorStore | `tests/test_vector_store.py` | NumpyStore add/search, 코사인 유사도 정확도, remove 후 결과, 빈 스토어, LanceDB mock |
| HybridSearcher | `tests/test_hybrid_search.py` | BM25-only 모드, 하이브리드 모드, 가중치 변경, 중복 제거, graceful degradation |
| IncrementalIndexer | `tests/test_incremental_indexer.py` | 최초 인덱싱, 파일 수정 증분, 파일 삭제, 캐시 저장/로드, gitignore 필터, 빈 프로젝트 |
| MCP Server | `tests/test_mcp_server.py` | 5종 도구 응답 형식, search_by_symbol 매칭 모드, get_file_structure 깊이 제한 |

### E2E QC 테스트 전략

**대상**: 이 프로젝트 자체의 `src/` 디렉토리 (실제 Python 코드)

**검증 기준**:

1. **청크 경계 정확도**
   - `ASTChunker`로 `src/core/interfaces.py` 청킹 → 7개 Protocol 클래스가 각각 독립 청크로 분리됨을 검증

2. **BM25 상위 반환 정확도**
   - 쿼리 `"ChunkerProtocol chunk method"` → `src/core/interfaces.py`의 `ChunkerProtocol` 청크가 top-3에 포함됨을 검증
   - 기존 Boolean BoW와 비교: BM25가 더 관련성 높은 청크를 상위에 반환함을 수치로 확인

3. **증분 인덱싱 효율**
   - 전체 인덱싱 후 단일 파일 수정 → `update()` 호출
   - 처리된 파일 수가 변경 파일 수와 일치함을 검증 (전체 재인덱싱 아님)

4. **하이브리드 검색 품질**
   - BM25-only vs 하이브리드 검색 결과 비교
   - 의미적으로 유사하지만 키워드가 다른 쿼리에서 하이브리드가 더 관련성 높은 결과 반환

5. **MCP 도구 응답 형식**
   - 5종 도구 모두 `{"content": [{"type": "text", "text": "..."}]}` 형식 준수

### 실패 시 자동 수정 플로우

```
테스트 실패
    → 에러 메시지 분석
    → 원인 분류:
        ImportError → 의존성 확인 (rank-bm25, numpy 설치 여부)
        AssertionError (청크 경계) → ASTChunker 노드 탐지 로직 수정
        AssertionError (스코어 순서) → 토큰화 또는 BM25 파라미터 조정
        API 오류 → AnthropicEmbedder mock 수정
    → 수정 후 해당 테스트 재실행
    → 전체 pytest 재실행으로 회귀 확인
```

---

## 5. 구현 순서 및 우선순위

모든 상위 모듈이 하위 모듈에 의존하므로, 아래 순서대로 구현한다.

```
1. ASTChunker (chunker.py)
   ↓ CodeChunk 공급
2. BM25Scorer (scorer.py)
   ↓ 스코어링 엔진
3. AnthropicEmbedder (embedder.py)
   ↓ 벡터 생성
4. VectorStore (vector_store.py)
   ↓ 벡터 저장/검색
5. HybridSearcher (hybrid_search.py)
   ↓ BM25 + 벡터 통합
6. IncrementalIndexer (incremental_indexer.py)
   ↓ 전체 조율 + 싱글톤
7. MCP Server (mcp_server.py)
   ↓ 에이전트 인터페이스
```

**이유**:
- `chunker.py`는 외부 의존성 없음 → 가장 먼저 독립 구현 가능
- `scorer.py`는 `rank-bm25`만 필요 → chunker와 병렬 가능하지만 순서 일관성 유지
- `embedder.py`는 API 키 없어도 mock으로 테스트 가능
- `vector_store.py`는 numpy만 필요 (lancedb 선택)
- `hybrid_search.py`는 3-4번 완료 후 통합
- `incremental_indexer.py`는 1-5번 모두 완료 후 조립
- `mcp_server.py`는 6번 완료 후 래핑

---

## 6. 성능 목표

| 지표 | 현재 | 목표 |
|------|------|------|
| 인덱싱 속도 (100 파일) | ~2s (전체 재인덱싱) | <0.5s (증분, 변경 없을 시) |
| 검색 정확도 (top-5 hit rate) | 측정 안 됨 | >80% (관련 파일 top-5 포함) |
| 메모리 사용량 | ~10MB (청크만) | <50MB (임베딩 포함, numpy 기준) |
| 청크 크기 일관성 | 불일치 (50줄 강제 분리) | 함수/클래스 단위 의미 경계 준수 |
| BM25 vs Boolean BoW | - | 동일 쿼리에서 BM25가 더 관련성 높은 청크 상위 반환 |

---

## 7. 모듈 간 의존성 요약

```
core/interfaces.py  ←  모든 모듈이 Protocol 계약 참조
core/domain.py      ←  CodeChunk 사용 (chunker, scorer, vector_store, hybrid_search, indexer, mcp_server)
infra/config.py     ←  RAGSettings (bm25_weight, vector_weight, top_k, use_vector_search, cache_enabled)
infra/logger.py     ←  모든 모듈이 구조화 로그 사용

chunker.py          ←  core/domain.py (CodeChunk)
scorer.py           ←  core/interfaces.py (ScorerProtocol), rank-bm25
embedder.py         ←  core/interfaces.py (EmbeddingProtocol), anthropic SDK
vector_store.py     ←  core/domain.py (CodeChunk), numpy [, lancedb]
hybrid_search.py    ←  scorer.py, vector_store.py, embedder.py, infra/config.py
incremental_indexer.py ← chunker.py, scorer.py, vector_store.py, hybrid_search.py, embedder.py
mcp_server.py       ←  incremental_indexer.py
```

**의존성 방향**: 모든 의존성은 단방향 하향. 순환 참조 없음.

---

## 8. Protocol 인터페이스 활용 전략

Phase 0에서 정의된 `src/core/interfaces.py`의 Protocol을 최대한 활용한다.

```python
# ChunkerProtocol 구현 선언
class ASTChunker:
    def chunk(self, file_path: str, content: str) -> list[CodeChunk]:
        ...
# 런타임 체크: isinstance(ASTChunker(), ChunkerProtocol) == True

# ScorerProtocol은 score(query, doc_index) → float 시그니처
# BM25Scorer가 이를 구현하고, 추가로 top_k() 편의 메서드 제공

# EmbeddingProtocol은 embed(texts) → list[list[float]] 비동기
# AnthropicEmbedder가 구현
```

**VectorStoreProtocol은 Phase 0에 정의되지 않았으므로**, `src/rag/vector_store.py` 내부에 별도 Protocol 정의:

```python
# src/rag/vector_store.py
class VectorStoreProtocol(Protocol):
    def add(self, chunks: list[CodeChunk], embeddings: list[list[float]]) -> None: ...
    def search(self, query_embedding: list[float], top_k: int) -> list[tuple[CodeChunk, float]]: ...
    def remove(self, file_path: str) -> None: ...
    def clear(self) -> None: ...
```

---

## 9. QC 통합 지점 명세

### 모듈별 QC 시점

| 단계 | 모듈 | QC 내용 | 통과 기준 |
|------|------|---------|-----------|
| 1 | chunker | Python 함수/클래스 경계 정확도 | 모든 테스트 통과, 커버리지 90%+ |
| 2 | scorer | BM25 스코어 순서 정확도 | IDF 반영 희귀 단어 가중치 검증 |
| 3 | embedder | API mock 캐시 동작 | 캐시 히트 시 API 미호출 확인 |
| 4 | vector_store | 코사인 유사도 정확도 | 동일 벡터 유사도 = 1.0 |
| 5 | hybrid_search | BM25-only + 하이브리드 분기 | 가중치 변경 시 결과 순서 변화 |
| 6 | incremental_indexer | 증분 처리 파일 수 == 변경 파일 수 | mtime 비교 정확도 |
| 7 | mcp_server | 5종 도구 응답 형식 | MCP 표준 응답 구조 준수 |

### E2E QC 기준

`pytest tests/ -v --cov` 전체 통과 후:

1. `ruff check src/` — 린트 에러 0개
2. `mypy src/` — 타입 에러 0개
3. 커버리지 90%+
4. BM25가 Boolean BoW 대비 top-5 hit rate 개선 확인 (수동 검증)
5. 단일 파일 수정 후 `update()` — 처리 파일 수 = 1 (증분 검증)
6. MCP 서버 새 도구 3개 정상 응답 확인
