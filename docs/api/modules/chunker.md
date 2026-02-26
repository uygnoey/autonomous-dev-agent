# ASTChunker API

**파일**: `src/rag/chunker.py`

AST 기반 코드 청크 분할기. Python 파일은 함수·클래스·메서드 경계를 추출하여 의미 단위로 분할하고, 비Python 파일은 50줄 고정 크기 + 10줄 오버랩 폴백을 사용합니다.

## 클래스

### `ASTChunker`

`ChunkerProtocol`(`src/core/interfaces.py`)을 구조적으로 준수합니다.

#### 클래스 속성

| 속성 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `MIN_LINES` | `int` | `5` | 5줄 미만 함수는 module 청크에 병합 |
| `MAX_LINES` | `int` | `100` | 100줄 초과 ClassDef는 메서드별 서브청킹 |
| `BLOCK_SIZE` | `int` | `50` | 비Python 파일 블록 크기 |
| `OVERLAP` | `int` | `10` | 비Python 파일 오버랩 줄 수 |

#### 메서드

##### `chunk(file_path, content) -> list[CodeChunk]`

파일 내용을 CodeChunk 리스트로 분할합니다.

```python
def chunk(self, file_path: str, content: str) -> list[CodeChunk]
```

**파라미터**

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `file_path` | `str` | 파일 경로 (메타데이터 용도, 확장자로 처리 방식 결정) |
| `content` | `str` | 파일 전체 텍스트 내용 |

**반환값**

`list[CodeChunk]` — 분할된 코드 청크 목록. 빈 파일이면 빈 리스트.

**동작 방식**

- `.py` 파일: AST 파싱 → 함수/클래스/메서드/모듈 청크 생성
- 기타 파일(`.js`, `.ts`, `.tsx`, `.jsx`, `.yaml`, `.yml`, `.md`, `.go`, `.java`, `.rs`): 50줄 고정 + 10줄 오버랩 블록 청크
- `SyntaxError` 발생 시: 폴백(고정 크기 블록)으로 graceful 처리

**사용 예시**

```python
from src.rag.chunker import ASTChunker

chunker = ASTChunker()

# Python 파일 청킹
with open("src/rag/scorer.py") as f:
    content = f.read()

chunks = chunker.chunk("src/rag/scorer.py", content)
for chunk in chunks:
    print(f"{chunk.chunk_type}: {chunk.name} ({chunk.start_line}-{chunk.end_line})")
# 출력 예:
# class: BM25Scorer (29-171)
# method: __init__ (50-51)
# method: fit (54-81)
# method: score (83-111)
# method: top_k (113-140)
# method: _tokenize (146-171)
# module: None (1-27)
```

## 청크 타입

| `chunk_type` | 생성 조건 |
|-------------|----------|
| `"function"` | 최상위 `FunctionDef` / `AsyncFunctionDef` (MIN_LINES 이상) |
| `"class"` | `ClassDef` (MAX_LINES 이하) |
| `"method"` | ClassDef 내부 `FunctionDef` / `AsyncFunctionDef` (MIN_LINES 이상) |
| `"module"` | 함수·클래스에 속하지 않는 모듈 레벨 코드 |
| `"block"` | 비Python 파일의 고정 크기 블록 |

## 크기 규칙

| 조건 | 처리 |
|------|------|
| 함수/메서드가 `MIN_LINES(5)` 미만 | module 청크에 병합 |
| ClassDef가 `MAX_LINES(100)` 초과 | 클래스 청크 생략, 메서드 청크만 생성 |

## 지원 파일 형식

- **AST 파싱**: `.py`
- **폴백(50줄 블록)**: `.js`, `.ts`, `.tsx`, `.jsx`, `.yaml`, `.yml`, `.md`, `.go`, `.java`, `.rs`

## 모듈 레벨 헬퍼

내부 헬퍼 함수들은 모두 모듈 레벨에 정의되어 있습니다.

- `_end_lineno(node)` — AST 노드의 마지막 줄 번호 반환
- `_decorator_start(node)` — 데코레이터 포함 시작 줄 번호 반환
- `_extract_lines(lines, start_line, end_line)` — 1-indexed 라인 범위 텍스트 추출
