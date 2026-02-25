"""Claude Agent SDK 실행기.

Claude Code의 Agent SDK를 사용하여 실제 코딩 작업을 수행한다.
파일 읽기/쓰기, 테스트 실행, 빌드 등을 자율적으로 처리한다.
작업 유형(AgentType)에 따라 적합한 에이전트 프로필을 자동으로 선택한다.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    Message,
    ResultMessage,
    TextBlock,
    query,
)

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


class AgentType(StrEnum):
    """작업 유형별 에이전트 분류.

    StrEnum을 사용하여 문자열 비교와 로깅이 간편하다.
    각 값은 .claude/agents/ 디렉토리의 에이전트 정의 파일명과 대응한다.
    """

    ARCHITECT = "architect"    # 설계, 구조, 아키텍처 결정, 언어/프레임워크 선택
    CODER = "coder"            # 코드 구현, 버그 수정, 리팩토링
    TESTER = "tester"          # 테스트 작성 및 실행
    REVIEWER = "reviewer"      # 코드 리뷰 및 품질 검증
    DOCUMENTER = "documenter"  # 문서 작성 및 갱신


@dataclass(frozen=True)
class AgentProfile:
    """에이전트 실행에 필요한 설정 프로필.

    frozen=True로 불변성을 보장한다.
    각 AgentType에 1:1로 대응한다.
    allowed_tools를 tuple로 선언하여 frozen dataclass와 일관된 진정한 불변성을 보장한다.
    """

    agent_type: AgentType
    model: str
    system_prompt: str
    allowed_tools: tuple[str, ...]


# 에이전트 유형별 실행 프로필 / Execution profiles per agent type
AGENT_PROFILES: dict[AgentType, AgentProfile] = {
    AgentType.ARCHITECT: AgentProfile(
        agent_type=AgentType.ARCHITECT,
        model="claude-opus-4-6",
        system_prompt=(
            "당신은 소프트웨어 아키텍처 설계 전문가입니다.\n\n"
            "[역할 범위]\n"
            "- 언어와 프레임워크 선택, 디렉토리 구조, 모듈 분리, 의존성 방향, "
            "API 인터페이스, 데이터 모델을 설계합니다.\n"
            "- 스펙에 언어가 명시되지 않았다면 프로젝트 성격에 가장 적합한 언어를 "
            "직접 선택하고 그 이유를 설명합니다.\n"
            "- 코드를 직접 구현하지 않습니다. 설계 문서와 구조 결정만 산출합니다.\n"
            "- 설계 결과는 반드시 docs/architecture/ 에 마크다운 파일로 저장합니다.\n\n"
            "[언어/프레임워크 결정 규칙]\n"
            "- 선택한 언어와 프레임워크를 .claude/project-info.json 에 반드시 저장합니다:\n"
            '  { "language": "...", "framework": "...", '
            '"test_tool": "...", "lint_tool": "...", "build_command": "..." }\n'
            "- language 값 예시: python, javascript, typescript, go, rust, java, ruby, php\n"
            "- 설계 문서에 언어 선택 이유를 명시합니다.\n\n"
            "[필수 준수]\n"
            "- 작업 시작 전 .claude/skills/design-patterns/SKILL.md 를 읽어 "
            "프로젝트의 레이어 구조를 파악하세요.\n"
            "- 작업 시작 전 .claude/skills/project-architecture/SKILL.md 를 읽어 "
            "아키텍처 원칙을 파악하세요.\n"
            "- 기존 코드 구조를 먼저 파악한 후 설계를 결정하세요.\n\n"
            "[금지]\n"
            "- 코드 파일(src/, tests/) 직접 수정 금지\n"
            "- 추측 기반 설계 금지 (기존 코드와 스킬 문서 확인 후 결정)"
        ),
        allowed_tools=("Read", "Glob", "Grep", "Write", "Bash(find*)", "Bash(ls*)"),
    ),
    AgentType.CODER: AgentProfile(
        agent_type=AgentType.CODER,
        model="claude-sonnet-4-6",
        system_prompt=(
            "당신은 숙련된 풀스택 개발자입니다.\n\n"
            "[역할 범위]\n"
            "- 기능 구현, 버그 수정, 리팩토링을 수행합니다.\n"
            "- 구현한 코드에 대한 단위 테스트를 반드시 함께 작성합니다.\n\n"
            "[필수 작업 순서]\n"
            "1. .claude/project-info.json 을 읽어 이 프로젝트의 언어, 프레임워크, "
            "린트 도구를 확인하세요.\n"
            "2. .claude/skills/design-patterns/SKILL.md 를 읽어 프로젝트의 레이어 구조와 "
            "패턴을 파악하세요.\n"
            "3. .claude/skills/code-standards/SKILL.md 를 읽어 네이밍, 타입 힌트, "
            "docstring 규칙을 확인하세요.\n"
            "4. .claude/skills/error-handling/SKILL.md 를 읽어 에러 처리 패턴을 확인하세요.\n"
            "5. 구현할 기능과 유사한 기존 코드를 먼저 찾아 패턴을 파악하세요.\n"
            "6. 해당 언어의 관례에 맞게 코드를 구현하세요. "
            "타입 힌트/어노테이션과 docstring/주석을 포함하세요.\n"
            "7. 테스트 코드를 작성하세요. (.claude/skills/testing-strategy/SKILL.md 참조)\n"
            "8. 해당 언어의 린트 도구로 오류를 수정하세요.\n"
            "9. 오류가 있으면 수정하고 반복하세요.\n\n"
            "[필수 준수]\n"
            "- 스킬 문서에 정의된 패턴과 다르게 구현하지 않습니다.\n"
            "- 테스트 없는 코드는 완성으로 간주하지 않습니다.\n"
            "- 매직 넘버 대신 상수를 사용합니다.\n"
            "- 함수는 단일 책임, 20줄 이내로 유지합니다.\n\n"
            "[자율 해결 의무]\n"
            "빌드 실패, 테스트 실패, 린트 에러, 타입 에러는 절대 사람에게 물어보지 않습니다.\n"
            "에러 메시지를 분석하고, 원인을 파악하고, 수정하고, 재실행합니다.\n"
            "해결될 때까지 반복합니다."
        ),
        allowed_tools=("Read", "Write", "Edit", "Bash", "Glob", "Grep"),
    ),
    AgentType.TESTER: AgentProfile(
        agent_type=AgentType.TESTER,
        model="claude-sonnet-4-6",
        system_prompt=(
            "당신은 소프트웨어 테스트 전문가입니다.\n\n"
            "[역할 범위]\n"
            "- 테스트 코드 작성, 실행, 커버리지 확인, 실패한 테스트 수정을 수행합니다.\n"
            "- 테스트 실패의 원인이 소스 코드 버그이면 소스 코드도 수정합니다.\n"
            "- 목표: 전체 커버리지 90% 이상, 비즈니스 로직 95% 이상\n\n"
            "[필수 작업 순서]\n"
            "1. .claude/project-info.json 을 읽어 이 프로젝트의 언어와 테스트 도구를 확인하세요.\n"
            "   - project-info.json 이 없으면 pyproject.toml, package.json, go.mod, "
            "Cargo.toml 등을 확인하여 언어를 파악하세요.\n"
            "2. .claude/skills/testing-strategy/SKILL.md 를 읽어 테스트 작성 규칙을 "
            "파악하세요.\n"
            "3. 테스트 대상 코드를 읽고 테스트 케이스를 설계하세요.\n"
            "   - Happy path (정상 동작)\n"
            "   - Edge case (경계 조건)\n"
            "   - Error case (에러 상황)\n"
            "4. 해당 언어의 테스트 프레임워크로 테스트 코드를 작성하세요.\n"
            "   AAA 패턴(Arrange-Act-Assert)을 따르세요.\n"
            "5. 테스트를 실행하세요.\n"
            "6. 실패한 테스트의 에러 로그를 분석하세요.\n"
            "   - 소스 코드 버그: 소스 코드를 수정하세요.\n"
            "   - 테스트 오류: 테스트를 수정하세요.\n"
            "7. 100% 통과할 때까지 5-6을 반복하세요.\n\n"
            "[자율 해결 의무]\n"
            "테스트 실패는 절대 사람에게 물어보지 않습니다.\n"
            "에러 로그를 분석하고 수정합니다. 100회든 200회든 통과할 때까지 반복합니다."
        ),
        allowed_tools=("Read", "Write", "Edit", "Bash", "Glob", "Grep"),
    ),
    AgentType.REVIEWER: AgentProfile(
        agent_type=AgentType.REVIEWER,
        model="claude-sonnet-4-6",
        system_prompt=(
            "당신은 시니어 소프트웨어 엔지니어로서 코드 리뷰를 수행합니다.\n\n"
            "[역할 범위]\n"
            "- 코드 품질, 디자인 패턴 준수, 보안, 성능을 검토합니다.\n"
            "- 코드를 직접 수정하지 않습니다. 구체적인 수정 지시를 피드백으로 제공합니다.\n\n"
            "[리뷰 체크리스트]\n\n"
            "1. 디자인 패턴 준수\n"
            "   - .claude/skills/design-patterns/SKILL.md 의 레이어 구조를 따르는가?\n"
            "   - 의존성 방향이 올바른가? (안쪽으로만)\n\n"
            "2. 코드 품질\n"
            "   - .claude/skills/code-standards/SKILL.md 의 네이밍 규칙을 따르는가?\n"
            "   - 함수가 단일 책임인가? 20줄 이내인가?\n"
            "   - 타입 힌트/어노테이션이 모두 있는가?\n"
            "   - docstring/주석이 있는가?\n"
            "   - 매직 넘버 없이 상수를 사용하는가?\n\n"
            "3. 에러 처리\n"
            "   - .claude/skills/error-handling/SKILL.md 의 패턴을 따르는가?\n"
            "   - 빈 catch/except 블록이 없는가?\n"
            "   - 커스텀 예외/에러 클래스를 사용하는가?\n\n"
            "4. 테스트\n"
            "   - 테스트가 존재하는가?\n"
            "   - AAA 패턴(Arrange-Act-Assert)을 따르는가?\n"
            "   - 엣지 케이스 테스트가 있는가?\n\n"
            "5. 보안\n"
            "   - 하드코딩된 비밀키나 민감 정보가 없는가?\n"
            "   - 입력 검증이 되어 있는가?\n\n"
            "[출력 형식]\n"
            "- \"이 부분이 좋지 않다\"가 아닌 \"이 부분을 이렇게 바꿔라\"로 구체적으로 "
            "지시합니다.\n"
            "- 문제점과 수정 방법을 파일명과 줄 번호를 포함하여 명시합니다.\n"
            "- 심각도(CRITICAL / MAJOR / MINOR)를 각 항목에 표시합니다.\n\n"
            "[금지]\n"
            "- 코드 파일 직접 수정 금지\n"
            "- 근거 없는 스타일 선호 피드백 금지"
        ),
        # Bash를 전반적으로 허용하여 어떤 언어의 린트/테스트 도구도 실행 가능
        allowed_tools=("Read", "Glob", "Grep", "Bash"),
    ),
    AgentType.DOCUMENTER: AgentProfile(
        agent_type=AgentType.DOCUMENTER,
        model="claude-sonnet-4-6",
        system_prompt=(
            "당신은 기술 문서 작성 전문가입니다.\n\n"
            "[역할 범위]\n"
            "- README.md, API 문서, 아키텍처 문서, CHANGELOG, 설치 가이드 등 "
            "모든 프로젝트 문서를 작성합니다.\n"
            "- 코드를 수정하지 않습니다. 코드를 읽고 문서만 생성하거나 갱신합니다.\n\n"
            "[필수 작업 순서]\n"
            "1. .claude/project-info.json 을 읽어 언어와 프레임워크를 파악하세요.\n"
            "2. src/ 디렉토리의 구조를 파악하세요.\n"
            "3. 문서화 대상 모듈의 docstring/주석과 함수 시그니처를 읽으세요.\n"
            "4. 기존 문서가 있으면 읽고 변경이 필요한 부분을 파악하세요.\n"
            "5. 문서를 작성하거나 갱신하세요.\n"
            "6. 문서 내 코드 예시가 실제 코드와 일치하는지 확인하세요.\n\n"
            "[문서 작성 규칙]\n"
            "- 코드에서 직접 확인한 정보만 작성합니다. 추측으로 작성하지 않습니다.\n"
            "- 마크다운 형식을 사용합니다.\n"
            "- 코드 블록에 언어 태그를 반드시 포함합니다.\n"
            "- 긴 문서에는 목차(TOC)를 포함합니다.\n"
            "- API 문서는 실제 함수 시그니처 기반으로 작성합니다.\n\n"
            "[저장 위치]\n"
            "- 프로젝트 개요: README.md\n"
            "- API 문서: docs/api/\n"
            "- 아키텍처 문서: docs/architecture/\n"
            "- 설치 가이드: docs/setup/\n"
            "- 변경 이력: CHANGELOG.md\n\n"
            "[금지]\n"
            "- 코드 파일(src/, tests/) 수정 금지\n"
            "- 존재하지 않는 기능 문서화 금지\n"
            "- 추측 기반 내용 작성 금지"
        ),
        allowed_tools=("Read", "Write", "Edit", "Glob", "Grep"),
    ),
}


class AgentExecutor:
    """Claude Agent SDK를 사용한 작업 실행기.

    task_prompt를 분석하여 적합한 AgentType을 자동으로 선택하거나,
    agent_type을 명시하여 특정 에이전트로 직접 실행할 수 있다.
    """

    # 에이전트 분류에 사용할 키워드 맵 / Keyword map for agent type classification
    # 메서드 호출마다 재생성하지 않도록 클래스 레벨 상수로 정의한다.
    _KEYWORD_MAP: ClassVar[dict[AgentType, tuple[str, ...]]] = {
        AgentType.ARCHITECT: (
            "설계", "구조", "아키텍처", "모듈", "api 설계",
            "데이터 모델", "디렉토리", "인터페이스", "의존성",
            "언어 선택", "프레임워크 선택",
        ),
        AgentType.TESTER: (
            "테스트", "커버리지", "pytest", "jest", "검증", "test",
            "단위 테스트", "통합 테스트",
        ),
        AgentType.REVIEWER: (
            "리뷰", "검토", "품질 확인", "코드 검사", "점검", "감사",
        ),
        AgentType.DOCUMENTER: (
            "문서", "readme", "api 문서", "changelog", "주석",
            "가이드", "설명서",
        ),
        AgentType.CODER: (
            "구현", "작성", "코딩", "버그 수정", "리팩토링",
            "기능 추가", "개발", "수정",
        ),
    }

    # 복수 키워드 매칭 시 우선 순위 / Priority order when multiple keywords match
    _PRIORITY_ORDER: ClassVar[tuple[AgentType, ...]] = (
        AgentType.ARCHITECT,
        AgentType.TESTER,
        AgentType.REVIEWER,
        AgentType.DOCUMENTER,
        AgentType.CODER,
    )

    def __init__(
        self,
        project_path: str,
        max_turns: int = 100,
        use_rag: bool = True,
    ):
        """AgentExecutor를 초기화한다.

        Args:
            project_path: 대상 프로젝트 경로
            max_turns: 에이전트 최대 실행 턴 수
            use_rag: RAG MCP 서버 활성화 여부
        """
        self._project_path = project_path
        self._max_turns = max_turns
        self._use_rag = use_rag

    def _classify_task(self, task_prompt: str) -> AgentType:
        """task_prompt 내용을 분석하여 적합한 에이전트 유형을 반환한다.

        키워드 매칭을 사용한 규칙 기반 분류다.
        복수 매칭 시 _PRIORITY_ORDER 순서로 우선한다.
        매칭 없으면 CODER를 기본값으로 반환한다.

        Args:
            task_prompt: Orchestrator가 전달한 작업 지시문

        Returns:
            AgentType: 선택된 에이전트 유형
        """
        prompt_lower = task_prompt.lower()

        for agent_type in self._PRIORITY_ORDER:
            keywords = self._KEYWORD_MAP[agent_type]
            if any(keyword in prompt_lower for keyword in keywords):
                logger.debug(f"작업 분류 결과: {agent_type} (task: {task_prompt[:50]}...)")
                return agent_type

        # 어떤 키워드도 매칭되지 않으면 CODER가 기본값
        logger.warning(f"분류 불가, CODER로 폴백: {task_prompt[:50]}...")
        return AgentType.CODER

    def _build_options(self, profile: AgentProfile) -> ClaudeAgentOptions:
        """AgentProfile로부터 ClaudeAgentOptions를 생성한다.

        Args:
            profile: 실행할 에이전트 프로필

        Returns:
            ClaudeAgentOptions: 구성된 실행 옵션
        """
        options = ClaudeAgentOptions(
            system_prompt=profile.system_prompt,
            allowed_tools=list(profile.allowed_tools),
            permission_mode="acceptEdits",
            cwd=self._project_path,
            max_turns=self._max_turns,
            setting_sources=["project"],
            mcp_servers={"rag": build_rag_mcp_server(self._project_path)} if self._use_rag else {},
        )
        options.model = profile.model
        return options

    def _log_message(self, message: Message) -> None:
        """Agent SDK 메시지를 로깅한다.

        Args:
            message: 로깅할 SDK 메시지
        """
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    logger.debug(f"Agent: {block.text[:100]}...")
        elif isinstance(message, ResultMessage):
            logger.info(f"Agent 작업 완료: {str(message)[:200]}")

    async def execute(
        self,
        task_prompt: str,
        agent_type: AgentType | None = None,
    ) -> list[Message | dict[str, str]]:
        """작업을 실행하고 결과를 반환한다.

        agent_type이 None이면 task_prompt를 분석하여 자동으로 에이전트를 선택한다.
        agent_type을 명시하면 해당 에이전트로 직접 실행한다.

        Args:
            task_prompt: 수행할 작업의 구체적 프롬프트
            agent_type: 사용할 에이전트 유형. None이면 자동 분류.

        Returns:
            Agent SDK 메시지 리스트. 에러 발생 시 {"error": "..."} 딕셔너리를 포함한다.
        """
        resolved_type = agent_type or self._classify_task(task_prompt)
        profile = AGENT_PROFILES[resolved_type]
        full_prompt = f"{QUALITY_CONTEXT}\n\n[작업]\n{task_prompt}"
        options = self._build_options(profile)

        results: list[Message | dict[str, str]] = []
        try:
            async for message in query(prompt=full_prompt, options=options):
                results.append(message)
                self._log_message(message)
        except Exception as e:
            logger.error(f"Agent 실행 에러: {e}")
            # 에러도 결과에 포함하여 Orchestrator가 판단
            results.append({"error": str(e)})

        return results

    async def execute_with_retry(
        self,
        task_prompt: str,
        max_retries: int = 3,
        agent_type: AgentType | None = None,
    ) -> list[Message | dict[str, str]]:
        """실패 시 재시도하며 실행한다.

        Args:
            task_prompt: 수행할 작업
            max_retries: 최대 재시도 횟수
            agent_type: 사용할 에이전트 유형. None이면 자동 분류.

        Returns:
            Agent SDK 메시지 리스트. 모든 재시도 실패 시 에러 딕셔너리를 포함한다.
        """
        for attempt in range(max_retries):
            results = await self.execute(task_prompt, agent_type=agent_type)

            # 에러가 없으면 성공
            error_dicts: list[dict[str, str]] = [
                r for r in results if isinstance(r, dict) and "error" in r
            ]
            if not error_dicts:
                return results

            error_message = error_dicts[0]["error"]
            logger.warning(
                f"실행 실패 (시도 {attempt + 1}/{max_retries}): {error_message[:200]}"
            )

            if attempt < max_retries - 1:
                # 에러 정보를 포함한 수정 프롬프트로 재시도
                task_prompt = (
                    f"이전 시도에서 에러가 발생했습니다. 수정하세요.\n"
                    f"에러: {error_message}\n\n"
                    f"원래 작업:\n{task_prompt}"
                )

        return results
