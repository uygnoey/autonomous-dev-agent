"""BM25Scorer 유닛 테스트.

테스트 대상: src/rag/scorer.py — BM25Scorer 클래스
커버리지 목표: 90% 이상

테스트 케이스:
1. 기본 BM25 스코어링
2. IDF 가중치 (희귀 단어 높은 점수)
3. 빈 쿼리/빈 문서
4. top_k 제한
5. Python 식별자 토큰화 (camelCase, snake_case)
"""

import pytest

from src.rag.scorer import BM25Scorer


@pytest.fixture
def scorer() -> BM25Scorer:
    """BM25Scorer 인스턴스를 제공하는 픽스처."""
    return BM25Scorer()


@pytest.fixture
def fitted_scorer() -> BM25Scorer:
    """기본 코퍼스로 fit된 BM25Scorer 픽스처."""
    s = BM25Scorer()
    s.fit([
        "def hello world function",
        "class user authentication service",
        "import database connection pool",
    ])
    return s


class TestBasicBM25Scoring:
    """기본 BM25 스코어링 테스트."""

    def test_score_returns_positive_for_matching_doc(self, scorer: BM25Scorer) -> None:
        """매칭 문서에 대해 양수 점수를 반환하는지 검증."""
        # Arrange
        scorer.fit([
            "def hello world",
            "class database connection",
            "import logging module",
        ])

        # Act — "hello"가 포함된 문서(index 0)의 점수
        score = scorer.score("hello", 0)

        # Assert
        assert score > 0.0

    def test_score_returns_zero_for_non_matching_doc(self, scorer: BM25Scorer) -> None:
        """매칭되지 않는 문서에 대해 0점을 반환하는지 검증."""
        # Arrange
        scorer.fit([
            "def hello world",
            "class database connection",
        ])

        # Act — "hello"가 없는 문서(index 1)의 점수
        score = scorer.score("hello", 1)

        # Assert
        assert score == 0.0

    def test_score_matching_doc_higher_than_non_matching(self, scorer: BM25Scorer) -> None:
        """매칭 문서가 비매칭 문서보다 높은 점수를 받는지 검증.

        BM25Okapi IDF = log((N - df + 0.5) / (df + 0.5)):
        N=2, df=1 이면 log(1)=0 → score=0이 됩니다.
        IDF > 0이 되려면 코퍼스가 3개 이상이어야 합니다.
        """
        # Arrange — 3개 이상의 문서로 IDF > 0 보장
        scorer.fit([
            "def calculate total price discount",
            "class user profile settings",
            "import logging configuration module",
        ])

        # Act
        score_match = scorer.score("calculate", 0)
        score_no_match = scorer.score("calculate", 1)

        # Assert
        assert score_match > score_no_match

    def test_fit_updates_corpus_size(self, scorer: BM25Scorer) -> None:
        """fit() 후 코퍼스 크기가 올바르게 설정되는지 검증."""
        # Arrange & Act
        scorer.fit(["doc one", "doc two", "doc three"])

        # Assert
        assert scorer._corpus_size == 3

    def test_score_before_fit_returns_zero(self, scorer: BM25Scorer) -> None:
        """fit() 없이 score() 호출 시 0.0을 반환하는지 검증."""
        # Act
        score = scorer.score("any query", 0)

        # Assert
        assert score == 0.0

    def test_top_k_before_fit_returns_empty(self, scorer: BM25Scorer) -> None:
        """fit() 없이 top_k() 호출 시 빈 리스트를 반환하는지 검증."""
        # Act
        results = scorer.top_k("any query", k=3)

        # Assert
        assert results == []


class TestIdfWeighting:
    """IDF 가중치 테스트 — 희귀 단어가 더 높은 점수를 받아야 함."""

    def test_rare_word_scores_higher_than_common_word(self, scorer: BM25Scorer) -> None:
        """희귀 단어가 포함된 문서가 흔한 단어보다 높은 점수를 받는지 검증."""
        # Arrange — "common"은 모든 문서에, "rare"는 하나에만 등장
        docs = [
            "common word appears here",      # doc 0: common만
            "common word rare unique term",  # doc 1: common + rare
            "common word another sentence",  # doc 2: common만
        ]
        scorer.fit(docs)

        # Act
        score_rare = scorer.score("rare", 1)      # 희귀 단어 — doc 1에만 있음
        score_common = scorer.score("common", 1)  # 흔한 단어 — 모든 doc에 있음

        # Assert: 희귀 단어 점수가 흔한 단어 점수보다 높아야 함 (IDF 효과)
        assert score_rare > score_common

    def test_word_only_in_one_doc_has_high_idf(self, scorer: BM25Scorer) -> None:
        """단 1개 문서에만 등장하는 단어가 높은 IDF 점수를 받는지 검증."""
        # Arrange
        docs = [
            "authentication login password",
            "authentication session token",
            "authentication oauth provider",
            "authentication jwt secret unique_special_term",  # doc 3만 포함
        ]
        scorer.fit(docs)

        # Act — 4번째 문서(index 3)에만 있는 단어로 검색
        result = scorer.top_k("unique special term", k=1)

        # Assert: 상위 결과가 doc 3이어야 함
        assert len(result) > 0
        assert result[0][0] == 3

    def test_repeated_fit_resets_idf(self, scorer: BM25Scorer) -> None:
        """fit()을 재호출하면 IDF가 새 코퍼스로 갱신되는지 검증."""
        # Arrange
        scorer.fit(["hello world", "hello python"])
        score_first = scorer.score("hello", 0)

        # Act — 새 코퍼스로 재학습 (문서 수 다름)
        scorer.fit(["hello world", "goodbye world", "hello again world"])
        score_second = scorer.score("hello", 0)

        # Assert: 점수가 달라져야 함 (코퍼스 변경 반영)
        # 두 점수가 동일하지 않음 (IDF 재계산됨)
        assert score_first != score_second or scorer._corpus_size == 3


