"""스펙 빌더.

개발 시작 전 Claude와 대화하여 프로젝트 스펙을 확정한다.
대화를 통해 모호한 요구사항을 구체화하고,
확정된 스펙을 spec.md 파일로 저장한다.
"""

from pathlib import Path

from src.utils.claude_client import call_claude_for_text
from src.utils.events import Event, EventBus, EventType
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

SPEC_SYSTEM_PROMPT = """당신은 숙련된 소프트웨어 아키텍트입니다.
사용자의 프로젝트 아이디어를 듣고, 구체적인 개발 스펙으로 만들어주는 역할을 합니다.

대화 규칙:
1. 처음엔 사용자 아이디어를 듣고 핵심을 파악합니다
2. 모호한 부분은 구체적 질문으로 명확히 합니다
3. 불필요한 복잡성은 피하고 MVP에 집중합니다
4. 스펙이 충분히 구체화되면 "SPEC_CONFIRMED" 태그와 함께 최종 스펙을 출력합니다

최종 스펙 형식 (SPEC_CONFIRMED 태그 후 마크다운으로):
- 프로젝트 개요
- 기술 스택
- 핵심 기능 목록 (우선순위 포함)
- API/데이터 모델 개요
- 제약사항 및 비기능 요구사항"""


class SpecBuilder:
    """Claude와 대화하며 프로젝트 스펙을 확정한다."""

    def __init__(
        self,
        event_bus: EventBus,
        model: str = "claude-sonnet-4-6-20260217",
    ) -> None:
        self._event_bus = event_bus
        self._model = model
        self._conversation: list[dict[str, str]] = []

    async def build(self, project_path: Path) -> str:
        """대화를 통해 스펙을 확정하고 spec.md로 저장한다.

        Args:
            project_path: 프로젝트 루트 경로

        Returns:
            확정된 스펙 문자열
        """
        # 기존 spec.md가 있으면 그대로 사용
        spec_path = project_path / "spec.md"
        if spec_path.exists():
            spec = spec_path.read_text()
            await self._event_bus.publish(Event(
                type=EventType.SPEC_MESSAGE,
                data={"role": "assistant", "content": f"기존 스펙을 발견했습니다.\n\n{spec}"},
            ))
            return spec

        # 첫 인사
        greeting = (
            "안녕하세요! 어떤 프로젝트를 만들고 싶으신가요? "
            "아이디어를 자유롭게 말씀해 주세요."
        )
        await self._event_bus.publish(Event(
            type=EventType.SPEC_MESSAGE,
            data={"role": "assistant", "content": greeting},
        ))

        # 대화 루프
        while True:
            user_input = await self._event_bus.wait_for_answer()

            if not user_input.strip():
                continue

            self._conversation.append({"role": "user", "content": user_input})

            # Claude에게 응답 요청
            response = await self._ask_claude()
            self._conversation.append({"role": "assistant", "content": response})

            if "SPEC_CONFIRMED" in response:
                spec = self._extract_spec(response)
                spec_path.write_text(spec)
                logger.info(f"스펙 저장: {spec_path}")

                await self._event_bus.publish(Event(
                    type=EventType.SPEC_MESSAGE,
                    data={
                        "role": "assistant",
                        "content": f"✅ 스펙 확정! spec.md에 저장했습니다.\n\n---\n{spec}",
                    },
                ))
                return spec

            await self._event_bus.publish(Event(
                type=EventType.SPEC_MESSAGE,
                data={"role": "assistant", "content": response},
            ))

    async def _ask_claude(self) -> str:
        """현재 대화 이력으로 Claude에게 응답을 요청한다."""
        conversation_text = "\n".join(
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in self._conversation
        )
        user_prompt = f"대화 이력:\n{conversation_text}\n\nASSISTANT:"
        return await call_claude_for_text(
            system=SPEC_SYSTEM_PROMPT,
            user=user_prompt,
            model=self._model,
        )

    def _extract_spec(self, response: str) -> str:
        """SPEC_CONFIRMED 태그 이후 내용을 추출한다."""
        if "SPEC_CONFIRMED" in response:
            parts = response.split("SPEC_CONFIRMED", 1)
            spec = parts[1].strip().lstrip(":").strip()
            return spec
        return response
