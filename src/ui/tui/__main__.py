"""TUI 실행 진입점.

사용법:
    python -m src.ui.tui                        # 현재 디렉토리, 스펙 대화부터
    python -m src.ui.tui /path/to/project       # 지정 경로, 스펙 대화부터
    python -m src.ui.tui /path/to/project spec.md  # 스펙 파일 있으면 바로 개발 시작
"""

import sys

from src.ui.tui.app import run_tui

if __name__ == "__main__":
    project_path = sys.argv[1] if len(sys.argv) > 1 else None
    spec_file = sys.argv[2] if len(sys.argv) > 2 else None
    run_tui(project_path=project_path, spec_file=spec_file)
