"""Claude Agent SDK 실행기.

Claude Code의 Agent SDK를 사용하여 실제 코딩 작업을 수행한다.
파일 읽기/쓰기, 테스트 실행, 빌드 등을 자율적으로 처리한다.
"""

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query

from src.rag.mcp_server import build_rag_mcp_server
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

# Agent SDK에 주입할 품질 보장 컨텍스트
QUALITY_CONTEXT = """
[필수 준수사항]
1. .claude/skills/design-patterns/SKILL.md 의 패턴을 반드시 따를 것
2. .claude/skills/code-standards/SKILL.md 의 규칙을 반드시 준수할 것
3. .claude/skills/error-handling/SKILL.md 의 에러 처리 패턴을 따를 것
4. 기존 코드의 패턴과 일관성을 유지할 것
5. 새 파일 생성 시 기존 유사 파일의 구조를 먼저 확인할 것
6. 테스트 코드를 반드시 함께 작성할 것
7. 빌드/테스트 실패 시 스스로 분석하고 수정할 것. 사람에게 물어보지 말 것.
"""


class AgentExecutor:
    """Claude Agent SDK를 사용한 작업 실행기."""

    def __init__(
        self,
        project_path: str,
        max_turns: int = 100,
        model: str | None = None,
        use_rag: bool = True,
    ):
        self._project_path = project_path
        self._max_turns = max_turns
        self._model = model
        self._use_rag = use_rag

    async def execute(self, task_prompt: str) -> list:
        """작업을 실행하고 결과를 반환한다.

        Args:
            task_prompt: 수행할 작업의 구체적 프롬프트

        Returns:
            Agent SDK 메시지 리스트
        """
        full_prompt = f"{QUALITY_CONTEXT}\n\n[작업]\n{task_prompt}"

        options = ClaudeAgentOptions(
            system_prompt=(
                "당신은 전문 소프트웨어 개발자입니다. "
                "프로젝트의 .claude/skills/ 에 정의된 디자인 패턴과 코딩 규칙을 "
                "반드시 따르세요. 코드는 읽기 쉽고 일관된 패턴이어야 합니다. "
                "빌드 실패, 테스트 실패, 린트 에러, 타입 에러는 "
                "사람에게 물어보지 말고 직접 분석하고 수정하세요. "
                "해결될 때까지 반복하세요."
            ),
            allowed_tools=[
                "Read", "Write", "Edit", "Bash",
                "Glob", "Grep", "WebSearch", "WebFetch",
            ],
            permission_mode="acceptEdits",
            cwd=self._project_path,
            max_turns=self._max_turns,
            setting_sources=["project"],
            mcp_servers={"rag": build_rag_mcp_server(self._project_path)} if self._use_rag else {},
        )

        if self._model:
            options.model = self._model

        results: list = []
        try:
            async for message in query(prompt=full_prompt, options=options):
                results.append(message)

                # 진행 상황 로깅
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            # 첫 100자만 로깅
                            logger.debug(f"Agent: {block.text[:100]}...")

                elif isinstance(message, ResultMessage):
                    logger.info(f"Agent 작업 완료: {str(message)[:200]}")

        except Exception as e:
            logger.error(f"Agent 실행 에러: {e}")
            # 에러도 결과에 포함하여 Orchestrator가 판단
            results.append({"error": str(e)})

        return results

    async def execute_with_retry(
        self,
        task_prompt: str,
        max_retries: int = 3,
    ) -> list:
        """실패 시 재시도하며 실행한다.

        Args:
            task_prompt: 수행할 작업
            max_retries: 최대 재시도 횟수

        Returns:
            Agent SDK 메시지 리스트
        """
        for attempt in range(max_retries):
            results = await self.execute(task_prompt)

            # 에러가 없으면 성공
            errors = [r for r in results if isinstance(r, dict) and "error" in r]
            if not errors:
                return results

            logger.warning(
                f"실행 실패 (시도 {attempt + 1}/{max_retries}): "
                f"{errors[0]['error'][:200]}"
            )

            if attempt < max_retries - 1:
                # 에러 정보를 포함한 수정 프롬프트로 재시도
                task_prompt = (
                    f"이전 시도에서 에러가 발생했습니다. 수정하세요.\n"
                    f"에러: {errors[0]['error']}\n\n"
                    f"원래 작업:\n{task_prompt}"
                )

        return results
