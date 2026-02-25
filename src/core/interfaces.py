"""핵심 인터페이스 정의.

모든 모듈이 의존하는 Protocol 기반 계약.
구현체는 각 모듈에서 제공한다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from src.core.domain import AgentResult, AgentTask, CodeChunk, ExecutionContext


@runtime_checkable
class AgentProtocol(Protocol):
    """에이전트 실행 계약.

    각 에이전트 구현체(architect, coder, tester 등)가 준수해야 하는 인터페이스.
    """

    @property
    def agent_type(self) -> str:
        """에이전트 유형 식별자."""
        ...

    async def execute(
        self,
        task: AgentTask,
        context: ExecutionContext,
    ) -> AgentResult:
        """주어진 태스크를 실행하고 결과를 반환한다.

        Args:
            task: 수행할 작업 명세
            context: 현재 프로젝트 실행 컨텍스트

        Returns:
            실행 결과
        """
        ...


@runtime_checkable
class RouterProtocol(Protocol):
    """태스크 라우팅 계약.

    태스크를 분석하여 가장 적합한 에이전트를 선택하는 책임을 가진다.
    """

    async def route(
        self,
        task: AgentTask,
        available_agents: list[str],
    ) -> str:
        """태스크를 처리할 에이전트 유형을 결정한다.

        Args:
            task: 라우팅할 작업
            available_agents: 사용 가능한 에이전트 유형 목록

        Returns:
            선택된 에이전트 유형 문자열
        """
        ...


@runtime_checkable
class ChunkerProtocol(Protocol):
    """코드 청킹 계약.

    소스 파일을 의미 있는 단위(함수, 클래스 등)로 분할한다.
    """

    def chunk(self, file_path: str, content: str) -> list[CodeChunk]:
        """소스 파일 내용을 코드 청크 목록으로 분할한다.

        Args:
            file_path: 파일 경로 (메타데이터 용도)
            content: 파일 전체 텍스트 내용

        Returns:
            분할된 CodeChunk 목록
        """
        ...


@runtime_checkable
class ScorerProtocol(Protocol):
    """문서 스코어링 계약.

    쿼리와 문서 간의 관련도를 계산하는 BM25 등의 스코어러가 구현한다.
    """

    def fit(self, documents: list[str]) -> None:
        """문서 코퍼스로 스코어러를 학습한다.

        Args:
            documents: 학습에 사용할 문서 텍스트 목록
        """
        ...

    def score(self, query: str, doc_index: int) -> float:
        """특정 문서에 대한 쿼리의 관련도 점수를 반환한다.

        Args:
            query: 검색 쿼리
            doc_index: 대상 문서의 인덱스 (fit 시 전달한 목록 기준)

        Returns:
            관련도 점수 (높을수록 관련성 높음)
        """
        ...


@runtime_checkable
class EmbeddingProtocol(Protocol):
    """텍스트 임베딩 계약.

    텍스트를 벡터 공간으로 변환하는 구현체가 준수해야 한다.
    """

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """텍스트 목록을 임베딩 벡터로 변환한다.

        Args:
            texts: 임베딩할 텍스트 목록

        Returns:
            각 텍스트에 대응하는 float 벡터 목록
        """
        ...


@runtime_checkable
class UIAdapterProtocol(Protocol):
    """UI 어댑터 계약.

    TUI, CLI, Web 등 다양한 UI 구현체가 준수해야 하는 공통 인터페이스.
    emit_* 메서드는 단방향 알림이고, ask_question은 사용자 응답을 기다린다.
    """

    async def emit_log(self, msg: str, level: str) -> None:
        """로그 메시지를 UI에 출력한다.

        Args:
            msg: 출력할 메시지
            level: 로그 레벨 (debug/info/warning/error)
        """
        ...

    async def emit_progress(self, data: dict[str, Any]) -> None:
        """진행 상태 데이터를 UI에 전달한다.

        Args:
            data: 진행률, 단계, 반복 횟수 등의 상태 정보
        """
        ...

    async def ask_question(self, issue: str) -> str | None:
        """크리티컬 이슈에 대한 사용자 답변을 요청한다.

        Args:
            issue: 사용자에게 물어볼 이슈 내용

        Returns:
            사용자의 답변 문자열, 타임아웃/취소 시 None
        """
        ...

    async def emit_completed(self, summary: str) -> None:
        """프로젝트 완성 이벤트를 UI에 전달한다.

        Args:
            summary: 완성 요약 텍스트
        """
        ...


@runtime_checkable
class PluginProtocol(Protocol):
    """플러그인 계약.

    Orchestrator 생애주기 이벤트를 구독하는 플러그인이 구현한다.
    """

    @property
    def name(self) -> str:
        """플러그인 고유 이름."""
        ...

    @property
    def version(self) -> str:
        """플러그인 버전 (semver 권장)."""
        ...

    async def on_task_complete(self, result: AgentResult) -> None:
        """에이전트 태스크 완료 시 호출된다.

        Args:
            result: 완료된 태스크의 실행 결과
        """
        ...

    async def on_phase_change(self, phase: str) -> None:
        """프로젝트 단계가 전환될 때 호출된다.

        Args:
            phase: 새로운 단계 이름 (PhaseType 값)
        """
        ...
