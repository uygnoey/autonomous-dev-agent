"""pydantic-settings 기반 애플리케이션 설정.

계층형 오버라이드: 환경변수 > .env > config/default.yaml > 기본값
ADEV_ 접두사로 환경변수를 자동 인식한다.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "default.yaml"


class OrchestratorSettings(BaseModel):
    """Orchestrator 모델 설정."""

    planning_model: str = "claude-opus-4-6"
    classifier_model: str = "claude-sonnet-4-6"


class AgentSettings(BaseModel):
    """Agent 실행 설정."""

    max_turns_per_task: int = 100
    permission_mode: str = "bypassPermissions"
    use_rag: bool = True


class RAGSettings(BaseModel):
    """RAG 시스템 설정.

    KR: RAG 파이프라인의 청킹, 검색, 필터링 동작을 제어하는 설정 모델.
    EN: Settings model that controls chunking, retrieval, and filtering behavior of the RAG
    pipeline.
    """

    chunk_strategy: str = "ast"
    bm25_weight: float = 0.6
    vector_weight: float = 0.4
    top_k: int = 10
    use_vector_search: bool = False
    cache_enabled: bool = True

    # .gitignore 외에 추가로 인덱싱에 포함/제외할 glob 패턴 목록
    # KR: 빈 리스트이면 기본 동작(SUPPORTED_EXTENSIONS만 허용)을 따른다.
    # EN: Empty list means default behavior (only SUPPORTED_EXTENSIONS are allowed).
    include_patterns: list[str] = []

    # KR: 이 패턴에 매칭되는 파일은 .gitignore와 무관하게 인덱싱에서 제외한다.
    # EN: Files matching these patterns are excluded from indexing regardless of .gitignore.
    exclude_patterns: list[str] = []


class TokenSettings(BaseModel):
    """토큰 한도 대기 설정."""

    initial_wait_seconds: int = 60
    max_wait_seconds: int = 300


class LoopSettings(BaseModel):
    """자율 루프 설정."""

    max_iterations: int = 500


class QualitySettings(BaseModel):
    """완성 판단 기준."""

    test_pass_rate: float = 100.0
    lint_errors: int = 0
    type_errors: int = 0
    coverage_min: float = 90.0


class AppSettings(BaseSettings):
    """애플리케이션 전체 설정.

    중첩 모델을 포함한 단일 진입점.
    ADEV_ 접두사 환경변수와 .env 파일을 자동 인식한다.
    """

    model_config = SettingsConfigDict(
        env_prefix="ADEV_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    orchestrator: OrchestratorSettings = OrchestratorSettings()
    agent: AgentSettings = AgentSettings()
    rag: RAGSettings = RAGSettings()
    token: TokenSettings = TokenSettings()
    loop: LoopSettings = LoopSettings()
    quality: QualitySettings = QualitySettings()


_settings: AppSettings | None = None


def get_settings() -> AppSettings:
    """싱글톤 AppSettings 인스턴스를 반환한다.

    최초 호출 시 생성하고 이후에는 캐시된 인스턴스를 반환한다.

    Returns:
        AppSettings 인스턴스
    """
    global _settings
    if _settings is None:
        _settings = AppSettings()
    return _settings


def load_config(path: Path | None = None) -> AppSettings:
    """기존 API 호환 래퍼.

    config/default.yaml을 읽어 AppSettings에 오버라이드한 뒤 반환한다.
    파일이 없거나 읽기 실패 시 기본값을 사용한다.

    Args:
        path: 설정 파일 경로. None이면 config/default.yaml 사용.

    Returns:
        AppSettings 인스턴스
    """
    config_path = path or _DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return AppSettings()

    try:
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return AppSettings()

    overrides: dict[str, object] = {}
    _apply_section(overrides, "orchestrator", data.get("orchestrator", {}))
    _apply_section(overrides, "agent", data.get("agent", {}))
    _apply_section(overrides, "rag", data.get("rag", {}))
    _apply_section(overrides, "token", data.get("token", {}))
    _apply_section(overrides, "loop", data.get("loop", {}))
    _apply_section(overrides, "quality", data.get("quality", {}))

    return AppSettings(**overrides)  # type: ignore[arg-type]


def _apply_section(overrides: dict[str, object], key: str, section: dict[str, object]) -> None:
    """YAML 섹션이 비어 있지 않으면 overrides에 추가한다."""
    if section:
        overrides[key] = section
