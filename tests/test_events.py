"""EventBus 유닛 테스트."""

import asyncio

import pytest

from src.utils.events import Event, EventBus, EventType


class TestEventBus:
    @pytest.fixture
    def bus(self) -> EventBus:
        return EventBus()

    @pytest.mark.asyncio
    async def test_subscribe_returns_queue(self, bus: EventBus):
        q = bus.subscribe()
        assert isinstance(q, asyncio.Queue)

    @pytest.mark.asyncio
    async def test_publish_delivers_to_subscriber(self, bus: EventBus):
        q = bus.subscribe()
        event = Event(type=EventType.LOG, data={"message": "hello"})
        await bus.publish(event)
        received = await asyncio.wait_for(q.get(), timeout=1.0)
        assert received.type == EventType.LOG
        assert received.data["message"] == "hello"

    @pytest.mark.asyncio
    async def test_publish_delivers_to_multiple_subscribers(self, bus: EventBus):
        q1 = bus.subscribe()
        q2 = bus.subscribe()
        event = Event(type=EventType.PROGRESS, data={"iteration": 5})
        await bus.publish(event)
        r1 = await asyncio.wait_for(q1.get(), timeout=1.0)
        r2 = await asyncio.wait_for(q2.get(), timeout=1.0)
        assert r1.data["iteration"] == 5
        assert r2.data["iteration"] == 5

    @pytest.mark.asyncio
    async def test_put_and_wait_for_answer(self, bus: EventBus):
        await bus.put_answer("사용자 답변")
        answer = await asyncio.wait_for(bus.wait_for_answer(), timeout=1.0)
        assert answer == "사용자 답변"

    @pytest.mark.asyncio
    async def test_has_waiting_answer_false_when_empty(self, bus: EventBus):
        assert bus.has_waiting_answer() is False

    @pytest.mark.asyncio
    async def test_has_waiting_answer_true_after_put(self, bus: EventBus):
        await bus.put_answer("test")
        assert bus.has_waiting_answer() is True

    def test_event_type_values(self):
        assert EventType.LOG == "log"
        assert EventType.PROGRESS == "progress"
        assert EventType.QUESTION == "question"
        assert EventType.SPEC_MESSAGE == "spec_message"
        assert EventType.AGENT_OUTPUT == "agent_output"
        assert EventType.COMPLETED == "completed"

    def test_event_dataclass_defaults(self):
        event = Event(type=EventType.LOG)
        assert event.data == {}

    def test_unsubscribe_removes_queue(self, bus: EventBus):
        q = bus.subscribe()
        assert q in bus._subscriber_queues
        bus.unsubscribe(q)
        assert q not in bus._subscriber_queues

    def test_unsubscribe_nonexistent_queue_is_safe(self, bus: EventBus):
        q: asyncio.Queue = asyncio.Queue()
        bus.unsubscribe(q)  # 없는 큐 제거 → 에러 없음
