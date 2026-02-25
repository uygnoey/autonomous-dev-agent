"""설정 로더.

config/default.yaml을 읽어 AppConfig로 반환한다.
파일이 없거나 읽기 실패 시 기본값을 그대로 사용한다.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

# config/default.yaml 의 기본 경로 (이 파일 기준 상대 경로)
_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "default.yaml"


@dataclass(frozen=True)
class AppConfig:
    """설정 값 컨테이너."""

    # Orchestrator 모델
    planning_model: str = "claude-sonnet-4-6"
    classifier_model: str = "claude-sonnet-4-6"

    # Agent 실행 설정
    max_turns_per_task: int = 100
    permission_mode: str = "delegate"  # 완전 자율 실행

    # 토큰 한도 대기 설정
    initial_wait_seconds: int = 60
    max_wait_seconds: int = 300

    # 자율 루프 설정
    max_iterations: int = 500

    # 완성 판단 기준
    test_pass_rate: float = 100.0
    lint_errors: int = 0
    type_errors: int = 0


def load_config(config_path: Path | None = None) -> AppConfig:
    """config/default.yaml을 읽어 AppConfig를 반환한다.

    파일이 없거나 읽기 실패 시 AppConfig 기본값을 사용한다.

    Args:
        config_path: 설정 파일 경로. None이면 config/default.yaml 사용.

    Returns:
        AppConfig 인스턴스
    """
    path = config_path or _DEFAULT_CONFIG_PATH
    if not path.exists():
        return AppConfig()

    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return AppConfig()

    defaults = AppConfig()
    orch = data.get("orchestrator", {})
    agent_cfg = data.get("agent", {})
    token = data.get("token", {})
    loop = data.get("loop", {})
    quality = data.get("quality", {})

    return AppConfig(
        planning_model=orch.get("planning_model", defaults.planning_model),
        classifier_model=orch.get("classifier_model", defaults.classifier_model),
        max_turns_per_task=agent_cfg.get("max_turns_per_task", defaults.max_turns_per_task),
        permission_mode=agent_cfg.get("permission_mode", defaults.permission_mode),
        initial_wait_seconds=token.get("initial_wait_seconds", defaults.initial_wait_seconds),
        max_wait_seconds=token.get("max_wait_seconds", defaults.max_wait_seconds),
        max_iterations=loop.get("max_iterations", defaults.max_iterations),
        test_pass_rate=float(quality.get("test_pass_rate", defaults.test_pass_rate)),
        lint_errors=int(quality.get("lint_errors", defaults.lint_errors)),
        type_errors=int(quality.get("type_errors", defaults.type_errors)),
    )
