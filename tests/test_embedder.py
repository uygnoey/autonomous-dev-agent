"""AnthropicEmbedder 유닛 테스트 / AnthropicEmbedder Unit Tests.

테스트 대상 / Test Target:
    src/rag/embedder.py — AnthropicEmbedder 클래스 / AnthropicEmbedder class

커버리지 목표 / Coverage Target: 90% 이상 / 90% or higher

테스트 케이스 / Test Cases:
1. API 호출 mock (Voyage AI httpx.AsyncClient)
2. 배치 분할 로직 (96개 초과 시 자동 분할)
3. 캐시 히트/미스
4. 에러 시 graceful degradation (API 호출 실패 시 빈 임베딩 반환 + 경고 로깅)
5. API 키 없음 (SDK 폴백 모드) — BM25 폴백 동작 + fallback_mode 속성 + 경고 로깅
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.rag.embedder import AnthropicEmbedder, _exponential_delay, _sha256


# ---------------------------------------------------------------------------
# 공통 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_cache(tmp_path: Path) -> Path:
    """테스트용 임시 캐시 경로."""
    return tmp_path / "embeddings.json"


@pytest.fixture
def embedder(tmp_cache: Path) -> AnthropicEmbedder:
    """VOYAGE_API_KEY가 설정된 AnthropicEmbedder 픽스처."""
    with patch.dict("os.environ", {"VOYAGE_API_KEY": "test-api-key"}, clear=False):
        return AnthropicEmbedder(cache_path=str(tmp_cache))


@pytest.fixture
def embedder_no_key(tmp_cache: Path) -> AnthropicEmbedder:
    """API 키가 없는 AnthropicEmbedder 픽스처."""
    with patch.dict("os.environ", {}, clear=False):
        import os
        old_voyage = os.environ.pop("VOYAGE_API_KEY", None)
        old_anthropic = os.environ.pop("ANTHROPIC_API_KEY", None)
        embedder = AnthropicEmbedder(cache_path=str(tmp_cache))
        if old_voyage is not None:
            os.environ["VOYAGE_API_KEY"] = old_voyage
        if old_anthropic is not None:
            os.environ["ANTHROPIC_API_KEY"] = old_anthropic
        return embedder


def _make_voyage_response(texts: list[str], dim: int = 4) -> dict:
    """Voyage AI API 응답 형식의 mock 데이터를 생성한다."""
    return {
        "data": [
            {"index": i, "embedding": [float(i + 1)] * dim}
            for i in range(len(texts))
        ]
    }


def _make_mock_response(texts: list[str], status_code: int = 200) -> MagicMock:
    """httpx.Response mock을 생성한다."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = status_code
    mock_resp.json.return_value = _make_voyage_response(texts)
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ---------------------------------------------------------------------------
# 1. API 호출 mock 테스트
# ---------------------------------------------------------------------------

