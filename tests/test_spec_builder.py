"""SpecBuilder 유닛 테스트."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.orchestrator.spec_builder import SpecBuilder
from src.utils.events import Event, EventBus, EventType


class TestSpecBuilder:
    @pytest.fixture
    def bus(self) -> EventBus:
        return EventBus()

    @pytest.fixture
    def builder(self, bus: EventBus) -> SpecBuilder:
        return SpecBuilder(bus)

    @pytest.mark.asyncio
    async def test_build_returns_existing_spec(
        self, builder: SpecBuilder, bus: EventBus, tmp_path: Path
    ):
        """spec.md가 이미 있으면 대화 없이 해당 내용을 반환한다."""
        spec_content = "# 기존 스펙\n프로젝트 내용"
        (tmp_path / "spec.md").write_text(spec_content)

        # 이벤트 구독
        q = bus.subscribe()
        result = await builder.build(tmp_path)

        assert result == spec_content
        # 이벤트 발행 확인
        event: Event = await asyncio.wait_for(q.get(), timeout=1.0)
        assert event.type == EventType.SPEC_MESSAGE
        assert "기존 스펙" in event.data["content"]

    @pytest.mark.asyncio
    async def test_build_emits_greeting_when_no_spec(
        self, builder: SpecBuilder, bus: EventBus, tmp_path: Path
    ):
        """spec.md가 없으면 첫 인사 메시지를 발행한다."""
        q = bus.subscribe()

        # Claude가 바로 스펙 확정 응답 반환하도록 mock
        confirmed_response = "SPEC_CONFIRMED\n# 프로젝트 스펙\n기능 목록"
        with patch(
            "src.orchestrator.spec_builder.call_claude_for_text",
            new=AsyncMock(return_value=confirmed_response),
        ):
            # 사용자 답변을 미리 큐에 넣기
            await bus.put_answer("투두 앱 만들어줘")
            result = await builder.build(tmp_path)

        # 첫 이벤트: 인사
        greeting_event: Event = await asyncio.wait_for(q.get(), timeout=1.0)
        assert greeting_event.type == EventType.SPEC_MESSAGE
        assert greeting_event.data["role"] == "assistant"
        assert result == "# 프로젝트 스펙\n기능 목록"

    @pytest.mark.asyncio
    async def test_build_saves_spec_file(
        self, builder: SpecBuilder, bus: EventBus, tmp_path: Path
    ):
        """스펙이 확정되면 spec.md 파일로 저장한다."""
        confirmed_response = "SPEC_CONFIRMED\n# 스펙 내용"
        with patch(
            "src.orchestrator.spec_builder.call_claude_for_text",
            new=AsyncMock(return_value=confirmed_response),
        ):
            await bus.put_answer("앱 아이디어")
            await builder.build(tmp_path)

        assert (tmp_path / "spec.md").exists()
        saved = (tmp_path / "spec.md").read_text()
        assert "스펙 내용" in saved

    @pytest.mark.asyncio
    async def test_build_continues_conversation_until_confirmed(
        self, builder: SpecBuilder, bus: EventBus, tmp_path: Path
    ):
        """SPEC_CONFIRMED가 나올 때까지 대화를 반복한다."""
        responses = [
            "어떤 기능이 필요하신가요?",            # 첫 응답: 계속 질문
            "SPEC_CONFIRMED\n# 최종 스펙",        # 두 번째: 확정
        ]
        with patch(
            "src.orchestrator.spec_builder.call_claude_for_text",
            new=AsyncMock(side_effect=responses),
        ):
            await bus.put_answer("투두 앱")
            await bus.put_answer("CRUD 기능")
            result = await builder.build(tmp_path)

        assert result == "# 최종 스펙"

    def test_extract_spec_removes_tag(self, builder: SpecBuilder):
        """SPEC_CONFIRMED 태그 이후 내용만 반환한다."""
        response = "일부 대화...\nSPEC_CONFIRMED\n# 프로젝트 스펙\n내용"
        spec = builder._extract_spec(response)
        assert spec == "# 프로젝트 스펙\n내용"
        assert "SPEC_CONFIRMED" not in spec

    def test_extract_spec_without_tag_returns_full(self, builder: SpecBuilder):
        """태그 없으면 전체 내용을 반환한다."""
        response = "# 그냥 응답"
        spec = builder._extract_spec(response)
        assert spec == "# 그냥 응답"

    @pytest.mark.asyncio
    async def test_build_skips_empty_input_and_waits_again(
        self, builder: SpecBuilder, bus: EventBus, tmp_path: Path
    ):
        """빈 입력은 무시하고 다음 답변을 기다린다. (line 79 - continue branch)"""
        confirmed_response = "SPEC_CONFIRMED\n# 스펙"
        with patch(
            "src.orchestrator.spec_builder.call_claude_for_text",
            new=AsyncMock(return_value=confirmed_response),
        ):
            await bus.put_answer("")          # 빈 입력 → 스킵
            await bus.put_answer("앱 아이디어")  # 실제 입력
            result = await builder.build(tmp_path)

        assert "스펙" in result
