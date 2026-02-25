"""IssueClassifier 유닛 테스트."""

from unittest.mock import AsyncMock, patch

import pytest

from src.orchestrator.issue_classifier import IssueClassifier, IssueLevel


class TestIssueClassifier:
    @pytest.fixture
    def classifier(self):
        return IssueClassifier()

    async def test_purely_technical_issues_return_empty(self, classifier: IssueClassifier):
        """순수 기술적 이슈는 빈 목록을 반환해야 한다."""
        verification = {
            "tests_total": 10,
            "tests_passed": 8,
            "tests_failed": 2,
            "issues": ["test failed: assert 1 == 2", "lint error in module"],
        }
        result = await classifier.classify(verification)
        assert result == []

    async def test_no_issues_returns_empty(self, classifier: IssueClassifier):
        """이슈가 없으면 빈 목록을 반환한다."""
        verification = {"issues": []}
        result = await classifier.classify(verification)
        assert result == []

    def test_is_purely_technical_with_build_keywords(self, classifier: IssueClassifier):
        verification = {"issues": ["build failed", "compile error"]}
        assert classifier._is_purely_technical(verification) is True

    def test_is_purely_technical_with_test_keywords(self, classifier: IssueClassifier):
        verification = {"issues": ["test assertion failed", "pytest error"]}
        assert classifier._is_purely_technical(verification) is True

    def test_is_purely_technical_with_type_keywords(self, classifier: IssueClassifier):
        verification = {"issues": ["mypy type error", "typescript compile error"]}
        assert classifier._is_purely_technical(verification) is True

    def test_not_purely_technical_with_ambiguous_issue(self, classifier: IssueClassifier):
        verification = {"issues": ["authentication flow unclear", "spec ambiguity"]}
        assert classifier._is_purely_technical(verification) is False

    def test_is_purely_technical_with_empty_issues(self, classifier: IssueClassifier):
        verification = {"issues": []}
        assert classifier._is_purely_technical(verification) is True

    def test_parse_response_valid_json(self, classifier: IssueClassifier):
        text = (
            '```json\n[{"description": "spec unclear", "level": "critical",'
            ' "suggestion": "ask user"}]\n```'
        )
        result = classifier._parse_response(text)
        assert len(result) == 1
        assert result[0]["level"] == "critical"

    def test_parse_response_invalid_json_returns_empty(self, classifier: IssueClassifier):
        result = classifier._parse_response("not a json response")
        assert result == []

    def test_issue_level_enum_values(self):
        assert IssueLevel.CRITICAL == "critical"
        assert IssueLevel.NON_CRITICAL == "non_critical"

    # ─── classify() with mocked call_claude_for_text ──────────────────

    @pytest.mark.asyncio
    async def test_classify_calls_claude_when_non_technical_issue(
        self, classifier: IssueClassifier
    ):
        """비기술적 이슈가 있으면 Claude API를 호출한다."""
        verification = {
            "issues": ["authentication flow unclear"],
        }
        expected_response = '[{"description": "auth spec 모호", "level": "critical"}]'
        with patch(
            "src.orchestrator.issue_classifier.call_claude_for_text",
            new=AsyncMock(return_value=expected_response),
        ) as mock_call:
            result = await classifier.classify(verification)

        mock_call.assert_called_once()
        assert len(result) == 1
        assert result[0]["level"] == "critical"

    @pytest.mark.asyncio
    async def test_classify_returns_parsed_issues(self, classifier: IssueClassifier):
        """Claude 응답을 올바르게 파싱하여 반환한다."""
        verification = {
            "issues": ["spec is ambiguous for login page"],
        }
        json_response = (
            '```json\n[{"description": "login spec 모호", "level": "critical",'
            ' "suggestion": "소셜만인지 이메일도인지 확인"}]\n```'
        )
        with patch(
            "src.orchestrator.issue_classifier.call_claude_for_text",
            new=AsyncMock(return_value=json_response),
        ):
            result = await classifier.classify(verification)

        assert len(result) == 1
        assert result[0]["description"] == "login spec 모호"
        assert result[0]["level"] == "critical"

    @pytest.mark.asyncio
    async def test_classify_returns_empty_on_invalid_response(self, classifier: IssueClassifier):
        """파싱 실패 시 빈 목록을 반환한다."""
        verification = {"issues": ["spec ambiguous"]}
        with patch(
            "src.orchestrator.issue_classifier.call_claude_for_text",
            new=AsyncMock(return_value="invalid response"),
        ):
            result = await classifier.classify(verification)

        assert result == []

    def test_parse_response_with_plain_json(self, classifier: IssueClassifier):
        """마크다운 블록 없는 순수 JSON도 파싱한다."""
        text = '[{"description": "issue", "level": "non_critical"}]'
        result = classifier._parse_response(text)
        assert len(result) == 1

    def test_parse_response_returns_empty_for_non_list(self, classifier: IssueClassifier):
        """응답이 리스트가 아니면 빈 목록을 반환한다."""
        text = '{"description": "issue"}'  # dict, not list
        result = classifier._parse_response(text)
        assert result == []
