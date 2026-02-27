"""공통 테스트 픽스처 및 헬퍼 함수.

여러 테스트 파일에서 공통으로 사용되는 헬퍼 함수와 pytest 픽스처를 정의한다.
"""

from unittest.mock import MagicMock

from claude_agent_sdk import AssistantMessage, TextBlock


def make_mock_query(*messages):
    """테스트용 비동기 제너레이터 팩토리.

    Args:
        *messages: yield할 메시지 시퀀스

    Returns:
        async generator function
    """
    async def _mock(*args, **kwargs):
        for msg in messages:
            yield msg
    return _mock


def make_assistant_message(text: str) -> AssistantMessage:
    """AssistantMessage mock 생성.

    Args:
        text: TextBlock에 담을 텍스트

    Returns:
        AssistantMessage spec의 MagicMock
    """
    mock_block = MagicMock(spec=TextBlock)
    mock_block.text = text
    mock_msg = MagicMock(spec=AssistantMessage)
    mock_msg.content = [mock_block]
    return mock_msg