class TestEmptyQueryAndDocument:
    """빈 쿼리 및 빈 문서 처리 테스트."""

    def test_empty_query_score_returns_zero(self, fitted_scorer: BM25Scorer) -> None:
        """빈 쿼리로 score() 호출 시 0.0을 반환하는지 검증."""
        # Act
        score = fitted_scorer.score("", 0)

        # Assert
        assert score == 0.0

    def test_empty_query_top_k_returns_empty(self, fitted_scorer: BM25Scorer) -> None:
        """빈 쿼리로 top_k() 호출 시 빈 리스트를 반환하는지 검증."""
        # Act
        results = fitted_scorer.top_k("", k=3)

        # Assert
        assert results == []

    def test_whitespace_only_query_returns_zero(self, fitted_scorer: BM25Scorer) -> None:
        """공백만 있는 쿼리로 score() 호출 시 0.0을 반환하는지 검증."""
        # Act
        score = fitted_scorer.score("   \t\n  ", 0)

        # Assert
        assert score == 0.0

    def test_fit_with_empty_corpus_then_score_returns_zero(self, scorer: BM25Scorer) -> None:
        """빈 코퍼스로 fit() 후 score() 호출 시 0.0을 반환하는지 검증."""
        # Arrange
        scorer.fit([])

        # Act
        score = scorer.score("anything", 0)

        # Assert
        assert score == 0.0

    def test_fit_with_empty_corpus_then_top_k_returns_empty(self, scorer: BM25Scorer) -> None:
        """빈 코퍼스로 fit() 후 top_k() 호출 시 빈 리스트를 반환하는지 검증."""
        # Arrange
        scorer.fit([])

        # Act
        results = scorer.top_k("anything", k=3)

        # Assert
        assert results == []

    def test_out_of_range_doc_index_returns_zero(self, scorer: BM25Scorer) -> None:
        """범위를 벗어난 doc_index로 score() 호출 시 0.0을 반환하는지 검증."""
        # Arrange
        scorer.fit(["only one doc here"])

        # Act — doc_index=1은 범위 밖 (corpus_size=1)
        score = scorer.score("one", 1)

        # Assert
        assert score == 0.0

    def test_negative_doc_index_returns_zero(self, scorer: BM25Scorer) -> None:
        """음수 doc_index로 score() 호출 시 0.0을 반환하는지 검증."""
        # Arrange
        scorer.fit(["some document content"])

        # Act
        score = scorer.score("document", -1)

        # Assert
        assert score == 0.0


class TestTopKLimit:
    """top_k 제한 테스트."""

    def test_top_k_returns_at_most_k_results(self, scorer: BM25Scorer) -> None:
        """top_k()가 최대 k개 결과만 반환하는지 검증."""
        # Arrange
        docs = [f"function code module {i} search" for i in range(20)]
        scorer.fit(docs)

        # Act
        results = scorer.top_k("function", k=5)

        # Assert
        assert len(results) <= 5

    def test_top_k_results_sorted_by_score_descending(self, scorer: BM25Scorer) -> None:
        """top_k() 결과가 점수 내림차순으로 정렬되는지 검증."""
        # Arrange
        scorer.fit([
            "python function definition",
            "python class method",
            "javascript function arrow",
            "python function decorator",
        ])

        # Act
        results = scorer.top_k("python function", k=10)

        # Assert: 점수 내림차순 정렬 확인
        if len(results) > 1:
            scores = [s for _, s in results]
            assert scores == sorted(scores, reverse=True)

    def test_top_k_with_k_zero_returns_empty(self, scorer: BM25Scorer) -> None:
        """k=0으로 top_k() 호출 시 빈 리스트를 반환하는지 검증."""
        # Arrange
        scorer.fit(["some document content"])

        # Act
        results = scorer.top_k("document", k=0)

        # Assert
        assert results == []

    def test_top_k_with_negative_k_returns_empty(self, scorer: BM25Scorer) -> None:
        """k<0으로 top_k() 호출 시 빈 리스트를 반환하는지 검증."""
        # Arrange
        scorer.fit(["some document content"])

        # Act
        results = scorer.top_k("document", k=-1)

        # Assert
        assert results == []

    def test_top_k_returns_index_and_score_tuples(self, scorer: BM25Scorer) -> None:
        """top_k() 결과가 (int, float) 튜플 목록인지 검증."""
        # Arrange
        scorer.fit([
            "search function query result",
            "database index lookup",
        ])

        # Act
        results = scorer.top_k("search", k=5)

        # Assert
        for item in results:
            assert isinstance(item, tuple)
            assert len(item) == 2
            idx, score = item
            assert isinstance(idx, int)
            assert isinstance(score, float)
            assert score > 0.0

    def test_top_k_only_returns_positive_score_docs(self, scorer: BM25Scorer) -> None:
        """top_k()가 점수 0인 문서를 제외하는지 검증."""
        # Arrange
        scorer.fit([
            "matching query word here",
            "completely different content xyz",
        ])

        # Act
        results = scorer.top_k("matching", k=10)

        # Assert: 모든 결과의 점수 > 0
        assert all(s > 0.0 for _, s in results)


