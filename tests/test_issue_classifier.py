"""IssueClassifier 유닛 테스트."""

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
        # 기술적 이슈만 있으면 API 호출 없이 빈 목록 반환
        result = await classifier.classify(verification)
        assert result == []

    async def test_no_issues_returns_empty(self, classifier: IssueClassifier):
        """이슈가 없으면 빈 목록을 반환한다."""
        verification = {"issues": []}
        result = await classifier.classify(verification)
        assert result == []

    def test_is_purely_technical_with_build_keywords(self, classifier: IssueClassifier):
        """빌드 관련 키워드가 있으면 순수 기술적으로 판단한다."""
        verification = {"issues": ["build failed", "compile error"]}
        assert classifier._is_purely_technical(verification) is True

    def test_is_purely_technical_with_test_keywords(self, classifier: IssueClassifier):
        """테스트 관련 키워드가 있으면 순수 기술적으로 판단한다."""
        verification = {"issues": ["test assertion failed", "pytest error"]}
        assert classifier._is_purely_technical(verification) is True

    def test_is_purely_technical_with_type_keywords(self, classifier: IssueClassifier):
        """타입 관련 키워드가 있으면 순수 기술적으로 판단한다."""
        verification = {"issues": ["mypy type error", "typescript compile error"]}
        assert classifier._is_purely_technical(verification) is True

    def test_not_purely_technical_with_ambiguous_issue(self, classifier: IssueClassifier):
        """기술적 키워드가 없는 이슈는 비순수 기술적으로 판단한다."""
        verification = {"issues": ["authentication flow unclear", "spec ambiguity"]}
        assert classifier._is_purely_technical(verification) is False

    def test_is_purely_technical_with_empty_issues(self, classifier: IssueClassifier):
        """이슈가 없으면 순수 기술적으로 판단한다."""
        verification = {"issues": []}
        assert classifier._is_purely_technical(verification) is True

    def test_parse_response_valid_json(self, classifier: IssueClassifier):
        """유효한 JSON 응답을 파싱한다."""
        text = '```json\n[{"description": "spec unclear", "level": "critical", "suggestion": "ask user"}]\n```'
        result = classifier._parse_response(text)
        assert len(result) == 1
        assert result[0]["level"] == "critical"

    def test_parse_response_invalid_json_returns_empty(self, classifier: IssueClassifier):
        """유효하지 않은 JSON은 빈 목록을 반환한다."""
        result = classifier._parse_response("not a json response")
        assert result == []

    def test_issue_level_enum_values(self):
        assert IssueLevel.CRITICAL == "critical"
        assert IssueLevel.NON_CRITICAL == "non_critical"
