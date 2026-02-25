"""Claude 텍스트 쿼리 헬퍼.

ANTHROPIC_API_KEY가 설정되어 있으면 직접 Anthropic API 사용,
없으면 Claude Code 세션(claude init / subscription)을 통해 사용한다.

사용 예:
    response = await call_claude_for_text(
        system="당신은 전문가입니다.",
        user="다음 작업을 계획해줘.",
    )
"""

import os

import anthropic
from anthropic.types import TextBlock as AnthropicTextBlock
from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, query
from claude_agent_sdk import TextBlock as SDKTextBlock

from src.utils.logger import setup_logger

logger = setup_logger(__name__)


async def call_claude_for_text(
    system: str,
    user: str,
    model: str = "claude-sonnet-4-6-20260217",
    max_tokens: int = 4096,
) -> str:
    """Claude에 텍스트 쿼리를 보내고 응답 텍스트를 반환한다.

    ANTHROPIC_API_KEY가 있으면 직접 Anthropic API 사용,
    없으면 Claude Code 세션(claude init / subscription)을 통해 사용한다.

    Args:
        system: 시스템 프롬프트
        user: 사용자 메시지
        model: 사용할 모델 ID
        max_tokens: 최대 출력 토큰 수 (API 모드에서만 사용)

    Returns:
        Claude 응답 텍스트
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        return _call_via_api(system, user, model, max_tokens)
    return await _call_via_sdk(system, user, model)


def _call_via_api(system: str, user: str, model: str, max_tokens: int) -> str:
    """Anthropic API 키로 직접 호출한다."""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    content = response.content[0]
    if not isinstance(content, AnthropicTextBlock):
        raise ValueError(f"예상치 못한 응답 블록 타입: {type(content)}")
    return content.text


async def _call_via_sdk(system: str, user: str, model: str) -> str:
    """Claude Code 세션(subscription)으로 호출한다.

    claude init으로 인증된 세션을 활용하여 API 키 없이도 동작한다.
    """
    options = ClaudeAgentOptions(
        system_prompt=system,
        allowed_tools=[],
        permission_mode="acceptEdits",
        max_turns=1,
    )
    options.model = model

    result_text = ""
    async for message in query(prompt=user, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, SDKTextBlock):
                    result_text += block.text

    if not result_text:
        logger.warning("Claude SDK 응답에서 텍스트를 찾지 못했습니다.")
    return result_text
