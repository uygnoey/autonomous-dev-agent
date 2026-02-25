"""이벤트 버스.

Orchestrator와 UI(TUI/Web) 사이의 비동기 통신을 담당한다.
asyncio.Queue 기반으로 여러 구독자를 지원하며,
사용자 입력(답변)은 별도 채널로 처리한다.
"""

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    """이벤트 타입 정의."""

    LOG = "log"                  # 로그 메시지
    PROGRESS = "progress"        # 진행 상황 업데이트
    QUESTION = "question"        # 사용자에게 질문 (크리티컬 이슈)
    SPEC_MESSAGE = "spec_message"  # 스펙 확정 대화 메시지
    AGENT_OUTPUT = "agent_output"  # 에이전트 실행 결과
    COMPLETED = "completed"      # 완성 보고


@dataclass
class Event:
    """이벤트 데이터 클래스."""

    type: EventType
    data: dict[str, Any] = field(default_factory=dict)


class EventBus:
    """asyncio.Queue 기반 이벤트 버스.

    여러 UI 구독자가 동시에 이벤트를 받을 수 있다.
    사용자 답변은 별도 큐로 Orchestrator에 전달된다.
    """

    def __init__(self) -> None:
        self._subscriber_queues: list[asyncio.Queue[Event]] = []
        # 사용자 답변 채널 (사용자 → Orchestrator)
        self._answer_queue: asyncio.Queue[str] = asyncio.Queue()

    def subscribe(self) -> asyncio.Queue[Event]:
        """새 구독자 큐를 생성하고 반환한다.

        Returns:
            이벤트를 받을 asyncio.Queue
        """
        q: asyncio.Queue[Event] = asyncio.Queue()
        self._subscriber_queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Event]) -> None:
        """구독을 해제한다."""
        self._subscriber_queues.discard(q) if hasattr(
            self._subscriber_queues, "discard"
        ) else (self._subscriber_queues.remove(q) if q in self._subscriber_queues else None)

    async def publish(self, event: Event) -> None:
        """모든 구독자에게 이벤트를 발행한다.

        Args:
            event: 발행할 이벤트
        """
        for q in self._subscriber_queues:
            await q.put(event)

    async def wait_for_answer(self) -> str:
        """사용자 답변을 기다린다. Orchestrator가 호출.

        Returns:
            사용자가 입력한 답변 문자열
        """
        return await self._answer_queue.get()

    async def put_answer(self, answer: str) -> None:
        """사용자 답변을 큐에 넣는다. UI가 호출.

        Args:
            answer: 사용자가 입력한 답변
        """
        await self._answer_queue.put(answer)

    def has_waiting_answer(self) -> bool:
        """대기 중인 답변이 있는지 확인한다."""
        return not self._answer_queue.empty()
