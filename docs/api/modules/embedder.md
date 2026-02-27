# AnthropicEmbedder API

**파일**: `src/rag/embedder.py`

Anthropic Voyage AI 임베딩 모듈. Voyage AI API(`voyage-3` 모델)를 호출하여 텍스트를 벡터로 변환합니다. SHA256 기반 파일 캐시로 중복 API 호출을 방지하고, API 실패 시 graceful degradation으로 빈 벡터를 반환합니다.

### Subscription 환경 지원 (Fallback Mode)

`VOYAGE_API_KEY`와 `ANTHROPIC_API_KEY`가 모두 없거나 API 호출이 영구 실패하면 **BM25-only 폴백 모드**로 자동 전환됩니다.

- `is_available=False`, `fallback_mode=True` 상태가 됩니다.
- 이후 `embed()` 호출은 즉시 빈 리스트를 반환합니다.
- Subscription 환경(claude-agent-sdk / anthropic SDK)에서는 임베딩 API가 제공되지 않으므로 벡터 검색 대신 BM25 텍스트 검색만 사용됩니다.

## 클래스

### `AnthropicEmbedder`

`EmbeddingProtocol`(`src/core/interfaces.py`)을 구조적으로 준수합니다.

#### 클래스 속성

| 속성 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `BATCH_SIZE` | `int` | `96` | Voyage AI API 배치 제한 |

#### 생성자

```python
def __init__(self, cache_path: str = ".rag_cache/embeddings.json") -> None
```

**파라미터**

| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| `cache_path` | `str` | `".rag_cache/embeddings.json"` | 임베딩 캐시 JSON 파일 경로 |

**인증 우선순위**: `VOYAGE_API_KEY` → `ANTHROPIC_API_KEY` 환경변수 순서로 시도.

#### 속성

##### `is_available -> bool`

임베딩 가능 여부를 반환합니다.

```python
@property
def is_available(self) -> bool
```

`True`: API 키 존재 + 최근 호출 성공.
`False`: API 키 없음 또는 최근 API 실패.

---

##### `fallback_mode -> bool`

BM25 전용 폴백 모드 여부를 반환합니다.

```python
@property
def fallback_mode(self) -> bool
```

`True`이면 `embed()`는 항상 빈 리스트를 반환하고, 호출측은 BM25만으로 검색을 수행합니다.

**폴백 모드 진입 조건:**

| 조건 | 설명 |
|------|------|
| API 키 없음 | `VOYAGE_API_KEY`와 `ANTHROPIC_API_KEY` 모두 미설정 시 초기화 단계에서 즉시 전환 |
| 4xx 클라이언트 오류 | 잘못된 키 등 클라이언트 측 오류 → 재시도 없이 즉시 전환 |
| 최대 재시도 초과 | 3회 지수 백오프 재시도 후 영구 실패 시 전환 |

#### 메서드

##### `embed(texts) -> list[list[float]]`

텍스트 목록을 임베딩 벡터로 변환합니다.

```python
async def embed(self, texts: list[str]) -> list[list[float]]
```

**파라미터**

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `texts` | `list[str]` | 임베딩할 텍스트 목록 |

**반환값**

`list[list[float]]` — 각 텍스트에 대응하는 float 벡터 목록. 실패 시 빈 리스트(`[]`).

**동작 방식**

1. SHA256 해시로 캐시 히트/미스 분류
2. 캐시 미스 텍스트만 Voyage AI API 배치 호출 (최대 `BATCH_SIZE=96`개씩)
3. 결과를 캐시에 저장
4. API 실패 시: 3회 지수 백오프 재시도
5. 최종 실패 시: `is_available=False` 설정, 캐시 히트 부분만 반환 (graceful degradation)

## 재시도 정책

| 설정 | 값 |
|------|-----|
| 최대 재시도 횟수 | 3회 |
| 기본 대기 시간 | 1.0초 |
| 최대 대기 시간 | 30.0초 |
| 알고리즘 | 지수 백오프 (1s → 2s → 4s ...) |

**HTTP 상태별 처리:**

| 상태 코드 | 처리 |
|---------|------|
| `429` (Rate Limit) | `Retry-After` 헤더 우선, 없으면 지수 백오프 |
| `5xx` (서버 오류) | 지수 백오프 재시도 |
| `4xx` (클라이언트 오류) | 즉시 실패, 재시도 없음 |

## 캐시 구조

**파일**: `.rag_cache/embeddings.json`

```json
{
  "<sha256_hash_of_text>": [0.123, -0.456, 0.789, ...],
  "<sha256_hash_of_text2>": [0.321, 0.654, -0.987, ...]
}
```

캐시 키는 텍스트의 SHA256 해시(64자 16진수)입니다. 디렉토리가 없으면 자동 생성합니다.

## 사용 예시

```python
import asyncio
from src.rag.embedder import AnthropicEmbedder

embedder = AnthropicEmbedder()

async def main():
    # fallback_mode 확인 (API 키 없음 / 영구 실패 시 True)
    if embedder.fallback_mode:
        print("BM25-only 폴백 모드 — 벡터 검색 비활성화")
        return

    if not embedder.is_available:
        print("임베딩 일시 불가")
        return

    texts = [
        "def get_user(user_id: int) -> User:",
        "class UserService: ...",
    ]

    vectors = await embedder.embed(texts)
    print(f"임베딩 차원: {len(vectors[0])}")  # voyage-3: 1024차원
    print(f"벡터 수: {len(vectors)}")

asyncio.run(main())
```

## Voyage AI API 정보

| 항목 | 값 |
|------|-----|
| API 엔드포인트 | `https://api.voyageai.com/v1/embeddings` |
| 모델 | `voyage-3` |
| 임베딩 차원 | 1024 |
| 배치 제한 | 96개/요청 |
| 타임아웃 | 60초 |
