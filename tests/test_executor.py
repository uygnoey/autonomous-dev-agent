"""AgentExecutor 테스트.

AgentType enum, AgentProfile dataclass, AGENT_PROFILES 상수,
_classify_task 메서드, execute 및 execute_with_retry 메서드를 검증한다.
"""

from dataclasses import FrozenInstanceError
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

from src.agents.executor import (
    AGENT_PROFILES,
    AgentExecutor,
    AgentProfile,
    AgentType,
)


# ---------------------------------------------------------------------------
# 헬퍼 / Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 1. AgentType enum 테스트 / AgentType enum tests
# ---------------------------------------------------------------------------

class TestAgentType:
    """AgentType StrEnum 값 검증."""

    def test_architect_value(self):
        """ARCHITECT 값이 'architect' 문자열인지 확인."""
        assert AgentType.ARCHITECT == "architect"

    def test_coder_value(self):
        """CODER 값이 'coder' 문자열인지 확인."""
        assert AgentType.CODER == "coder"

    def test_tester_value(self):
        """TESTER 값이 'tester' 문자열인지 확인."""
        assert AgentType.TESTER == "tester"

    def test_reviewer_value(self):
        """REVIEWER 값이 'reviewer' 문자열인지 확인."""
        assert AgentType.REVIEWER == "reviewer"

    def test_documenter_value(self):
        """DOCUMENTER 값이 'documenter' 문자열인지 확인."""
        assert AgentType.DOCUMENTER == "documenter"

    def test_str_comparison(self):
        """StrEnum이므로 일반 문자열과 == 비교가 가능한지 확인."""
        assert AgentType.ARCHITECT == "architect"
        assert AgentType.CODER == "coder"
        assert AgentType.TESTER == "tester"
        assert AgentType.REVIEWER == "reviewer"
        assert AgentType.DOCUMENTER == "documenter"

    def test_all_five_members(self):
        """AgentType에 정확히 5개의 멤버가 존재하는지 확인."""
        assert len(AgentType) == 5


# ---------------------------------------------------------------------------
# 2. AgentProfile dataclass 테스트 / AgentProfile dataclass tests
# ---------------------------------------------------------------------------

class TestAgentProfile:
    """AgentProfile frozen dataclass 검증."""

    def setup_method(self):
        """테스트용 AgentProfile 인스턴스 생성."""
        self.profile = AgentProfile(
            agent_type=AgentType.CODER,
            model="claude-sonnet-4-6",
            system_prompt="테스트 시스템 프롬프트",
            allowed_tools=("Read", "Write"),
        )

    def test_field_access(self):
        """필드 값에 올바르게 접근할 수 있는지 확인."""
        assert self.profile.agent_type == AgentType.CODER
        assert self.profile.model == "claude-sonnet-4-6"
        assert self.profile.system_prompt == "테스트 시스템 프롬프트"
        assert self.profile.allowed_tools == ("Read", "Write")

    def test_allowed_tools_is_tuple(self):
        """allowed_tools가 tuple 타입인지 확인 (진정한 불변성 보장)."""
        assert isinstance(self.profile.allowed_tools, tuple)

    def test_allowed_tools_immutable_via_tuple(self):
        """tuple이므로 allowed_tools 내부 변이(append)가 불가능한지 확인."""
        with pytest.raises(AttributeError):
            self.profile.allowed_tools.append("EVIL_TOOL")  # type: ignore[attr-defined]

    def test_frozen_immutability_agent_type(self):
        """frozen=True 이므로 agent_type 수정 시 FrozenInstanceError 발생."""
        with pytest.raises(FrozenInstanceError):
            self.profile.agent_type = AgentType.TESTER

    def test_frozen_immutability_model(self):
        """frozen=True 이므로 model 수정 시 FrozenInstanceError 발생."""
        with pytest.raises(FrozenInstanceError):
            self.profile.model = "other-model"

    def test_frozen_immutability_system_prompt(self):
        """frozen=True 이므로 system_prompt 수정 시 FrozenInstanceError 발생."""
        with pytest.raises(FrozenInstanceError):
            self.profile.system_prompt = "변경된 프롬프트"

    def test_frozen_immutability_allowed_tools(self):
        """frozen=True 이므로 allowed_tools 재할당 시 FrozenInstanceError 발생."""
        with pytest.raises(FrozenInstanceError):
            self.profile.allowed_tools = ("Bash",)


# ---------------------------------------------------------------------------
# 3. AGENT_PROFILES 상수 테스트 / AGENT_PROFILES constant tests
# ---------------------------------------------------------------------------

