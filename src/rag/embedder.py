"""Anthropic Voyage AI 임베딩 모듈 / Anthropic Voyage AI Embedding Module.

KR:
    Voyage AI API(voyage-3 모델)를 호출하여 텍스트를 벡터로 변환한다.
    SHA256 기반 파일 캐시로 중복 API 호출을 방지하고,
    API 실패 시 graceful degradation으로 빈 벡터를 반환한다.

    폴백 모드 (Fallback Mode):
        VOYAGE_API_KEY / ANTHROPIC_API_KEY 가 모두 없거나 API 호출이 영구 실패하면
        자동으로 BM25-only 폴백 모드로 전환된다.
        - claude-agent-sdk 및 anthropic SDK 모두 임베딩 API를 제공하지 않으므로
          subscription 환경에서는 벡터 검색 대신 BM25 텍스트 검색만 사용된다.
        - is_available=False + fallback_mode=True 상태가 된다.
        - 이후 embed() 호출은 즉시 빈 리스트를 반환한다.

EN:
    Calls Voyage AI API (voyage-3 model) to convert text into embedding vectors.
    Prevents duplicate API calls using SHA256-based file cache.
    Returns empty vectors via graceful degradation on API failure.

    Fallback Mode:
        Automatically switches to BM25-only fallback mode when both
        VOYAGE_API_KEY / ANTHROPIC_API_KEY are absent or API calls permanently fail.
        - Neither claude-agent-sdk nor anthropic SDK provides an embeddings API,
          so subscription environments use BM25 text search instead of vector search.
        - State becomes is_available=False + fallback_mode=True.
        - Subsequent embed() calls immediately return an empty list.

EmbeddingProtocol(src/core/interfaces.py)을 구조적으로 준수한다.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import TypedDict

import httpx

from src.utils.logger import setup_logger


class _EmbeddingItem(TypedDict):
    """Voyage AI API 응답의 개별 임베딩 항목."""

    index: int
    embedding: list[float]

logger = setup_logger(__name__)

# Voyage AI API 엔드포인트 및 모델
_VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings"
_EMBEDDING_MODEL = "voyage-3"

# 재시도 설정
_MAX_RETRIES = 3
_BASE_DELAY = 1.0   # 초
_MAX_DELAY = 30.0   # 초

# 기본 캐시 경로
_DEFAULT_CACHE_PATH = ".rag_cache/embeddings.json"


class AnthropicEmbedder:
    """Voyage AI API 기반 텍스트 임베딩기 / Voyage AI API-based text embedder.

    KR:
        EmbeddingProtocol(src/core/interfaces.py)을 구조적으로 준수한다.

        - VOYAGE_API_KEY 또는 ANTHROPIC_API_KEY 환경변수로 인증
        - SHA256 기반 디스크 캐시로 중복 API 호출 방지
        - 최대 BATCH_SIZE(96)개씩 배치 분할 호출
        - API 실패 시 3회 지수 백오프 재시도 후 is_available=False
        - API 키 없음 또는 영구 실패 시 fallback_mode=True로 BM25 전용 전환

    EN:
        Structurally complies with EmbeddingProtocol(src/core/interfaces.py).

        - Authenticates via VOYAGE_API_KEY or ANTHROPIC_API_KEY env variable
        - Prevents duplicate API calls with SHA256-based disk cache
        - Splits into batches of BATCH_SIZE(96) for API calls
        - After 3 exponential backoff retries on failure, sets is_available=False
        - Sets fallback_mode=True for BM25-only mode when no key or permanent failure
    """

    BATCH_SIZE: int = 96  # Voyage AI API 배치 제한 / Voyage AI API batch limit

    def __init__(self, cache_path: str = _DEFAULT_CACHE_PATH) -> None:
        """임베딩기 초기화 / Initialize embedder.

        KR:
            API 키 존재 여부에 따라 벡터 검색 모드 또는 BM25 폴백 모드로 시작한다.
            API 키가 없으면 즉시 fallback_mode=True로 설정되며 경고를 로깅한다.

        EN:
            Starts in vector search mode or BM25 fallback mode based on API key presence.
            If no API key found, immediately sets fallback_mode=True and logs a warning.

        Args:
            cache_path: 임베딩 캐시 JSON 파일 경로 / Path to the embedding cache JSON file
        """
        self._api_key: str | None = (
            os.environ.get("VOYAGE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        )
        self._cache_path = Path(cache_path)
        self._cache: dict[str, list[float]] = self._load_cache()
        # API 키 존재 + 최근 호출 성공 여부 / Whether API key exists and last call succeeded
        self._available: bool = self._api_key is not None
        # BM25 폴백 모드 여부 / Whether in BM25-only fallback mode
        self._fallback_mode: bool = self._api_key is None

        if self._fallback_mode:
            logger.warning(
                "AnthropicEmbedder: VOYAGE_API_KEY와 ANTHROPIC_API_KEY 모두 없음. "
                "벡터 검색 비활성화, BM25 폴백 모드로 전환. "
                "/ Neither VOYAGE_API_KEY nor ANTHROPIC_API_KEY found. "
                "Vector search disabled, switching to BM25 fallback mode."
            )

    @property
    def is_available(self) -> bool:
        """임베딩 가능 여부 (API 키 존재 + 최근 호출 성공) / Whether embedding is available."""
        return self._available

    @property
    def fallback_mode(self) -> bool:
        """BM25 전용 폴백 모드 여부 / Whether in BM25-only fallback mode.

        KR:
            True이면 embed()는 항상 빈 리스트를 반환하고,
            호출측은 BM25만으로 검색을 수행해야 한다.

        EN:
            If True, embed() always returns an empty list,
            and the caller should rely solely on BM25 for search.
        """
        return self._fallback_mode

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """텍스트 목록을 임베딩 벡터로 변환한다.

        EmbeddingProtocol 구현 메서드.
        캐시 히트는 즉시 반환하고, 미스는 API를 배치 호출한다.
        전체 실패 시 is_available=False로 설정하고 빈 리스트 반환.

        Args:
            texts: 임베딩할 텍스트 목록

        Returns:
            각 텍스트에 대응하는 float 벡터 목록.
            실패 시 빈 리스트([]) 반환.
        """
        if not texts:
            return []

        # 1. 캐시 히트/미스 분류
        hashes = [_sha256(t) for t in texts]
        results: list[list[float] | None] = [
            self._cache.get(h) for h in hashes
        ]

        # 2. 캐시 미스 텍스트만 API 호출
        miss_indices = [i for i, r in enumerate(results) if r is None]
        if miss_indices:
            miss_texts = [texts[i] for i in miss_indices]
            fetched = await self._fetch_embeddings(miss_texts)

            if fetched is None:
                # API 실패 → 캐시 히트 부분만 반환 (graceful degradation)
                return [r for r in results if r is not None]

            # 결과 병합 및 캐시 저장
            for local_idx, global_idx in enumerate(miss_indices):
                vec = fetched[local_idx]
                results[global_idx] = vec
                self._cache[hashes[global_idx]] = vec

            self._save_cache()

        # 3. None이 남은 경우는 없어야 하지만 타입 안전을 위해 필터
        return [r for r in results if r is not None]

    # ------------------------------------------------------------------
    # 내부 API 호출 로직
    # ------------------------------------------------------------------

    async def _fetch_embeddings(self, texts: list[str]) -> list[list[float]] | None:
        """캐시 미스 텍스트를 배치 분할하여 API를 호출한다.

        배치 크기(BATCH_SIZE)를 초과하면 자동으로 분할하여 순차 호출한다.

        Args:
            texts: API 호출이 필요한 텍스트 목록

        Returns:
            임베딩 벡터 목록. 전체 실패 시 None.
        """
        all_embeddings: list[list[float]] = []

        for batch_start in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[batch_start : batch_start + self.BATCH_SIZE]
            batch_result = await self._call_api_with_retry(batch)

            if batch_result is None:
                return None

            all_embeddings.extend(batch_result)

        return all_embeddings

    async def _call_api_with_retry(self, texts: list[str]) -> list[list[float]] | None:
        """지수 백오프로 최대 _MAX_RETRIES회 API를 재시도한다.

        rate limit(429) 응답 시 Retry-After 헤더를 우선 적용한다.
        최종 실패 시 is_available=False로 설정하고 None을 반환한다.

        Args:
            texts: 임베딩할 텍스트 배치

        Returns:
            임베딩 벡터 목록. 실패 시 None.
        """
        if not self._api_key:
            # 폴백 모드 상태 보장 / Ensure fallback mode state is set
            logger.warning(
                "AnthropicEmbedder: API 키 없음. 임베딩 불가. BM25 폴백 모드. "
                "/ No API key found. Embedding unavailable. BM25 fallback mode."
            )
            self._available = False
            self._fallback_mode = True
            return None

        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                result = await self._call_voyage_api(texts)
                # 성공 시 available 복구
                self._available = True
                return result

            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code

                if status == 429:
                    # Rate limit: Retry-After 헤더 우선 적용
                    retry_after = exc.response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else _exponential_delay(attempt)
                    logger.warning(
                        f"AnthropicEmbedder: rate limit (429), "
                        f"{delay:.1f}s 대기 후 재시도 ({attempt + 1}/{_MAX_RETRIES})"
                    )
                    await asyncio.sleep(delay)

                elif status >= 500:
                    delay = _exponential_delay(attempt)
                    logger.warning(
                        f"AnthropicEmbedder: 서버 오류 ({status}), "
                        f"{delay:.1f}s 대기 후 재시도 ({attempt + 1}/{_MAX_RETRIES})"
                    )
                    await asyncio.sleep(delay)

                else:
                    # 4xx 클라이언트 오류는 재시도 불필요 / 4xx client errors do not need retry
                    logger.error(
                        f"AnthropicEmbedder: 클라이언트 오류 ({status}), 재시도 중단. "
                        f"BM25 폴백 모드로 전환. "
                        f"/ Client error ({status}), stopping retry. "
                        f"Switching to BM25 fallback mode."
                    )
                    self._available = False
                    self._fallback_mode = True
                    return None

                last_error = exc

            except (httpx.RequestError, OSError) as exc:
                delay = _exponential_delay(attempt)
                logger.warning(
                    f"AnthropicEmbedder: 네트워크 오류 ({exc}), "
                    f"{delay:.1f}s 대기 후 재시도 ({attempt + 1}/{_MAX_RETRIES})"
                )
                await asyncio.sleep(delay)
                last_error = exc

        logger.error(
            f"AnthropicEmbedder: {_MAX_RETRIES}회 재시도 후 실패. "
            f"벡터 검색 비활성화, BM25 폴백 모드로 전환. 마지막 오류: {last_error} "
            f"/ After {_MAX_RETRIES} retries, permanently failed. "
            f"Vector search disabled, switching to BM25 fallback mode. Last error: {last_error}"
        )
        self._available = False
        self._fallback_mode = True
        return None

    async def _call_voyage_api(self, texts: list[str]) -> list[list[float]]:
        """Voyage AI API를 단일 호출한다.

        Args:
            texts: 임베딩할 텍스트 배치

        Returns:
            임베딩 벡터 목록 (texts와 동일한 순서)

        Raises:
            httpx.HTTPStatusError: HTTP 오류 응답
            httpx.RequestError: 네트워크 오류
        """
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": _EMBEDDING_MODEL, "input": texts}

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(_VOYAGE_API_URL, headers=headers, json=payload)
            response.raise_for_status()

        data = response.json()
        # Voyage AI 응답 구조: {"data": [{"embedding": [...], "index": 0}, ...]}
        embeddings_data: list[_EmbeddingItem] = data["data"]
        # index 기준 정렬하여 순서 보장
        sorted_data = sorted(embeddings_data, key=lambda x: x["index"])
        return [item["embedding"] for item in sorted_data]

    # ------------------------------------------------------------------
    # 캐시 관리
    # ------------------------------------------------------------------

    def _load_cache(self) -> dict[str, list[float]]:
        """디스크 캐시를 로드한다. 파일이 없거나 손상되면 빈 딕셔너리를 반환한다."""
        if not self._cache_path.exists():
            return {}
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
            return {}
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"AnthropicEmbedder: 캐시 로드 실패 ({exc}), 새 캐시로 시작.")
            return {}

    def _save_cache(self) -> None:
        """캐시를 디스크에 저장한다. 디렉토리가 없으면 생성한다."""
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=None),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning(f"AnthropicEmbedder: 캐시 저장 실패 ({exc})")


# ------------------------------------------------------------------
# 모듈 레벨 헬퍼
# ------------------------------------------------------------------


def _sha256(text: str) -> str:
    """텍스트의 SHA256 해시를 16진수 문자열로 반환한다.

    캐시 키로 사용하여 동일 텍스트의 중복 API 호출을 방지한다.

    Args:
        text: 해시할 텍스트

    Returns:
        64자 16진수 SHA256 다이제스트
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _exponential_delay(attempt: int) -> float:
    """지수 백오프 대기 시간을 계산한다.

    Args:
        attempt: 현재 시도 횟수 (0-indexed)

    Returns:
        대기 시간(초), _MAX_DELAY 이하로 제한
    """
    return float(min(_BASE_DELAY * (2**attempt), _MAX_DELAY))
