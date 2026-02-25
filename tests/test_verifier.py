"""Verifier 테스트."""

from unittest.mock import MagicMock, patch

import pytest
from claude_agent_sdk import AssistantMessage, TextBlock

from src.agents.verifier import Verifier


def make_mock_query(*messages):
    """테스트용 비동기 제너레이터 팩토리."""
    async def _mock(*args, **kwargs):
        for msg in messages:
            yield msg
    return _mock


def make_assistant_message_with_text(text: str) -> AssistantMessage:
    """텍스트가 있는 AssistantMessage mock."""
    mock_block = MagicMock(spec=TextBlock)
    mock_block.text = text
    mock_msg = MagicMock(spec=AssistantMessage)
    mock_msg.content = [mock_block]
    return mock_msg


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
