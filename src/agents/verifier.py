"""검증기.

Claude Agent SDK를 사용하여 테스트, 린트, 타입체크, 빌드를 실행하고
결과를 구조화된 형태로 반환한다.
"""

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class Verifier:
    """프로젝트 검증을 수행하는 검증기."""

    def __init__(self, project_path: str):
        self._project_path = project_path

    async def verify_all(self) -> dict:
        """모든 검증을 수행하고 결과를 반환한다.

        Returns:
            {
                "tests_total": int,
                "tests_passed": int,
                "tests_failed": int,
                "lint_errors": int,
                "type_errors": int,
                "build_success": bool,
                "issues": list[str],
            }
        """
        options = ClaudeAgentOptions(
            system_prompt=(
                "검증 에이전트입니다. 테스트, 린트, 타입체크, 빌드를 실행하고 "
                "결과를 정확히 보고하세요. 수정은 하지 마세요."
            ),
            allowed_tools=["Read", "Bash", "Glob", "Grep"],
            permission_mode="acceptEdits",
            cwd=self._project_path,
            max_turns=20,
        )

        verify_prompt = """
다음 검증을 순서대로 수행하고 결과를 JSON으로 정리하세요.
수정은 하지 말고, 현재 상태만 보고하세요.

1. 테스트 실행:
   pytest tests/ -v --tb=short 2>&1 || true

2. 린트 검사:
   ruff check src/ 2>&1 || true

3. 타입 체크:
   mypy src/ --ignore-missing-imports 2>&1 || true

4. 빌드 확인:
   python -c "import src" 2>&1 || true

결과를 반드시 아래 JSON 형식으로 마지막에 출력하세요:
```json
{
    "tests_total": <숫자>,
    "tests_passed": <숫자>,
    "tests_failed": <숫자>,
    "lint_errors": <숫자>,
    "type_errors": <숫자>,
    "build_success": <true/false>,
    "issues": ["이슈1", "이슈2"]
}
```
"""

        results = []
        async for message in query(prompt=verify_prompt, options=options):
            results.append(message)

        return self._parse_results(results)

    def _parse_results(self, messages: list) -> dict:
        """Agent SDK 결과에서 검증 정보를 추출한다."""
        import json

        default = {
            "tests_total": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "lint_errors": 0,
            "type_errors": 0,
            "build_success": False,
            "issues": [],
        }

        # 메시지에서 JSON 블록 찾기
        for msg in messages:
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        text = block.text
                        # JSON 블록 추출 시도
                        if "```json" in text:
                            try:
                                json_str = text.split("```json")[1].split("```")[0]
                                parsed = json.loads(json_str.strip())
                                return {**default, **parsed}
                            except (json.JSONDecodeError, IndexError):
                                continue

        logger.warning("검증 결과 파싱 실패. 기본값 반환.")
        return default