class TestAgentProfiles:
    """AGENT_PROFILES 딕셔너리 검증."""

    def test_all_agent_types_present(self):
        """5개의 AgentType 모두 키로 존재하는지 확인."""
        for agent_type in AgentType:
            assert agent_type in AGENT_PROFILES, f"{agent_type} 키가 없음"

    def test_architect_uses_opus_model(self):
        """ARCHITECT 프로필의 model이 'claude-opus-4-6'인지 확인."""
        assert AGENT_PROFILES[AgentType.ARCHITECT].model == "claude-opus-4-6"

    def test_coder_uses_sonnet_model(self):
        """CODER 프로필의 model이 'claude-sonnet-4-6'인지 확인."""
        assert AGENT_PROFILES[AgentType.CODER].model == "claude-sonnet-4-6"

    def test_tester_uses_sonnet_model(self):
        """TESTER 프로필의 model이 'claude-sonnet-4-6'인지 확인."""
        assert AGENT_PROFILES[AgentType.TESTER].model == "claude-sonnet-4-6"

    def test_reviewer_uses_sonnet_model(self):
        """REVIEWER 프로필의 model이 'claude-sonnet-4-6'인지 확인."""
        assert AGENT_PROFILES[AgentType.REVIEWER].model == "claude-sonnet-4-6"

    def test_documenter_uses_sonnet_model(self):
        """DOCUMENTER 프로필의 model이 'claude-sonnet-4-6'인지 확인."""
        assert AGENT_PROFILES[AgentType.DOCUMENTER].model == "claude-sonnet-4-6"

    def test_reviewer_allowed_tools_no_write(self):
        """REVIEWER의 allowed_tools에 'Write'가 없는지 확인 (코드 수정 금지)."""
        tools = AGENT_PROFILES[AgentType.REVIEWER].allowed_tools
        assert "Write" not in tools

    def test_reviewer_allowed_tools_no_edit(self):
        """REVIEWER의 allowed_tools에 'Edit'이 없는지 확인 (코드 수정 금지)."""
        tools = AGENT_PROFILES[AgentType.REVIEWER].allowed_tools
        assert "Edit" not in tools

    def test_documenter_allowed_tools_no_bash(self):
        """DOCUMENTER의 allowed_tools에 'Bash'가 없는지 확인 (명령 실행 금지)."""
        tools = AGENT_PROFILES[AgentType.DOCUMENTER].allowed_tools
        assert "Bash" not in tools

    def test_all_profiles_have_system_prompt(self):
        """모든 프로필에 비어 있지 않은 system_prompt가 있는지 확인."""
        for agent_type, profile in AGENT_PROFILES.items():
            assert profile.system_prompt, f"{agent_type}의 system_prompt가 비어 있음"

    def test_all_profiles_have_allowed_tools(self):
        """모든 프로필에 최소 1개 이상의 allowed_tools가 있는지 확인."""
        for agent_type, profile in AGENT_PROFILES.items():
            assert profile.allowed_tools, f"{agent_type}의 allowed_tools가 비어 있음"

    def test_all_profiles_allowed_tools_are_tuples(self):
        """모든 프로필의 allowed_tools가 tuple 타입인지 확인 (진정한 불변성 보장)."""
        for agent_type, profile in AGENT_PROFILES.items():
            assert isinstance(
                profile.allowed_tools, tuple
            ), f"{agent_type}의 allowed_tools가 tuple이 아님"


# ---------------------------------------------------------------------------
# 4. _classify_task 메서드 테스트 / _classify_task method tests
# ---------------------------------------------------------------------------