class TestApiCallMock:
    """Voyage AI API 호출을 mock한 기본 동작 테스트."""

    @pytest.mark.asyncio
    async def test_embed_calls_voyage_api(self, embedder: AnthropicEmbedder) -> None:
        """embed()가 Voyage AI API를 호출하는지 검증."""
        # Arrange
        texts = ["hello world", "python function"]
        mock_resp = _make_mock_response(texts)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            # Act
            result = await embedder.embed(texts)

        # Assert
        assert len(result) == 2
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert "voyageai.com" in call_kwargs[0][0]

    @pytest.mark.asyncio
    async def test_embed_returns_correct_vector_count(self, embedder: AnthropicEmbedder) -> None:
        """embed()가 입력 텍스트 수만큼 벡터를 반환하는지 검증."""
        # Arrange
        texts = ["text one", "text two", "text three"]
        mock_resp = _make_mock_response(texts)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            # Act
            result = await embedder.embed(texts)

        # Assert: 입력 3개 → 출력 3개
        assert len(result) == 3
        for vec in result:
            assert isinstance(vec, list)
            assert len(vec) == 4  # _make_voyage_response 기본 dim=4

    @pytest.mark.asyncio
    async def test_embed_empty_texts_returns_empty(self, embedder: AnthropicEmbedder) -> None:
        """빈 텍스트 목록으로 embed() 호출 시 빈 리스트를 반환하는지 검증."""
        # Act
        result = await embedder.embed([])

        # Assert
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_sets_correct_api_headers(self, embedder: AnthropicEmbedder) -> None:
        """API 호출 시 Authorization 헤더가 올바르게 설정되는지 검증."""
        # Arrange
        texts = ["test text"]
        mock_resp = _make_mock_response(texts)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            # Act
            await embedder.embed(texts)

        # Assert: Authorization Bearer 헤더 확인
        call_kwargs = mock_client.post.call_args[1]
        headers = call_kwargs.get("headers", {})
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer ")

    @pytest.mark.asyncio
    async def test_embed_voyage_response_order_sorted_by_index(
        self, embedder: AnthropicEmbedder
    ) -> None:
        """Voyage AI 응답의 index 순서로 정렬하여 반환하는지 검증."""
        # Arrange — 응답 순서를 역순으로 반환
        texts = ["first", "second", "third"]
        reversed_response = {
            "data": [
                {"index": 2, "embedding": [3.0, 3.0]},
                {"index": 0, "embedding": [1.0, 1.0]},
                {"index": 1, "embedding": [2.0, 2.0]},
            ]
        }
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = reversed_response
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            # Act
            result = await embedder.embed(texts)

        # Assert: index 0→1→2 순서로 정렬되어야 함
        assert result[0] == [1.0, 1.0]
        assert result[1] == [2.0, 2.0]
        assert result[2] == [3.0, 3.0]

    @pytest.mark.asyncio
    async def test_is_available_true_after_successful_call(
        self, embedder: AnthropicEmbedder
    ) -> None:
        """성공적인 API 호출 후 is_available이 True인지 검증."""
        # Arrange
        texts = ["success test"]
        mock_resp = _make_mock_response(texts)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            # Act
            await embedder.embed(texts)

        # Assert
        assert embedder.is_available is True


# ---------------------------------------------------------------------------
# 2. 배치 분할 로직 테스트
# ---------------------------------------------------------------------------

class TestBatchSplitting:
    """96개 초과 텍스트의 배치 분할 로직 테스트."""

    @pytest.mark.asyncio
    async def test_batch_split_over_96_texts(self, embedder: AnthropicEmbedder) -> None:
        """97개 텍스트가 2번의 API 호출로 분할되는지 검증."""
        # Arrange — 97개 텍스트 (96 + 1)
        texts = [f"unique text number {i}" for i in range(97)]
        call_count = 0

        async def mock_post(url: str, **kwargs: object) -> MagicMock:
            nonlocal call_count
            batch = kwargs["json"]["input"]
            call_count += 1
            resp = MagicMock(spec=httpx.Response)
            resp.json.return_value = _make_voyage_response(batch)
            resp.raise_for_status = MagicMock()
            return resp

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = mock_post
            mock_client_cls.return_value = mock_client

            # Act
            result = await embedder.embed(texts)

        # Assert: 97개 텍스트 → 2번 호출, 97개 결과
        assert call_count == 2
        assert len(result) == 97

    @pytest.mark.asyncio
    async def test_batch_split_exactly_96_texts(self, embedder: AnthropicEmbedder) -> None:
        """정확히 96개 텍스트가 1번의 API 호출로 처리되는지 검증."""
        # Arrange — 정확히 96개
        texts = [f"text {i}" for i in range(96)]
        call_count = 0

        async def mock_post(url: str, **kwargs: object) -> MagicMock:
            nonlocal call_count
            batch = kwargs["json"]["input"]
            call_count += 1
            resp = MagicMock(spec=httpx.Response)
            resp.json.return_value = _make_voyage_response(batch)
            resp.raise_for_status = MagicMock()
            return resp

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = mock_post
            mock_client_cls.return_value = mock_client

            # Act
            result = await embedder.embed(texts)

        # Assert: 96개 → 1번 호출
        assert call_count == 1
        assert len(result) == 96

    @pytest.mark.asyncio
    async def test_batch_split_200_texts(self, embedder: AnthropicEmbedder) -> None:
        """200개 텍스트가 3번(96+96+8)의 API 호출로 분할되는지 검증."""
        # Arrange — 200개 텍스트
        texts = [f"item {i}" for i in range(200)]
        call_count = 0

        async def mock_post(url: str, **kwargs: object) -> MagicMock:
            nonlocal call_count
            batch = kwargs["json"]["input"]
            call_count += 1
            resp = MagicMock(spec=httpx.Response)
            resp.json.return_value = _make_voyage_response(batch)
            resp.raise_for_status = MagicMock()
            return resp

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = mock_post
            mock_client_cls.return_value = mock_client

            # Act
            result = await embedder.embed(texts)

        # Assert: ceil(200/96) = 3번 호출, 200개 결과
        assert call_count == 3
        assert len(result) == 200


