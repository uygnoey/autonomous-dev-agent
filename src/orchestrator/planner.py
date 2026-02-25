"""작업 계획 수립기.

Claude API를 사용하여 현재 프로젝트 상태를 분석하고
다음에 수행할 작업을 결정한다.
"""

import anthropic
from anthropic.types import TextBlock

from src.utils.logger import setup_logger
from src.utils.state import ProjectState

logger = setup_logger(__name__)


class Planner:
    """Claude API로 다음 작업을 결정하는 계획 수립기."""

    def __init__(self, model: str = "claude-sonnet-4-6-20260217"):
        self._client = anthropic.Anthropic()
        self._model = model

    async def decide_next_task(self, state: ProjectState) -> str:
        """현재 상태를 기반으로 다음 작업 프롬프트를 생성한다.

        Args:
            state: 현재 프로젝트 상태

        Returns:
            Claude Agent SDK가 실행할 구체적 프롬프트 문자열
        """
        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=PLANNER_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": self._build_context(state),
            }],
        )

        content = response.content[0]
        if not isinstance(content, TextBlock):
            raise ValueError(f"예상치 못한 응답 블록 타입: {type(content)}")
        task_prompt = content.text
        logger.info(f"다음 작업 결정: {task_prompt[:100]}...")
        return task_prompt

    def _build_context(self, state: ProjectState) -> str:
        """Planner에게 전달할 컨텍스트를 구성한다."""
        return f"""
현재 프로젝트 상태:
- 스펙: {state.spec[:500]}...
- 현재 Phase: {state.phase}
- 반복 횟수: {state.iteration}
- 완성도: {state.completion_percent:.1f}%
- 테스트 통과율: {state.test_pass_rate:.1f}%
- 린트 에러: {state.lint_errors}건
- 타입 에러: {state.type_errors}건
- 빌드 성공: {state.build_success}
- 미해결 이슈: {len(state.pending_questions)}건

다음에 수행할 가장 중요한 작업을 구체적 프롬프트로 작성해줘.
Claude Code가 바로 실행할 수 있도록 구체적이어야 한다.

핵심뿐 아니라 전체 기능 100% 완성이 목표다.
빌드 실패나 테스트 실패는 사람에게 물어보지 말고 직접 해결해라.
"""


PLANNER_SYSTEM_PROMPT = """당신은 시니어 테크 리드 겸 프로젝트 매니저입니다.

프로젝트 상태를 분석하고 다음에 수행할 가장 중요한 작업을 결정합니다.
응답은 Claude Code(Agent SDK)가 바로 실행할 수 있는 구체적인 프롬프트입니다.

규칙:
1. 테스트 100% 통과 + 전체 기능 100% 완성이 목표
2. 빌드/테스트 실패는 에이전트가 직접 해결 (사람에게 넘기지 않음)
3. 한 번에 하나의 명확한 작업만 지시
4. .claude/skills/ 의 패턴을 따르도록 명시
5. 항상 테스트 코드 작성을 포함

우선순위:
1. 빌드가 안 되면 → 빌드 수정
2. 테스트가 실패하면 → 테스트 수정 (코드 버그 or 테스트 오류)
3. 린트/타입 에러가 있으면 → 수정
4. 미구현 기능이 있으면 → 구현
5. 모두 통과하면 → 코드 품질 개선

프롬프트만 출력하세요. 설명이나 메타 정보는 불필요합니다.
"""
