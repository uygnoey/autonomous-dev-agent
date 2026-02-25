"""도메인 예외 계층.

AppError를 기반으로 한 구조화된 예외 체계.
모든 커스텀 예외는 AppError를 상속한다.

사용 예시:
    raise AgentError(agent_type="coder", reason="빌드 실패")
    raise ConfigError("ANTHROPIC_API_KEY가 설정되지 않았습니다")
"""

from __future__ import annotations


class AppError(Exception):
    """애플리케이션 기반 예외.

    모든 커스텀 예외의 최상위 클래스.
    code 속성으로 프로그래매틱 에러 분류를 지원한다.
    """

    def __init__(self, message: str, code: str = "UNKNOWN") -> None:
        """AppError를 초기화한다.

        Args:
            message: 사람이 읽을 수 있는 에러 설명
            code: 프로그래매틱 에러 분류 코드 (기본값: UNKNOWN)
        """
        super().__init__(message)
        self.message = message
        self.code = code

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"


class AgentError(AppError):
    """에이전트 실행 중 발생한 예외.

    어떤 에이전트에서, 어떤 이유로 실패했는지를 함께 기록한다.
    """

    def __init__(self, agent_type: str, reason: str) -> None:
        """AgentError를 초기화한다.

        Args:
            agent_type: 실패한 에이전트 유형 (예: "coder", "tester")
            reason: 실패 원인 설명
        """
        super().__init__(
            message=f"[{agent_type}] 에이전트 실행 실패: {reason}",
            code="AGENT_ERROR",
        )
        self.agent_type = agent_type
        self.reason = reason


class RAGError(AppError):
    """RAG 시스템 관련 예외.

    인덱싱, 검색, 청킹 과정에서 발생하는 오류를 나타낸다.
    """

    def __init__(self, message: str) -> None:
        """RAGError를 초기화한다.

        Args:
            message: 사람이 읽을 수 있는 에러 설명
        """
        super().__init__(message=message, code="RAG_ERROR")


class ConfigError(AppError):
    """설정 오류 예외.

    환경 변수 누락, 잘못된 설정 값 등 구성 관련 오류를 나타낸다.
    """

    def __init__(self, message: str) -> None:
        """ConfigError를 초기화한다.

        Args:
            message: 사람이 읽을 수 있는 에러 설명
        """
        super().__init__(message=message, code="CONFIG_ERROR")


class TokenLimitError(AppError):
    """토큰 한도 초과 예외.

    Claude API의 컨텍스트 토큰 한도에 도달했을 때 발생한다.
    Orchestrator가 이 예외를 포착하여 상태를 저장하고 재시작을 대기한다.
    """

    def __init__(self, message: str) -> None:
        """TokenLimitError를 초기화한다.

        Args:
            message: 사람이 읽을 수 있는 에러 설명
        """
        super().__init__(message=message, code="TOKEN_LIMIT")
