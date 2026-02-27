"""Verifier 테스트."""

from unittest.mock import MagicMock, patch

import pytest
from claude_agent_sdk import AssistantMessage, TextBlock

from src.agents.verifier import Verifier
from tests.conftest import make_assistant_message as make_assistant_message_with_text, make_mock_query


class TestVerifier:
    def setup_method(self):
        self.verifier = Verifier(project_path="/tmp/test")

    @pytest.mark.asyncio
    async def test_verify_all_parses_json_result(self):
        json_response = """
검증 완료.

```json
{
    "tests_total": 10,
    "tests_passed": 10,
    "tests_failed": 0,
    "lint_errors": 0,
    "type_errors": 0,
    "build_success": true,
    "issues": []
}
```
"""
        mock_msg = make_assistant_message_with_text(json_response)
        with patch("src.agents.verifier.query", new=make_mock_query(mock_msg)):
            result = await self.verifier.verify_all()

        assert result["tests_total"] == 10
        assert result["tests_passed"] == 10
        assert result["lint_errors"] == 0
        assert result["build_success"] is True

    @pytest.mark.asyncio
    async def test_verify_all_returns_default_when_no_json(self):
        mock_msg = make_assistant_message_with_text("검증 실행 중...")
        with patch("src.agents.verifier.query", new=make_mock_query(mock_msg)):
            result = await self.verifier.verify_all()

        assert result["tests_total"] == 0
        assert result["tests_passed"] == 0
        assert result["build_success"] is False

    @pytest.mark.asyncio
    async def test_verify_all_returns_default_on_empty_messages(self):
        async def empty_query(*args, **kwargs):
            return
            yield

        with patch("src.agents.verifier.query", new=empty_query):
            result = await self.verifier.verify_all()

        assert result["tests_total"] == 0
        assert result["lint_errors"] == 0

    def test_parse_results_extracts_json_block(self):
        json_text = """
결과 보고:
```json
{"tests_total": 5, "tests_passed": 4, "tests_failed": 1,
 "lint_errors": 2, "type_errors": 0, "build_success": false, "issues": ["fail"]}
```
"""
        mock_block = MagicMock(spec=TextBlock)
        mock_block.text = json_text
        mock_msg = MagicMock(spec=AssistantMessage)
        mock_msg.content = [mock_block]

        result = self.verifier._parse_results([mock_msg])

        assert result["tests_total"] == 5
        assert result["tests_passed"] == 4
        assert result["lint_errors"] == 2
        assert result["build_success"] is False

    def test_parse_results_handles_invalid_json(self):
        mock_block = MagicMock(spec=TextBlock)
        mock_block.text = "```json\n{invalid json}\n```"
        mock_msg = MagicMock(spec=AssistantMessage)
        mock_msg.content = [mock_block]

        result = self.verifier._parse_results([mock_msg])

        # 기본값 반환
        assert result["tests_total"] == 0
        assert result["build_success"] is False

    def test_load_project_info_reads_valid_file(self, tmp_path):
        """유효한 project-info.json 파일을 읽어 dict를 반환한다. (lines 31-33)"""
        info_dir = tmp_path / ".claude"
        info_dir.mkdir()
        (info_dir / "project-info.json").write_text('{"language": "python", "framework": "pytest"}')

        verifier = Verifier(project_path=str(tmp_path))
        result = verifier._load_project_info()

        assert result == {"language": "python", "framework": "pytest"}

    def test_load_project_info_handles_invalid_json(self, tmp_path):
        """project-info.json이 유효하지 않은 JSON이면 빈 dict를 반환한다. (lines 34-35)"""
        info_dir = tmp_path / ".claude"
        info_dir.mkdir()
        (info_dir / "project-info.json").write_text("invalid json content")

        verifier = Verifier(project_path=str(tmp_path))
        result = verifier._load_project_info()

        assert result == {}

    @pytest.mark.asyncio
    async def test_verify_all_uses_language_hint_when_language_set(self, tmp_path):
        """project-info.json에 language가 있으면 언어 힌트 분기가 실행된다. (line 61)"""
        info_dir = tmp_path / ".claude"
        info_dir.mkdir()
        (info_dir / "project-info.json").write_text('{"language": "python", "test_tool": "pytest"}')

        verifier = Verifier(project_path=str(tmp_path))
        json_response = (
            "```json\n"
            '{"tests_total": 3, "tests_passed": 3, "tests_failed": 0, '
            '"lint_errors": 0, "type_errors": 0, "build_success": true, "issues": []}\n'
            "```"
        )
        mock_msg = make_assistant_message_with_text(json_response)
        with patch("src.agents.verifier.query", new=make_mock_query(mock_msg)):
            result = await verifier.verify_all()

        assert result["tests_total"] == 3
        assert result["build_success"] is True

    def test_parse_results_merges_with_defaults(self):
        """파싱된 값이 기본값과 병합된다."""
        mock_block = MagicMock(spec=TextBlock)
        mock_block.text = '```json\n{"tests_total": 3, "tests_passed": 3}\n```'
        mock_msg = MagicMock(spec=AssistantMessage)
        mock_msg.content = [mock_block]

        result = self.verifier._parse_results([mock_msg])

        assert result["tests_total"] == 3
        assert result["tests_passed"] == 3
        # 기본값이 채워져야 함
        assert "lint_errors" in result
        assert "build_success" in result
