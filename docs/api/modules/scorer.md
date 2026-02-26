# BM25Scorer API

**파일**: `src/rag/scorer.py`

BM25 기반 렉시컬 스코어링 모듈. rank-bm25 라이브러리의 `BM25Okapi`를 래핑하여 코드 검색에 최적화된 토큰화와 IDF 가중치 스코어링을 제공합니다.

## 클래스

### `BM25Scorer`

`ScorerProtocol`(`src/core/interfaces.py`)을 구조적으로 준수합니다.

`fit()` → `score()` / `top_k()` 순서로 사용합니다. `fit()` 호출 전에는 `score()`가 `0.0`을 반환하고 `top_k()`가 빈 리스트를 반환합니다.

#### 클래스 속성

| 속성 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `K1` | `float` | `1.5` | 단어 빈도 포화점 (높을수록 빈도 가중치 증가) |
| `B` | `float` | `0.75` | 문서 길이 정규화 강도 (1.0=완전 정규화, 0.0=없음) |

#### 메서드

##### `fit(documents) -> None`

BM25 인덱스를 학습합니다.

```python
def fit(self, documents: list[str]) -> None
```

**파라미터**

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `documents` | `list[str]` | 학습에 사용할 문서 텍스트 목록 |

**동작 방식**

- 빈 코퍼스(`[]`)는 허용하지만 이후 `score()`는 `0.0`을 반환
- 모든 문서가 빈 토큰이면 경고 로그 후 `_bm25 = None`으로 설정
- 코퍼스 변경 시 재호출해야 IDF가 갱신됨

---

##### `score(query, doc_index) -> float`

단일 문서에 대한 BM25 관련도 점수를 반환합니다.

```python
def score(self, query: str, doc_index: int) -> float
```

**파라미터**

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `query` | `str` | 검색 쿼리 |
| `doc_index` | `int` | 대상 문서의 인덱스 (fit 시 전달한 목록 기준) |

**반환값**

`float` — BM25 관련도 점수 (0.0 이상). `fit()` 미호출 또는 범위 벗어난 인덱스는 `0.0`.

---

##### `top_k(query, k) -> list[tuple[int, float]]`

쿼리에 대한 상위 k개 문서 인덱스와 점수를 반환합니다.

```python
def top_k(self, query: str, k: int) -> list[tuple[int, float]]
```

**파라미터**

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `query` | `str` | 검색 쿼리 |
| `k` | `int` | 반환할 최대 결과 수 |

**반환값**

`list[tuple[int, float]]` — `(doc_index, score)` 튜플 목록 (점수 내림차순 정렬). 점수가 0보다 큰 항목만 포함.

---

##### `_tokenize(text) -> list[str]` (내부 메서드)

코드 특화 토큰화를 수행합니다.

**토큰화 순서:**

1. camelCase 경계 분리 (`getUserById` → `get User By Id`)
2. 소문자 변환
3. 특수문자 제거 (알파벳·숫자·한글·공백만 유지)
4. 공백 기준 분리 후 빈 토큰 제거

snake_case는 `_`가 공백으로 치환되어 자동 분리됩니다.

## 사용 예시

```python
from src.rag.scorer import BM25Scorer

scorer = BM25Scorer()

documents = [
    "def get_user_by_id(user_id: int) -> User:",
    "class UserService: ...",
    "def authenticate(token: str) -> bool:",
]

scorer.fit(documents)

# 단일 문서 스코어
score = scorer.score("get user", doc_index=0)
print(f"score: {score:.4f}")  # 예: 0.8234

# 상위 k개 결과
results = scorer.top_k("user authentication", k=2)
for doc_index, score in results:
    print(f"doc[{doc_index}]: {score:.4f}")
# 출력 예:
# doc[2]: 0.9123
# doc[1]: 0.5432
```

## BM25 하이퍼파라미터

| 파라미터 | 값 | 의미 |
|---------|-----|------|
| `k1=1.5` | 기본값 | 단어 빈도 포화점. 클수록 빈도 가중치 증가 |
| `b=0.75` | 기본값 | 문서 길이 정규화. 1.0은 완전 정규화, 0.0은 없음 |