# ---------------------------------------------------------------------------
# 3. 캐시 히트/미스 테스트
# ---------------------------------------------------------------------------

class TestCacheHitAndMiss:
    """SHA256 기반 임베딩 캐시 히트/미스 테스트."""

    @pytest.mark.asyncio
    async def test_cache_miss_calls_api(self, embedder: AnthropicEmbedder) -> None:
        """캐시 미스 시 API가 호출되는지 검증."""
        # Arrange
        texts = ["brand new text"]
        mock_resp = _make_mock_response(texts)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            # Act
            await embedder.embed(texts)

        # Assert: API 호출됨
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_api(self, embedder: AnthropicEmbedder) -> None:
        """캐시 히트 시 API 호출을 건너뛰는지 검증."""
        # Arrange — 캐시에 미리 삽입
        text = "cached text content"
        cached_vec = [0.1, 0.2, 0.3]
        embedder._cache[_sha256(text)] = cached_vec

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock()
            mock_client_cls.return_value = mock_client

            # Act
            result = await embedder.embed([text])

        # Assert: API 호출 안 됨, 캐시 값 반환
        mock_client.post.assert_not_called()
        assert result == [cached_vec]

    @pytest.mark.asyncio
    async def test_cache_saved_after_api_call(
        self, embedder: AnthropicEmbedder, tmp_cache: Path
    ) -> None:
        """API 호출 성공 후 캐시가 디스크에 저장되는지 검증."""
        # Arrange
        texts = ["save me to cache"]
        mock_resp = _make_mock_response(texts)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            # Act
            await embedder.embed(texts)

        # Assert: 캐시 파일이 생성되고 내용이 있어야 함
        assert tmp_cache.exists()
        cache_data = json.loads(tmp_cache.read_text(encoding="utf-8"))
        assert isinstance(cache_data, dict)
        assert len(cache_data) == 1

    @pytest.mark.asyncio
    async def test_partial_cache_hit_only_fetches_misses(
        self, embedder: AnthropicEmbedder
    ) -> None:
        """일부 캐시 히트 시 미스 항목만 API를 호출하는지 검증."""
        # Arrange — text_a는 캐시에 있고 text_b는 없음
        text_a = "already cached"
        text_b = "not cached yet"
        cached_vec = [9.9, 8.8]
        embedder._cache[_sha256(text_a)] = cached_vec

        call_count = 0

        async def mock_post(url: str, **kwargs: object) -> MagicMock:
            nonlocal call_count
            batch = kwargs["json"]["input"]
            call_count += 1
            # text_b만 API 호출되어야 함
            assert len(batch) == 1
            assert batch[0] == text_b
            resp = MagicMock(spec=httpx.Response)
            resp.json.return_value = _make_voyage_response(batch)
            resp.raise_for_status = MagicMock()
            return resp

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = mock_post
            mock_client_cls.return_value = mock_client

            # Act
            result = await embedder.embed([text_a, text_b])

        # Assert: 1번만 API 호출, 결과 2개
        assert call_count == 1
        assert len(result) == 2
        assert result[0] == cached_vec  # text_a 캐시 값

    def test_cache_loaded_from_disk_on_init(self, tmp_cache: Path) -> None:
        """초기화 시 디스크 캐시가 로드되는지 검증."""
        # Arrange — 사전에 캐시 파일 생성
        existing_cache = {_sha256("preloaded"): [1.0, 2.0, 3.0]}
        tmp_cache.parent.mkdir(parents=True, exist_ok=True)
        tmp_cache.write_text(json.dumps(existing_cache), encoding="utf-8")

        # Act
        with patch.dict("os.environ", {"VOYAGE_API_KEY": "test-key"}, clear=False):
            embedder = AnthropicEmbedder(cache_path=str(tmp_cache))

        # Assert: 기존 캐시가 로드됨
        assert _sha256("preloaded") in embedder._cache

    def test_corrupted_cache_file_returns_empty_dict(self, tmp_cache: Path) -> None:
        """손상된 캐시 파일이 빈 딕셔너리로 시작되는지 검증."""
        # Arrange — 잘못된 JSON
        tmp_cache.parent.mkdir(parents=True, exist_ok=True)
        tmp_cache.write_text("{ invalid json }", encoding="utf-8")

        # Act
        with patch.dict("os.environ", {"VOYAGE_API_KEY": "test-key"}, clear=False):
            embedder = AnthropicEmbedder(cache_path=str(tmp_cache))

        # Assert: 빈 캐시로 시작
        assert embedder._cache == {}

    def test_non_dict_cache_file_returns_empty_dict(self, tmp_cache: Path) -> None:
        """캐시 파일이 딕셔너리가 아닌 경우(배열 등) 빈 딕셔너리로 시작되는지 검증."""
        # Arrange — 유효한 JSON이지만 dict가 아닌 list
        tmp_cache.parent.mkdir(parents=True, exist_ok=True)
        tmp_cache.write_text("[1, 2, 3]", encoding="utf-8")

        # Act
        with patch.dict("os.environ", {"VOYAGE_API_KEY": "test-key"}, clear=False):
            embedder = AnthropicEmbedder(cache_path=str(tmp_cache))

        # Assert: 빈 캐시로 시작
        assert embedder._cache == {}

    @pytest.mark.asyncio
    async def test_save_cache_oserror_does_not_raise(
        self, embedder: AnthropicEmbedder
    ) -> None:
        """_save_cache에서 OSError 발생 시 예외가 전파되지 않는지 검증."""
        # Arrange
        texts = ["text to embed"]
        mock_resp = _make_mock_response(texts)

        # pathlib.Path.write_text는 인스턴스 patch 불가 → 모듈 레벨 Path 클래스 패치
        with patch("httpx.AsyncClient") as mock_client_cls, \
             patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            # Act — OSError가 전파되면 안 됨
            result = await embedder.embed(texts)

        # Assert: 저장 실패해도 결과는 정상 반환
        assert len(result) == 1