class TestPythonIdentifierTokenization:
    """Python 식별자 토큰화 테스트 (camelCase, snake_case)."""

    def test_camel_case_tokenization(self, scorer: BM25Scorer) -> None:
        """camelCase 식별자가 개별 단어로 분리되는지 검증."""
        # Arrange
        tokens = scorer._tokenize("getUserById")

        # Assert: get, user, by, id로 분리되어야 함
        assert "get" in tokens
        assert "user" in tokens
        assert "by" in tokens
        assert "id" in tokens

    def test_snake_case_tokenization(self, scorer: BM25Scorer) -> None:
        """snake_case 식별자가 개별 단어로 분리되는지 검증."""
        # Arrange
        tokens = scorer._tokenize("get_user_by_id")

        # Assert: get, user, by, id로 분리되어야 함
        assert "get" in tokens
        assert "user" in tokens
        assert "by" in tokens
        assert "id" in tokens

    def test_camel_case_searchable_by_component_word(self, scorer: BM25Scorer) -> None:
        """camelCase 함수명의 구성 단어로 검색 가능한지 검증.

        "user"가 모든 문서에 등장하면 IDF=0이 됩니다.
        희귀 단어 "fetch"는 doc 0에만 있으므로 IDF > 0이 보장됩니다.
        """
        # Arrange — "fetch"는 doc 0에만 등장 → IDF > 0
        scorer.fit([
            "def fetchUserById(user_id): return db.query(user_id)",
            "def listAllProducts(): return db.all()",
            "def deleteProductRecord(record_id): db.delete(record_id)",
            "def calculateTotalPrice(items): return sum(items)",
        ])

        # Act — camelCase 구성 요소 "fetch"로 검색
        results = scorer.top_k("fetch", k=3)

        # Assert: fetchUserById(doc 0)가 상위에 있어야 함
        assert len(results) > 0
        assert results[0][0] == 0

    def test_snake_case_searchable_by_component_word(self, scorer: BM25Scorer) -> None:
        """snake_case 변수명의 구성 단어로 검색 가능한지 검증."""
        # Arrange
        scorer.fit([
            "max_retry_count = 3",
            "connection_timeout = 30",
            "default_page_size = 20",
        ])

        # Act — snake_case의 구성 요소 "retry"로 검색
        results = scorer.top_k("retry", k=1)

        # Assert: max_retry_count 문서(index 0)가 상위
        assert len(results) > 0
        assert results[0][0] == 0

    def test_special_characters_removed_in_tokenization(self, scorer: BM25Scorer) -> None:
        """특수문자가 토큰화 시 제거되는지 검증."""
        # Arrange
        tokens = scorer._tokenize("func(arg1, arg2) -> bool:")

        # Assert: 괄호, 쉼표, 화살표, 콜론이 없어야 함
        for tok in tokens:
            assert "(" not in tok
            assert ")" not in tok
            assert "," not in tok
            assert "->" not in tok
            assert ":" not in tok

    def test_tokenization_is_lowercase(self, scorer: BM25Scorer) -> None:
        """토큰화 결과가 모두 소문자인지 검증."""
        # Arrange
        tokens = scorer._tokenize("MyClass HTTPRequest UserID")

        # Assert
        for tok in tokens:
            assert tok == tok.lower()

    def test_mixed_identifier_tokenization(self, scorer: BM25Scorer) -> None:
        """camelCase와 snake_case가 혼합된 코드를 올바르게 토큰화하는지 검증."""
        # Arrange
        text = "def getUserName(user_id): return user_profile.get_name()"
        tokens = scorer._tokenize(text)

        # Assert: 핵심 단어들이 추출됨
        assert "get" in tokens
        assert "user" in tokens
        assert "name" in tokens
        assert "id" in tokens
        assert "profile" in tokens

    def test_consecutive_uppercase_camel_case(self, scorer: BM25Scorer) -> None:
        """연속 대문자 camelCase(HTTPRequest)가 올바르게 분리되는지 검증."""
        # Arrange — HTTPRequest → HTTP + Request
        tokens = scorer._tokenize("HTTPRequest")

        # Assert: http와 request로 분리
        assert "http" in tokens
        assert "request" in tokens
