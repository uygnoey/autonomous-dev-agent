"""CLI entry point for autonomous-dev-agent.

간단한 명령어로 에이전트를 실행할 수 있도록 하는 CLI 인터페이스.
`adev` 또는 `autonomous-dev` 명령어로 실행된다.
"""

import sys
from pathlib import Path

# .env 파일 로드 (Agent Teams 환경 변수 포함)
from dotenv import load_dotenv

# 프로젝트 루트의 .env 파일 로드
load_dotenv()


def main() -> None:
    """CLI 메인 함수.

    pyproject.toml의 [project.scripts]에서 호출된다.
    - adev = "src.cli:main"
    - autonomous-dev = "src.cli:main"
    """
    from src.ui.tui.app import run_tui

    # 명령줄 인자를 직접 파싱하여 전달
    sys.argv[0] = "adev"  # 명령어 이름을 adev로 통일
    project_path = sys.argv[1] if len(sys.argv) > 1 else None
    spec_file = sys.argv[2] if len(sys.argv) > 2 else None
    run_tui(project_path=project_path, spec_file=spec_file)


def cli_main() -> None:
    """대체 CLI 진입점 (Orchestrator 직접 실행).

    TUI 없이 Orchestrator만 실행하려는 경우 사용.
    현재는 사용하지 않지만 향후 확장을 위해 유지.
    """
    import asyncio

    from src.orchestrator.main import AutonomousOrchestrator

    if len(sys.argv) < 2:
        print("사용법: adev <spec.md>")
        print("또는:   adev <project-path> <spec.md>")
        sys.exit(1)

    # 스펙 파일 경로
    spec_path = Path(sys.argv[-1])
    if not spec_path.exists():
        print(f"❌ 스펙 파일을 찾을 수 없습니다: {spec_path}")
        sys.exit(1)

    # 프로젝트 경로 (지정하지 않으면 현재 디렉토리)
    project_path = Path(sys.argv[1]) if len(sys.argv) == 3 else Path.cwd()

    # Orchestrator 실행
    async def run() -> None:
        orchestrator = AutonomousOrchestrator(
            project_path=str(project_path),
            spec=spec_path.read_text(encoding="utf-8"),
        )
        await orchestrator.run()

    asyncio.run(run())


if __name__ == "__main__":
    main()
