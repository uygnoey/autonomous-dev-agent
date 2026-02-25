"""ProjectState 유닛 테스트."""

from pathlib import Path

from src.utils.state import PhaseType, ProjectState


class TestProjectState:
    def test_default_values(self):
        state = ProjectState(spec="test spec")
        assert state.phase == PhaseType.INIT
        assert state.iteration == 0
        assert state.completion_percent == 0.0
        assert state.test_pass_rate == 0.0
        assert state.lint_errors == 0
        assert state.type_errors == 0
        assert state.build_success is False
        assert state.pending_questions == []

    def test_save_and_load(self, tmp_path: Path):
        state = ProjectState(spec="test spec")
        state.phase = PhaseType.BUILD
        state.iteration = 5
        state.test_pass_rate = 80.0
        state.lint_errors = 2

        save_path = tmp_path / "state.json"
        state.save(save_path)

        assert save_path.exists()

        loaded = ProjectState.load(save_path)
        assert loaded.spec == "test spec"
        assert loaded.phase == PhaseType.BUILD
        assert loaded.iteration == 5
        assert loaded.test_pass_rate == 80.0
        assert loaded.lint_errors == 2

    def test_save_creates_parent_directory(self, tmp_path: Path):
        state = ProjectState(spec="test spec")
        save_path = tmp_path / "nested" / "dir" / "state.json"
        state.save(save_path)
        assert save_path.exists()

    def test_load_or_create_creates_new_when_no_file(self, tmp_path: Path):
        path = tmp_path / "state.json"
        state = ProjectState.load_or_create(path, spec="new spec")
        assert state.spec == "new spec"
        assert state.phase == PhaseType.INIT

    def test_load_or_create_restores_existing_state(self, tmp_path: Path):
        original = ProjectState(spec="existing spec")
        original.iteration = 10
        original.phase = PhaseType.VERIFY
        save_path = tmp_path / "state.json"
        original.save(save_path)

        restored = ProjectState.load_or_create(save_path, spec="existing spec")
        assert restored.iteration == 10
        assert restored.phase == PhaseType.VERIFY

    def test_load_or_create_ignores_mismatched_spec(self, tmp_path: Path):
        original = ProjectState(spec="old spec")
        original.iteration = 99
        save_path = tmp_path / "state.json"
        original.save(save_path)

        new_state = ProjectState.load_or_create(save_path, spec="completely different spec")
        # 스펙이 다르면 새 상태를 반환
        assert new_state.iteration == 0

    def test_save_sets_last_updated_at(self, tmp_path: Path):
        state = ProjectState(spec="test spec")
        assert state.last_updated_at == ""
        state.save(tmp_path / "state.json")
        assert state.last_updated_at != ""

    def test_phase_type_enum_values(self):
        assert PhaseType.INIT == "init"
        assert PhaseType.SETUP == "setup"
        assert PhaseType.BUILD == "build"
        assert PhaseType.VERIFY == "verify"
        assert PhaseType.DOCUMENT == "document"
        assert PhaseType.COMPLETE == "complete"
