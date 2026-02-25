"""AppConfig 및 load_config() 테스트."""

from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

from src.utils.config import AppConfig, load_config


class TestAppConfig:
    def test_default_values(self):
        config = AppConfig()
        assert config.planning_model == "claude-sonnet-4-6"
        assert config.classifier_model == "claude-sonnet-4-6"
        assert config.initial_wait_seconds == 60
        assert config.max_wait_seconds == 300
        assert config.max_iterations == 500
        assert config.test_pass_rate == 100.0
        assert config.lint_errors == 0
        assert config.type_errors == 0

    def test_frozen_immutability(self):
        config = AppConfig()
        with pytest.raises((AttributeError, TypeError)):
            config.planning_model = "other-model"  # type: ignore[misc]


class TestLoadConfig:
    def test_returns_defaults_when_file_missing(self, tmp_path):
        result = load_config(tmp_path / "nonexistent.yaml")
        assert result == AppConfig()

    def test_loads_orchestrator_section(self, tmp_path):
        yaml_content = """
orchestrator:
  planning_model: "claude-opus-4-6"
  classifier_model: "claude-haiku-4-5-20251001"
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml_content)

        result = load_config(config_file)
        assert result.planning_model == "claude-opus-4-6"
        assert result.classifier_model == "claude-haiku-4-5-20251001"

    def test_loads_token_section(self, tmp_path):
        yaml_content = """
token:
  initial_wait_seconds: 30
  max_wait_seconds: 600
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml_content)

        result = load_config(config_file)
        assert result.initial_wait_seconds == 30
        assert result.max_wait_seconds == 600

    def test_loads_loop_section(self, tmp_path):
        yaml_content = """
loop:
  max_iterations: 100
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml_content)

        result = load_config(config_file)
        assert result.max_iterations == 100

    def test_loads_quality_section(self, tmp_path):
        yaml_content = """
quality:
  test_pass_rate: 90
  lint_errors: 5
  type_errors: 2
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml_content)

        result = load_config(config_file)
        assert result.test_pass_rate == 90.0
        assert result.lint_errors == 5
        assert result.type_errors == 2

    def test_partial_override_keeps_defaults(self, tmp_path):
        yaml_content = """
orchestrator:
  planning_model: "claude-opus-4-6"
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml_content)

        result = load_config(config_file)
        assert result.planning_model == "claude-opus-4-6"
        # 나머지는 기본값
        assert result.classifier_model == "claude-sonnet-4-6"
        assert result.max_iterations == 500

    def test_returns_defaults_on_invalid_yaml(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(": invalid: yaml: [")

        result = load_config(config_file)
        assert result == AppConfig()

    def test_loads_default_yaml_when_no_path(self):
        """인수 없이 호출하면 config/default.yaml을 읽는다."""
        result = load_config()
        # default.yaml의 실제 값과 일치하는지 확인
        assert result.planning_model == "claude-sonnet-4-6"
        assert result.max_iterations == 500
