"""이슈 분류기.

Claude API 또는 Claude Code 세션을 사용하여 이슈를 크리티컬/비크리티컬로 분류한다.

크리티컬 (즉시 사람에게):
- 스펙 모호, 외부 연동 정보 필요, 스펙 간 모순, 보안 결정

크리티컬이 아닌 것 (에이전트가 해결):
- 빌드 실패, 테스트 실패, 린트 에러, 타입 에러, 의존성 충돌, 런타임 에러
"""

import json
from enum import StrEnum

from src.utils.claude_client import call_claude_for_text
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class IssueLevel(StrEnum):
    CRITICAL = "critical"
    NON_CRITICAL = "non_critical"


class IssueClassifier:
    """Claude로 이슈를 분류하는 분류기."""

    def __init__(self, model: str = "claude-sonnet-4-6-20260217"):
        self._model = model

    async def classify(self, verification: dict) -> list[dict]:
        """검증 결과에서 이슈를 추출하고 분류한다.

        Args:
            verification: Verifier의 검증 결과 dict

        Returns:
            [{"description": str, "level": IssueLevel, "suggestion": str?}]
        """
        # 기술적 이슈는 분류 없이 바로 비크리티컬
        # (에이전트가 스스로 해결해야 하므로 목록에 넣지도 않음)
        if self._is_purely_technical(verification):
            return []

        # 비기술적 이슈가 있을 수 있는 경우만 Claude로 분류
        issues_text = verification.get("issues", [])
        if not issues_text:
            return []

        response_text = await call_claude_for_text(
            system=CLASSIFIER_SYSTEM_PROMPT,
            user=f"검증 결과의 이슈 목록:\n{issues_text}",
            model=self._model,
        )
        return self._parse_response(response_text)

    def _is_purely_technical(self, verification: dict) -> bool:
        """순수 기술적 이슈(에이전트가 해결 가능)만 있는지 확인."""
        issues = verification.get("issues", [])
        if not issues:
            return True

        # 키워드 기반 빠른 필터링
        technical_keywords = [
            "build", "빌드", "compile", "컴파일",
            "test", "테스트", "assert", "fail",
            "lint", "린트", "ruff", "eslint",
            "type", "타입", "mypy", "typescript",
            "import", "module", "dependency", "의존성",
            "syntax", "구문", "runtime", "런타임",
            "error", "에러", "exception", "예외",
        ]

        for issue in issues:
            issue_lower = str(issue).lower()
            if not any(kw in issue_lower for kw in technical_keywords):
                # 기술적 키워드가 없는 이슈 → 분류가 필요할 수 있음
                return False

        return True

    def _parse_response(self, text: str) -> list[dict]:
        """Claude 응답을 파싱한다."""
        try:
            # JSON 블록 추출
            if "```json" in text:
                json_str = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                json_str = text.split("```")[1].split("```")[0]
            else:
                json_str = text

            parsed = json.loads(json_str.strip())
            if isinstance(parsed, list):
                return parsed
            return []
        except (json.JSONDecodeError, IndexError):
            logger.warning(f"이슈 분류 응답 파싱 실패: {text[:200]}")
            return []


CLASSIFIER_SYSTEM_PROMPT = """이슈를 critical 또는 non_critical로 분류하세요.

CRITICAL (즉시 사람에게 질문해야 하는 것):
- 스펙이 모호하여 구현 방향을 결정할 수 없는 경우
- 외부 서비스 연동 정보(API 키, 엔드포인트 등)가 필요한 경우
- 스펙 간 모순이 발견된 경우
- 보안 관련 아키텍처 결정이 필요한 경우

절대로 CRITICAL이 아닌 것:
- 빌드 실패 → 에이전트가 직접 수정
- 테스트 실패 → 에이전트가 직접 수정
- 린트 에러 → 에이전트가 직접 수정
- 타입 에러 → 에이전트가 직접 수정
- 의존성 충돌 → 에이전트가 직접 해결
- 런타임 에러 → 에이전트가 직접 디버깅
- 성능 이슈 → 에이전트가 직접 최적화

NON_CRITICAL (완성 후 모아서 전달):
- UI 세부 조정, 색상, 간격
- 네이밍 선택
- 성능 최적화 방향
- 부가 기능 구현 방식

JSON 배열로만 응답하세요:
```json
[{"description": "설명", "level": "critical", "suggestion": "제안"}]
```

기술적 이슈(빌드/테스트/린트/타입)는 목록에 포함하지 마세요.
"""
