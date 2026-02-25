"""cli.py 테스트."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.cli import main, cli_main


class TestMain:
    def test_calls_run_tui_with_no_args(self):
        """인수 없이 호출하면 project_path=None, spec_file=None으로 run_tui 실행."""
        with (
            patch("sys.argv", ["adev"]),
            patch("src.ui.tui.app.run_tui") as mock_tui,
        ):
            main()

        mock_tui.assert_called_once_with(project_path=None, spec_file=None)

    def test_calls_run_tui_with_project_path(self):
        """project_path만 전달하면 spec_file=None."""
        with (
            patch("sys.argv", ["adev", "/some/project"]),
            patch("src.ui.tui.app.run_tui") as mock_tui,
        ):
            main()

        mock_tui.assert_called_once_with(project_path="/some/project", spec_file=None)

    def test_calls_run_tui_with_both_args(self):
        """project_path와 spec_file 모두 전달."""
        with (
            patch("sys.argv", ["adev", "/some/project", "spec.md"]),
            patch("src.ui.tui.app.run_tui") as mock_tui,
        ):
            main()

        mock_tui.assert_called_once_with(project_path="/some/project", spec_file="spec.md")

    def test_argv_zero_is_set_to_adev(self):
        """sys.argv[0]이 'adev'로 통일된다."""
        with (
            patch("sys.argv", ["some-other-command"]),
            patch("src.ui.tui.app.run_tui"),
        ):
            main()
            # patch 컨텍스트 안에서 확인 (벗어나면 sys.argv가 복원됨)
            assert sys.argv[0] == "adev"


class TestCliMain:
    def test_exits_when_no_args(self):
        """인수 없이 호출하면 sys.exit(1)."""
        with (
            patch("sys.argv", ["adev"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            cli_main()

        assert exc_info.value.code == 1

    def test_exits_when_file_not_found(self, tmp_path):
        """존재하지 않는 스펙 파일이면 sys.exit(1)."""
        with (
            patch("sys.argv", ["adev", str(tmp_path / "nonexistent.md")]),
            pytest.raises(SystemExit) as exc_info,
        ):
            cli_main()

        assert exc_info.value.code == 1

    def test_runs_orchestrator_with_spec_file(self, tmp_path):
        """유효한 스펙 파일이면 Orchestrator를 생성하고 run()을 실행한다."""
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("테스트 스펙")

        mock_run = AsyncMock()
        with (
            patch("sys.argv", ["adev", str(spec_file)]),
            patch("src.orchestrator.main.AgentExecutor"),
            patch("src.orchestrator.main.Verifier"),
            patch("src.orchestrator.main.AutonomousOrchestrator.run", new=mock_run),
        ):
            cli_main()

        mock_run.assert_called_once()

    def test_uses_cwd_as_project_path_when_one_arg(self, tmp_path):
        """스펙 파일 하나만 전달하면 project_path는 CWD."""
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("스펙")

        captured = {}

        def fake_init(self, project_path, spec, event_bus=None):
            captured["project_path"] = project_path
            captured["spec"] = spec
            # 최소한의 초기화
            from pathlib import Path as P
            from src.utils.config import load_config
            from src.utils.events import EventBus
            from src.utils.state import ProjectState
            self.project_path = P(project_path)
            self.state = ProjectState(spec=spec)
            self._event_bus = event_bus
            config = load_config()
            from src.orchestrator.token_manager import TokenManager
            from src.orchestrator.planner import Planner
            from src.orchestrator.issue_classifier import IssueClassifier
            self.token_manager = TokenManager()
            self.planner = Planner()
            self.classifier = IssueClassifier()
            self._max_iterations = config.max_iterations
            self._completion_criteria = {}

        with (
            patch("sys.argv", ["adev", str(spec_file)]),
            patch("src.orchestrator.main.AgentExecutor"),
            patch("src.orchestrator.main.Verifier"),
            patch("src.orchestrator.main.AutonomousOrchestrator.__init__", fake_init),
            patch("src.orchestrator.main.AutonomousOrchestrator.run", new=AsyncMock()),
            patch("pathlib.Path.cwd", return_value=tmp_path),
        ):
            cli_main()

        assert captured["project_path"] == str(tmp_path)
        assert captured["spec"] == "스펙"