class TestClassifyTask:
    """_classify_task 키워드 기반 분류 로직 검증."""

    def setup_method(self):
        """AgentExecutor 인스턴스 생성."""
        self.executor = AgentExecutor(
            project_path="/tmp/test",
            use_rag=False,
        )

    def test_classify_architect_keyword(self):
        """'설계를 해주세요' 프롬프트는 ARCHITECT로 분류된다."""
        result = self.executor._classify_task("설계를 해주세요")
        assert result == AgentType.ARCHITECT

    def test_classify_coder_keyword(self):
        """'구현해주세요' 프롬프트는 CODER로 분류된다."""
        result = self.executor._classify_task("구현해주세요")
        assert result == AgentType.CODER

    def test_classify_tester_keyword(self):
        """'테스트를 작성해주세요' 프롬프트는 TESTER로 분류된다."""
        result = self.executor._classify_task("테스트를 작성해주세요")
        assert result == AgentType.TESTER

    def test_classify_reviewer_keyword(self):
        """'코드 리뷰해주세요' 프롬프트는 REVIEWER로 분류된다."""
        result = self.executor._classify_task("코드 리뷰해주세요")
        assert result == AgentType.REVIEWER

    def test_classify_documenter_readme_keyword(self):
        """'README 문서 작성' 프롬프트는 DOCUMENTER로 분류된다."""
        result = self.executor._classify_task("README 문서 작성")
        assert result == AgentType.DOCUMENTER

    def test_classify_fallback_to_coder(self):
        """매칭되는 키워드가 없으면 CODER로 폴백된다."""
        result = self.executor._classify_task("알 수 없는 작업")
        assert result == AgentType.CODER

    def test_classify_pytest_keyword(self):
        """'pytest 실행' 프롬프트는 TESTER로 분류된다."""
        result = self.executor._classify_task("pytest 실행")
        assert result == AgentType.TESTER

    def test_classify_case_insensitive(self):
        """'Test를 작성해주세요' 대문자 포함 프롬프트도 TESTER로 분류된다."""
        result = self.executor._classify_task("Test를 작성해주세요")
        assert result == AgentType.TESTER

    def test_classify_priority_architect_over_coder(self):
        """ARCHITECT 키워드와 CODER 키워드가 공존하면 ARCHITECT가 우선한다."""
        # '설계'(ARCHITECT) + '구현'(CODER) 동시 포함
        result = self.executor._classify_task("설계와 구현을 해주세요")
        assert result == AgentType.ARCHITECT

    def test_classify_priority_tester_over_coder(self):
        """TESTER 키워드와 CODER 키워드가 공존하면 TESTER가 우선한다."""
        # '테스트'(TESTER) + '작성'(CODER) 동시 포함
        result = self.executor._classify_task("테스트 코드 작성해주세요")
        assert result == AgentType.TESTER


# ---------------------------------------------------------------------------
# 5. execute 메서드 테스트 / execute method tests
# ---------------------------------------------------------------------------