# ---------------------------------------------------------------------------
# 4. 에러 시 graceful degradation 테스트
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    """API 에러 발생 시 graceful degradation 동작 테스트."""

    @pytest.mark.asyncio
    async def test_4xx_error_returns_empty_and_sets_unavailable(
        self, embedder: AnthropicEmbedder
    ) -> None:
        """4xx 클라이언트 오류 시 빈 리스트 반환 + is_available=False 검증."""
        # Arrange — 401 Unauthorized 응답
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 401
        mock_resp.headers = {}
        http_error = httpx.HTTPStatusError("401", request=MagicMock(), response=mock_resp)
        mock_resp.raise_for_status.side_effect = http_error

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            # Act
            result = await embedder.embed(["some text"])

        # Assert
        assert result == []
        assert embedder.is_available is False

    @pytest.mark.asyncio
    async def test_network_error_retries_and_returns_empty(
        self, embedder: AnthropicEmbedder
    ) -> None:
        """네트워크 오류(RequestError) 시 재시도 후 빈 리스트 반환 검증."""
        # Arrange — RequestError를 _MAX_RETRIES 횟수만큼 발생
        network_error = httpx.RequestError("connection failed")

        with patch("httpx.AsyncClient") as mock_client_cls, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=network_error)
            mock_client_cls.return_value = mock_client

            # Act
            result = await embedder.embed(["fail text"])

        # Assert
        assert result == []
        assert embedder.is_available is False

    @pytest.mark.asyncio
    async def test_500_server_error_retries(self, embedder: AnthropicEmbedder) -> None:
        """500 서버 오류 시 재시도 후 최종 실패하면 빈 리스트 반환 검증."""
        # Arrange — 500 응답
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 500
        mock_resp.headers = {}
        http_error = httpx.HTTPStatusError("500", request=MagicMock(), response=mock_resp)
        mock_resp.raise_for_status.side_effect = http_error

        with patch("httpx.AsyncClient") as mock_client_cls, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            # Act
            result = await embedder.embed(["server error text"])

        # Assert
        assert result == []
        assert embedder.is_available is False

    @pytest.mark.asyncio
    async def test_429_rate_limit_uses_retry_after_header(
        self, embedder: AnthropicEmbedder
    ) -> None:
        """429 rate limit 응답 시 Retry-After 헤더를 적용하는지 검증."""
        # Arrange — 처음 2번은 429, 세 번째는 성공
        texts = ["rate limited text"]
        call_count = 0

        async def mock_post(url: str, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                mock_resp = MagicMock(spec=httpx.Response)
                mock_resp.status_code = 429
                mock_resp.headers = {"Retry-After": "0.01"}
                http_error = httpx.HTTPStatusError(
                    "429", request=MagicMock(), response=mock_resp
                )
                mock_resp.raise_for_status.side_effect = http_error
                return mock_resp
            else:
                resp = MagicMock(spec=httpx.Response)
                resp.json.return_value = _make_voyage_response(texts)
                resp.raise_for_status = MagicMock()
                return resp

        with patch("httpx.AsyncClient") as mock_client_cls, \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = mock_post
            mock_client_cls.return_value = mock_client

            # Act
            result = await embedder.embed(texts)

        # Assert: 최종 성공, sleep이 호출됨 (Retry-After 대기)
        assert len(result) == 1
        assert mock_sleep.called

    @pytest.mark.asyncio
    async def test_batch_failure_returns_empty_for_all(
        self, embedder: AnthropicEmbedder
    ) -> None:
        """배치 중 하나라도 실패하면 전체 결과가 빈 리스트인지 검증."""
        # Arrange — 200개 텍스트, 두 번째 배치에서 실패
        texts = [f"text {i}" for i in range(200)]
        call_count = 0

        async def mock_post(url: str, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                # 두 번째 배치 실패 (4xx → 재시도 없음)
                mock_resp = MagicMock(spec=httpx.Response)
                mock_resp.status_code = 403
                mock_resp.headers = {}
                http_error = httpx.HTTPStatusError(
                    "403", request=MagicMock(), response=mock_resp
                )
                mock_resp.raise_for_status.side_effect = http_error
                return mock_resp
            else:
                batch = kwargs["json"]["input"]
                resp = MagicMock(spec=httpx.Response)
                resp.json.return_value = _make_voyage_response(batch)
                resp.raise_for_status = MagicMock()
                return resp

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = mock_post
            mock_client_cls.return_value = mock_client

            # Act
            result = await embedder.embed(texts)

        # Assert
        assert result == []

    @pytest.mark.asyncio
    async def test_api_failure_logs_warning_and_returns_empty(
        self, embedder: AnthropicEmbedder
    ) -> None:
        """API 호출 실패 시 경고 로그를 출력하고 빈 임베딩을 반환하는지 검증.

        KR: graceful degradation 핵심 시나리오 — 빈 리스트 반환 + 로깅 확인
        EN: Core graceful degradation scenario — verify empty list return + warning log
        """
        # Arrange — 네트워크 오류로 모든 재시도 실패
        network_error = httpx.RequestError("connection timeout")

        with patch("httpx.AsyncClient") as mock_client_cls, \
             patch("asyncio.sleep", new_callable=AsyncMock), \
             patch("src.rag.embedder.logger") as mock_logger:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=network_error)
            mock_client_cls.return_value = mock_client

            # Act
            result = await embedder.embed(["failure text"])

        # Assert: 빈 리스트 반환 + error 로그 호출됨
        assert result == []
        assert embedder.is_available is False
        assert embedder.fallback_mode is True
        # 최종 실패 에러 로그 확인
        mock_logger.error.assert_called()
        error_call_args = mock_logger.error.call_args[0][0]
        assert "재시도 후 실패" in error_call_args or "permanently failed" in error_call_args

    @pytest.mark.asyncio
    async def test_4xx_error_logs_warning_and_activates_fallback(
        self, embedder: AnthropicEmbedder
    ) -> None:
        """4xx 에러 시 경고 로그를 출력하고 BM25 폴백 모드로 전환되는지 검증.

        KR: 클라이언트 오류 발생 시 즉시 fallback_mode=True로 전환됨을 확인
        EN: Verify immediate fallback_mode=True transition on client error
        """
        # Arrange — 401 Unauthorized 응답
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 401
        mock_resp.headers = {}
        http_error = httpx.HTTPStatusError("401", request=MagicMock(), response=mock_resp)
        mock_resp.raise_for_status.side_effect = http_error

        with patch("httpx.AsyncClient") as mock_client_cls, \
             patch("src.rag.embedder.logger") as mock_logger:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            # Act
            result = await embedder.embed(["auth error text"])

        # Assert: 빈 리스트 + fallback_mode=True + error 로그
        assert result == []
        assert embedder.is_available is False
        assert embedder.fallback_mode is True
        mock_logger.error.assert_called()
        error_call_args = mock_logger.error.call_args[0][0]
        assert "BM25 폴백" in error_call_args or "BM25 fallback" in error_call_args


# ---------------------------------------------------------------------------
# 5. API 키 없음 (SDK 폴백 모드) 테스트
# ---------------------------------------------------------------------------

class TestNoApiKeyFallback:
    """API 키가 없을 때의 동작 테스트."""

    def test_no_api_key_is_available_false(self, tmp_cache: Path) -> None:
        """API 키 없이 생성된 embedder의 is_available이 False인지 검증."""
        # Arrange & Act
        import os
        env_backup = {}
        for key in ("VOYAGE_API_KEY", "ANTHROPIC_API_KEY"):
            env_backup[key] = os.environ.pop(key, None)

        try:
            embedder = AnthropicEmbedder(cache_path=str(tmp_cache))
            assert embedder.is_available is False
        finally:
            for key, val in env_backup.items():
                if val is not None:
                    os.environ[key] = val

    @pytest.mark.asyncio
    async def test_no_api_key_embed_returns_empty(self, tmp_cache: Path) -> None:
        """API 키 없이 embed() 호출 시 빈 리스트를 반환하는지 검증."""
        # Arrange
        import os
        env_backup = {}
        for key in ("VOYAGE_API_KEY", "ANTHROPIC_API_KEY"):
            env_backup[key] = os.environ.pop(key, None)

        try:
            embedder = AnthropicEmbedder(cache_path=str(tmp_cache))

            # Act
            result = await embedder.embed(["some text"])

            # Assert
            assert result == []
            assert embedder.is_available is False
        finally:
            for key, val in env_backup.items():
                if val is not None:
                    os.environ[key] = val

    def test_anthropic_api_key_also_works(self, tmp_cache: Path) -> None:
        """ANTHROPIC_API_KEY 환경변수로도 인증되는지 검증."""
        # Arrange
        import os
        old_voyage = os.environ.pop("VOYAGE_API_KEY", None)

        try:
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "anthropic-key"}, clear=False):
                embedder = AnthropicEmbedder(cache_path=str(tmp_cache))

            # Assert: ANTHROPIC_API_KEY로도 available
            assert embedder.is_available is True
            assert embedder._api_key == "anthropic-key"
        finally:
            if old_voyage is not None:
                os.environ["VOYAGE_API_KEY"] = old_voyage

    def test_voyage_key_takes_priority_over_anthropic_key(self, tmp_cache: Path) -> None:
        """VOYAGE_API_KEY가 ANTHROPIC_API_KEY보다 우선순위가 높은지 검증."""
        # Arrange & Act
        with patch.dict(
            "os.environ",
            {"VOYAGE_API_KEY": "voyage-key", "ANTHROPIC_API_KEY": "anthropic-key"},
            clear=False,
        ):
            embedder = AnthropicEmbedder(cache_path=str(tmp_cache))

        # Assert: VOYAGE_API_KEY가 선택됨
        assert embedder._api_key == "voyage-key"

    @pytest.mark.asyncio
    async def test_cached_text_returned_even_without_api_key(self, tmp_cache: Path) -> None:
        """캐시에 있는 텍스트는 API 키 없이도 반환되는지 검증."""
        # Arrange — 캐시 파일 사전 생성
        text = "cached without key"
        cached_vec = [5.0, 6.0, 7.0]
        existing_cache = {_sha256(text): cached_vec}
        tmp_cache.parent.mkdir(parents=True, exist_ok=True)
        tmp_cache.write_text(json.dumps(existing_cache), encoding="utf-8")

        import os
        env_backup = {}
        for key in ("VOYAGE_API_KEY", "ANTHROPIC_API_KEY"):
            env_backup[key] = os.environ.pop(key, None)

        try:
            embedder = AnthropicEmbedder(cache_path=str(tmp_cache))

            # Act
            result = await embedder.embed([text])

            # Assert: 캐시 히트 → API 호출 없이 반환
            assert result == [cached_vec]
        finally:
            for key, val in env_backup.items():
                if val is not None:
                    os.environ[key] = val

    def test_no_api_key_sets_fallback_mode_true(self, tmp_cache: Path) -> None:
        """API 키 없을 때 fallback_mode가 True로 설정되는지 검증.

        KR:
            subscription 환경(API 키 없음)에서 자동으로 BM25 폴백 모드가
            활성화되었는지 확인한다. fallback_mode=True는 호출측에서
            벡터 검색 대신 BM25만 사용해야 함을 나타낸다.

        EN:
            Verifies that BM25 fallback mode is automatically activated in
            subscription environments (no API key). fallback_mode=True signals
            to the caller that only BM25 should be used instead of vector search.
        """
        # Arrange
        import os
        env_backup = {}
        for key in ("VOYAGE_API_KEY", "ANTHROPIC_API_KEY"):
            env_backup[key] = os.environ.pop(key, None)

        try:
            # Act
            embedder = AnthropicEmbedder(cache_path=str(tmp_cache))

            # Assert: fallback_mode=True, is_available=False
            assert embedder.fallback_mode is True
            assert embedder.is_available is False
        finally:
            for key, val in env_backup.items():
                if val is not None:
                    os.environ[key] = val

    def test_no_api_key_logs_warning_on_init(self, tmp_cache: Path) -> None:
        """API 키 없이 초기화 시 경고 로그가 출력되는지 검증.

        KR:
            subscription 환경에서 AnthropicEmbedder 생성 시 경고 로그를 통해
            BM25 폴백 모드 전환을 명확히 알리는지 확인한다.

        EN:
            Verifies that a warning log clearly announces the BM25 fallback mode
            transition when AnthropicEmbedder is created in a subscription environment.
        """
        # Arrange
        import os
        env_backup = {}
        for key in ("VOYAGE_API_KEY", "ANTHROPIC_API_KEY"):
            env_backup[key] = os.environ.pop(key, None)

        try:
            with patch("src.rag.embedder.logger") as mock_logger:
                # Act
                AnthropicEmbedder(cache_path=str(tmp_cache))

            # Assert: 초기화 시 warning 로그 호출됨
            mock_logger.warning.assert_called()
            warning_call_args = mock_logger.warning.call_args[0][0]
            # 경고 메시지에 BM25 폴백 관련 내용 포함 확인
            assert "BM25" in warning_call_args
            assert "폴백" in warning_call_args or "fallback" in warning_call_args.lower()
        finally:
            for key, val in env_backup.items():
                if val is not None:
                    os.environ[key] = val

    @pytest.mark.asyncio
    async def test_no_api_key_embed_logs_warning(self, tmp_cache: Path) -> None:
        """API 키 없을 때 embed() 호출 시 경고 로그가 출력되는지 검증.

        KR:
            subscription 폴백 모드에서 embed() 호출 시 API 키 없음 경고를
            로깅하는지 확인한다.

        EN:
            Verifies that embed() logs a warning about missing API key
            when called in subscription fallback mode.
        """
        # Arrange
        import os
        env_backup = {}
        for key in ("VOYAGE_API_KEY", "ANTHROPIC_API_KEY"):
            env_backup[key] = os.environ.pop(key, None)

        try:
            embedder = AnthropicEmbedder(cache_path=str(tmp_cache))

            with patch("src.rag.embedder.logger") as mock_logger:
                # Act
                result = await embedder.embed(["no key text"])

            # Assert: 빈 리스트 반환 + warning 로그 호출됨
            assert result == []
            mock_logger.warning.assert_called()
            warning_call_args = mock_logger.warning.call_args[0][0]
            assert "API 키" in warning_call_args or "API key" in warning_call_args.lower()
        finally:
            for key, val in env_backup.items():
                if val is not None:
                    os.environ[key] = val


