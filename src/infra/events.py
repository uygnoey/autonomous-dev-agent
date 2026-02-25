"""이벤트 버스 시스템.

채널 분리로 질문/완료 답변이 섞이지 않도록 한다.
Event.to_json()/from_json()으로 향후 웹 UI 대비 직렬화를 지원한다.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    """이벤트 타입 정의."""

    # 기존 6개
    LOG = "log"
    PROGRESS = "progress"
    QUESTION = "question"
    SPEC_MESSAGE = "spec_message"
    AGENT_OUTPUT = "agent_output"
    COMPLETED = "completed"

    # 신규 6개
    AGENT_STARTED = "agent_started"
    AGENT_FINISHED = "agent_finished"
    PIPELINE_STARTED = "pipeline_started"
    PIPELINE_FINISHED = "pipeline_finished"
    RAG_INDEXED = "rag_indexed"
    ERROR = "error"


@dataclass
class Event:
    """이벤트 데이터 클래스."""

    type: EventType
    data: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """이벤트를 JSON 문자열로 직렬화한다.

        Returns:
            JSON 직렬화된 이벤트 문자열
        """
        return json.dumps({"type": str(self.type), "data": self.data}, ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> Event:
        """JSON 문자열에서 이벤트를 역직렬화한다.

        Args:
            text: JSON 직렬화된 이벤트 문자열

        Returns:
            복원된 Event 인스턴스
        """
        obj = json.loads(text)
        return cls(type=EventType(obj["type"]), data=obj.get("data", {}))


class EventChannel:
    """단일 asyncio.Queue 래퍼.

    특정 목적(질문/완료 등)의 문자열 메시지를 독립된 채널로 처리한다.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    async def put(self, answer: str) -> None:
        """채널에 메시지를 넣는다.

        Args:
            answer: 전달할 문자열 메시지
        """
        await self._queue.put(answer)

    async def get(self, timeout: float | None = None) -> str | None:
        """채널에서 메시지를 꺼낸다.

        Args:
            timeout: 대기 제한 시간(초). None이면 무한 대기.

        Returns:
            수신된 메시지 문자열, 타임아웃 시 None
        """
        try:
            if timeout is None:
                return await self._queue.get()
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except TimeoutError:
            return None


class EventBus:
    """asyncio.Queue 기반 이벤트 버스.

    여러 UI 구독자가 동시에 이벤트를 받을 수 있다.
    채널 분리로 질문/완료 답변이 섞이지 않도록 한다.
    """

    _DEFAULT_CHANNELS = ("question", "completion")

    def __init__(self) -> None:
        self._subscriber_queues: list[asyncio.Queue[Event]] = []
        self._channels: dict[str, EventChannel] = {
            name: EventChannel() for name in self._DEFAULT_CHANNELS
        }
        # 하위 호환: 기존 단일 답변 큐
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
        if q in self._subscriber_queues:
            self._subscriber_queues.remove(q)

    async def publish(self, event: Event) -> None:
        """모든 구독자에게 이벤트를 발행한다.

        Args:
            event: 발행할 이벤트
        """
        for q in self._subscriber_queues:
            await q.put(event)

    async def put_answer(self, answer: str, channel: str = "question") -> None:
        """사용자 답변을 지정 채널에 넣는다. UI가 호출.

        Args:
            answer: 사용자가 입력한 답변
            channel: 대상 채널 이름 (기본값: "question")
        """
        await self._answer_queue.put(answer)
        if channel in self._channels:
            await self._channels[channel].put(answer)

    async def wait_for_answer(self, channel: str | None = None) -> str:
        """사용자 답변을 기다린다. Orchestrator가 호출.

        Args:
            channel: 대기할 채널 이름. None이면 기존 단일 큐 사용 (하위 호환).

        Returns:
            사용자가 입력한 답변 문자열
        """
        if channel is not None and channel in self._channels:
            result = await self._channels[channel].get()
            return result if result is not None else ""
        return await self._answer_queue.get()

    def has_waiting_answer(self, channel: str | None = None) -> bool:
        """대기 중인 답변이 있는지 확인한다.

        Args:
            channel: 확인할 채널 이름. None이면 기존 단일 큐 확인 (하위 호환).

        Returns:
            대기 중인 답변 존재 여부
        """
        if channel is not None and channel in self._channels:
            return not self._channels[channel]._queue.empty()
        return not self._answer_queue.empty()

    def get_channel(self, name: str) -> EventChannel:
        """이름으로 채널을 조회하거나 새로 생성한다.

        Args:
            name: 채널 이름

        Returns:
            해당 EventChannel 인스턴스
        """
        if name not in self._channels:
            self._channels[name] = EventChannel()
        return self._channels[name]