class TestExecute:
    """execute 메서드 행동 검증."""

    def setup_method(self):
        """AgentExecutor 인스턴스 생성."""
        self.executor = AgentExecutor(
            project_path="/tmp/test",
            use_rag=False,
        )

    @pytest.mark.asyncio
    async def test_execute_returns_messages(self):
        """execute가 쿼리에서 반환된 메시지 리스트를 반환한다."""
        mock_msg = make_assistant_message("작업 완료")
        with patch("src.agents.executor.query", new=make_mock_query(mock_msg)):
            result = await self.executor.execute("do task")

        assert len(result) == 1
        assert result[0] is mock_msg

    @pytest.mark.asyncio
    async def test_execute_returns_multiple_messages(self):
        """execute가 복수 메시지를 모두 수집하여 반환한다."""
        msg1 = make_assistant_message("첫 번째")
        mock_result = MagicMock(spec=ResultMessage)
        with patch("src.agents.executor.query", new=make_mock_query(msg1, mock_result)):
            result = await self.executor.execute("task")

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_execute_handles_exception(self):
        """execute가 예외 발생 시 에러 딕셔너리를 결과에 포함한다."""
        async def error_query(*args, **kwargs):
            raise RuntimeError("API 연결 실패")
            yield  # async generator로 만들기 위한 yield

        with patch("src.agents.executor.query", new=error_query):
            result = await self.executor.execute("task")

        assert len(result) == 1
        assert "error" in result[0]
        assert "API 연결 실패" in result[0]["error"]

    @pytest.mark.asyncio
    async def test_execute_calls_classify_task_when_agent_type_is_none(self):
        """agent_type=None일 때 _classify_task가 호출되는지 확인."""
        with patch.object(
            self.executor, "_classify_task", return_value=AgentType.CODER
        ) as mock_classify:
            with patch("src.agents.executor.query", new=make_mock_query()):
                await self.executor.execute("구현해주세요", agent_type=None)

        mock_classify.assert_called_once_with("구현해주세요")

    @pytest.mark.asyncio
    async def test_execute_skips_classify_task_when_agent_type_provided(self):
        """agent_type을 명시하면 _classify_task가 호출되지 않는다."""
        with patch.object(
            self.executor, "_classify_task"
        ) as mock_classify:
            with patch("src.agents.executor.query", new=make_mock_query()):
                await self.executor.execute("task", agent_type=AgentType.CODER)

        mock_classify.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_uses_profile_model_in_options(self):
        """실행 시 지정된 프로필의 model이 ClaudeAgentOptions에 전달된다."""
        captured_options = {}

        async def capture_query(prompt, options):
            captured_options["model"] = getattr(options, "model", None)
            return
            yield

        with patch("src.agents.executor.query", new=capture_query):
            await self.executor.execute("task", agent_type=AgentType.ARCHITECT)

        # ARCHITECT 프로필의 model은 "claude-opus-4-6"
        assert captured_options["model"] == "claude-opus-4-6"

    @pytest.mark.asyncio
    async def test_execute_uses_profile_system_prompt_in_options(self):
        """실행 시 지정된 프로필의 system_prompt가 ClaudeAgentOptions에 전달된다."""
        captured_options = {}

        async def capture_query(prompt, options):
            captured_options["system_prompt"] = getattr(options, "system_prompt", None)
            return
            yield

        expected_prompt = AGENT_PROFILES[AgentType.CODER].system_prompt

        with patch("src.agents.executor.query", new=capture_query):
            await self.executor.execute("task", agent_type=AgentType.CODER)

        assert captured_options["system_prompt"] == expected_prompt

    @pytest.mark.asyncio
    async def test_execute_includes_quality_context_in_prompt(self):
        """execute가 quality context를 포함한 전체 프롬프트를 query에 전달한다."""
        captured_kwargs = {}

        async def capture_query(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return
            yield

        with patch("src.agents.executor.query", new=capture_query):
            await self.executor.execute("내 작업")

        prompt = captured_kwargs.get("prompt", "")
        assert "내 작업" in prompt
        assert "필수 준수사항" in prompt


# ---------------------------------------------------------------------------
# 6. execute_with_retry 테스트 / execute_with_retry tests
# ---------------------------------------------------------------------------

class TestExecuteWithRetry:
    """execute_with_retry 재시도 로직 및 agent_type 전달 검증."""

    def setup_method(self):
        """AgentExecutor 인스턴스 생성."""
        self.executor = AgentExecutor(
            project_path="/tmp/test",
            use_rag=False,
        )

    @pytest.mark.asyncio
    async def test_execute_with_retry_passes_agent_type_to_execute(self):
        """execute_with_retry가 agent_type을 execute()로 전달한다."""
        with patch.object(
            self.executor, "execute", new_callable=AsyncMock, return_value=[]
        ) as mock_execute:
            await self.executor.execute_with_retry(
                "task", max_retries=1, agent_type=AgentType.TESTER
            )

        mock_execute.assert_called_once_with("task", agent_type=AgentType.TESTER)

    @pytest.mark.asyncio
    async def test_execute_with_retry_passes_none_agent_type(self):
        """agent_type=None일 때 execute()에 None이 전달된다."""
        with patch.object(
            self.executor, "execute", new_callable=AsyncMock, return_value=[]
        ) as mock_execute:
            await self.executor.execute_with_retry("task", max_retries=1, agent_type=None)

        mock_execute.assert_called_once_with("task", agent_type=None)

    @pytest.mark.asyncio
    async def test_execute_with_retry_succeeds_on_first_try(self):
        """첫 번째 시도에 성공하면 바로 결과를 반환한다."""
        mock_msg = make_assistant_message("완료")
        with patch("src.agents.executor.query", new=make_mock_query(mock_msg)):
            result = await self.executor.execute_with_retry("task", max_retries=3)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_execute_with_retry_retries_on_error(self):
        """첫 번째 시도 실패 후 재시도하여 성공한다."""
        mock_msg = make_assistant_message("완료")
        call_count = 0

        async def failing_then_success(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                yield {"error": "일시적 오류"}
            else:
                yield mock_msg

        with patch("src.agents.executor.query", new=failing_then_success):
            result = await self.executor.execute_with_retry("task", max_retries=3)

        errors = [r for r in result if isinstance(r, dict) and "error" in r]
        assert not errors

    @pytest.mark.asyncio
    async def test_execute_with_retry_returns_after_max_retries(self):
        """최대 재시도 횟수 초과 후 에러 결과를 반환한다."""
        async def always_fail(*args, **kwargs):
            yield {"error": "계속 실패"}

        with patch("src.agents.executor.query", new=always_fail):
            result = await self.executor.execute_with_retry("task", max_retries=2)

        errors = [r for r in result if isinstance(r, dict) and "error" in r]
        assert errors
