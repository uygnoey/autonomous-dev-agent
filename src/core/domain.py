"""도메인 모델 정의.

에이전트 실행의 입력(AgentTask), 출력(AgentResult),
컨텍스트(ExecutionContext), RAG 청크(CodeChunk) 등
시스템 전체에서 사용하는 핵심 데이터 구조.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class AgentTask:
    """에이전트에게 전달하는 작업 명세.

    frozen=True로 불변성을 보장하여 여러 에이전트가
    동일한 태스크 객체를 안전하게 공유할 수 있다.
    """

    prompt: str
    agent_type: str | None = None
    priority: int = 0
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """에이전트 실행 결과.

    에이전트가 작업을 마친 뒤 반환하는 구조화된 결과.
    Orchestrator가 다음 계획 수립에 활용한다.
    """

    agent_type: str
    task_prompt: str
    output_text: str
    files_modified: list[str] = field(default_factory=list)
    success: bool = True
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


@dataclass
class ExecutionContext:
    """에이전트 실행 컨텍스트.

    현재 프로젝트 상태와 지금까지의 실행 이력을 담는다.
    에이전트는 이 정보를 참고하여 중복 작업을 피하고
    이전 결과를 기반으로 다음 작업을 수행한다.
    """

    # TYPE_CHECKING으로 순환 import를 방지하고 런타임에는 Any로 처리
    project_state: Any  # 실제 타입: ProjectState
    execution_history: list[AgentResult] = field(default_factory=list)
    rag_results: list[CodeChunk] = field(default_factory=list)

    def last_result_of(self, agent_type: str) -> AgentResult | None:
        """특정 에이전트 유형의 가장 최근 결과를 반환한다.

        Args:
            agent_type: 조회할 에이전트 유형 문자열

        Returns:
            가장 최근 AgentResult, 없으면 None
        """
        matches = [
            r for r in self.execution_history if r.agent_type == agent_type
        ]
        return matches[-1] if matches else None

    def summary_for_planner(self, n: int = 5) -> str:
        """Planner가 다음 계획 수립에 활용할 실행 이력 요약을 반환한다.

        최근 n개의 결과를 성공/실패 여부와 함께 간결하게 서술한다.

        Args:
            n: 포함할 최근 결과의 최대 개수

        Returns:
            사람이 읽기 쉬운 요약 문자열
        """
        recent = self.execution_history[-n:]
        if not recent:
            return "실행 이력 없음"

        lines: list[str] = []
        for result in recent:
            status = "성공" if result.success else f"실패({result.error})"
            lines.append(f"- [{result.agent_type}] {status}: {result.task_prompt[:60]}")

        return "\n".join(lines)


@dataclass(frozen=True)
class CodeChunk:
    """RAG 검색에 사용하는 코드 청크.

    소스 파일의 의미 있는 단위(함수, 클래스 등)를 나타낸다.
    frozen=True로 불변성을 보장하여 캐시와 집합 연산에 안전하다.

    chunk_type 허용값: function / class / module / block
    """

    file_path: str
    content: str
    start_line: int
    end_line: int
    chunk_type: str = "block"
    name: str | None = None

    def __str__(self) -> str:
        """사람이 읽기 쉬운 청크 표현을 반환한다."""
        label = self.name or f"lines {self.start_line}-{self.end_line}"
        return f"[{self.chunk_type}] {self.file_path}:{label}"