# ---------------------------------------------------------------------------
# 헬퍼 함수 단위 테스트
# ---------------------------------------------------------------------------

class TestHelperFunctions:
    """_sha256, _exponential_delay 헬퍼 함수 테스트."""

    def test_sha256_returns_64_char_hex(self) -> None:
        """_sha256이 64자 16진수 문자열을 반환하는지 검증."""
        result = _sha256("hello world")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_sha256_same_input_same_output(self) -> None:
        """동일 입력에 동일한 해시가 반환되는지 검증."""
        assert _sha256("test") == _sha256("test")

    def test_sha256_different_input_different_output(self) -> None:
        """다른 입력에 다른 해시가 반환되는지 검증."""
        assert _sha256("text a") != _sha256("text b")

    def test_exponential_delay_increases(self) -> None:
        """지수 백오프 대기 시간이 시도 횟수에 따라 증가하는지 검증."""
        delay_0 = _exponential_delay(0)
        delay_1 = _exponential_delay(1)
        delay_2 = _exponential_delay(2)
        assert delay_0 < delay_1 < delay_2

    def test_exponential_delay_capped_at_max(self) -> None:
        """지수 백오프가 _MAX_DELAY(30초)를 초과하지 않는지 검증."""
        # 매우 큰 attempt 값
        delay = _exponential_delay(100)
        assert delay <= 30.0

    def test_exponential_delay_base_is_1_second(self) -> None:
        """첫 번째 시도(attempt=0) 대기 시간이 1초인지 검증."""
        assert _exponential_delay(0) == 1.0
