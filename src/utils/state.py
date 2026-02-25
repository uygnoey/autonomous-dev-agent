"""프로젝트 상태 관리.

프로젝트의 현재 상태를 추적하고, 파일로 저장/복원하여
토큰 한도로 인한 재시작 시에도 이어서 진행할 수 있게 한다.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class PhaseType(StrEnum):
    INIT = "init"
    SETUP = "setup"
    BUILD = "build"
    VERIFY = "verify"
    DOCUMENT = "document"
    COMPLETE = "complete"


@dataclass
class ProjectState:
    """프로젝트 상태."""

    spec: str
    phase: PhaseType = PhaseType.INIT
    iteration: int = 0
    completion_percent: float = 0.0
    test_pass_rate: float = 0.0
    lint_errors: int = 0
    type_errors: int = 0
    build_success: bool = False
    pending_questions: list = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_updated_at: str = ""

    def save(self, path: Path) -> None:
        """상태를 JSON 파일로 저장한다.

        토큰 한도로 중단 후 재개 시 사용.
        """
        self.last_updated_at = datetime.now().isoformat()
        data = asdict(self)
        # Enum을 문자열로 변환
        data["phase"] = self.phase.value

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: Path) -> "ProjectState":
        """저장된 상태를 복원한다.

        Args:
            path: state.json 파일 경로

        Returns:
            복원된 ProjectState

        Raises:
            FileNotFoundError: 파일이 없을 때
        """
        with open(path) as f:
            data = json.load(f)

        data["phase"] = PhaseType(data["phase"])
        return cls(**data)

    @classmethod
    def load_or_create(cls, path: Path, spec: str) -> "ProjectState":
        """저장된 상태가 있으면 복원, 없으면 새로 생성한다.

        토큰 한도로 재시작할 때 이전 상태를 이어받기 위함.
        """
        if path.exists():
            state = cls.load(path)
            # 스펙이 같은지 확인
            if state.spec[:100] == spec[:100]:
                return state
        return cls(spec=spec)
