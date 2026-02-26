"""BM25 기반 렉시컬 스코어링 모듈.

rank-bm25 라이브러리의 BM25Okapi를 래핑하여 코드 검색에 최적화된
토큰화와 IDF 가중치 스코어링을 제공한다.

ScorerProtocol(src/core/interfaces.py)을 구조적으로 준수한다.
"""

from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

from src.utils.logger import setup_logger

logger = setup_logger(__name__)

# camelCase 단어 경계 패턴: 소문자→대문자 또는 대문자→대문자+소문자 경계
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

# 코드 식별자에서 허용할 문자 (알파벳, 숫자, 한글, 공백)
_ALLOWED_CHARS = re.compile(r"[^a-z0-9가-힣\s]")

# fit() 없이 score()/top_k() 호출 시 반환할 기본값
_UNFITTED_SCORE = 0.0


class BM25Scorer:
    """BM25 IDF 가중치 기반 코드 렉시컬 스코어러.

    ScorerProtocol(src/core/interfaces.py)을 구조적으로 준수한다.

    fit() → score() / top_k() 순서로 사용한다.
    fit() 호출 전에는 score()가 0.0을 반환하고 top_k()가 빈 리스트를 반환한다.

    토큰화 전략:
      1. camelCase 단어 경계 분리 (getUserById → get User By Id)
      2. 소문자 변환
      3. 특수문자 제거 (알파벳·숫자·한글·공백만 유지)
      4. 공백 기준 토큰 분리
    """

    # BM25Okapi 하이퍼파라미터
    # k1: 단어 빈도 포화점 (높을수록 빈도 가중치 증가)
    # b: 문서 길이 정규화 강도 (1.0 = 완전 정규화, 0.0 = 정규화 없음)
    K1: float = 1.5
    B: float = 0.75

    def __init__(self) -> None:
        self._bm25: BM25Okapi | None = None
        self._corpus_size: int = 0

    def fit(self, documents: list[str]) -> None:
        """BM25 인덱스를 학습한다.

        코퍼스가 변경될 때마다 재호출해야 IDF가 갱신된다.
        빈 코퍼스도 허용하지만 이후 score()는 0.0을 반환한다.

        Args:
            documents: 학습에 사용할 문서 텍스트 목록
        """
        if not documents:
            self._bm25 = None
            self._corpus_size = 0
            logger.warning("BM25Scorer.fit: 빈 코퍼스로 호출됨. score()는 0.0을 반환합니다.")
            return

        tokenized = [self._tokenize(doc) for doc in documents]
        # 모든 문서가 빈 토큰인 경우 BM25Okapi 내부 ZeroDivisionError 방지
        # (특수문자만 있는 문서 등 토큰화 후 빈 리스트가 될 수 있음)
        if not any(tokenized):
            self._bm25 = None
            self._corpus_size = 0
            logger.warning(
                "BM25Scorer.fit: 토큰화 결과 모든 문서가 빈 토큰. score()는 0.0을 반환합니다."
            )
            return
        self._bm25 = BM25Okapi(tokenized, k1=self.K1, b=self.B)
        self._corpus_size = len(documents)
        logger.debug(f"BM25Scorer.fit 완료: {self._corpus_size}개 문서")

    def score(self, query: str, doc_index: int) -> float:
        """단일 문서에 대한 BM25 관련도 점수를 반환한다.

        ScorerProtocol 호환 메서드. fit() 호출 전이거나
        doc_index가 범위를 벗어나면 0.0을 반환한다.

        Args:
            query: 검색 쿼리
            doc_index: 대상 문서의 인덱스 (fit 시 전달한 목록 기준)

        Returns:
            BM25 관련도 점수 (0.0 이상, 높을수록 관련성 높음)
        """
        if self._bm25 is None:
            return _UNFITTED_SCORE

        if doc_index < 0 or doc_index >= self._corpus_size:
            logger.warning(
                f"BM25Scorer.score: doc_index={doc_index}가 범위를 벗어남 "
                f"(corpus_size={self._corpus_size})"
            )
            return _UNFITTED_SCORE

        tokens = self._tokenize(query)
        if not tokens:
            return _UNFITTED_SCORE

        scores: list[float] = self._bm25.get_scores(tokens)
        return float(scores[doc_index])

    def top_k(self, query: str, k: int) -> list[tuple[int, float]]:
        """쿼리에 대한 상위 k개 문서 인덱스와 점수를 반환한다.

        HybridSearcher가 over-fetch(k*2) 후 재랭킹에 사용한다.
        fit() 호출 전이거나 쿼리 토큰이 없으면 빈 리스트를 반환한다.

        Args:
            query: 검색 쿼리
            k: 반환할 최대 결과 수

        Returns:
            (doc_index, score) 튜플 목록 (점수 내림차순 정렬)
        """
        if self._bm25 is None or k <= 0:
            return []

        tokens = self._tokenize(query)
        if not tokens:
            return []

        scores: list[float] = self._bm25.get_scores(tokens)

        # 점수가 0보다 큰 항목만 추출하여 내림차순 정렬
        indexed = [
            (idx, float(s)) for idx, s in enumerate(scores) if s > 0.0
        ]
        indexed.sort(key=lambda x: x[1], reverse=True)
        return indexed[:k]

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _tokenize(self, text: str) -> list[str]:
        """코드 특화 토큰화를 수행한다.

        처리 순서:
          1. camelCase 경계 분리 (getUserById → get User By Id)
          2. 소문자 변환
          3. 특수문자 제거 (알파벳·숫자·한글·공백만 유지)
          4. 공백 기준 분리 후 빈 토큰 제거

        snake_case는 특수문자 제거 단계에서 '_'가 공백으로 치환되므로
        별도 처리 없이 자동 분리된다.

        Args:
            text: 토큰화할 텍스트

        Returns:
            소문자 토큰 목록
        """
        # 1. camelCase 경계 공백 삽입
        text = _CAMEL_BOUNDARY.sub(" ", text)
        # 2. 소문자 변환
        text = text.lower()
        # 3. 허용 문자 외 모두 공백으로 치환
        text = _ALLOWED_CHARS.sub(" ", text)
        # 4. 공백 기준 분리, 빈 토큰 제거
        return [tok for tok in text.split() if tok]
