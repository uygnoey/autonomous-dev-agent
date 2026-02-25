"""구조화된 로깅 시스템.

structlog 기반 JSON 파일 핸들러 + 컬러 콘솔 핸들러.
기존 setup_logger(name) 시그니처를 유지한다.
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_FILE = Path("logs") / "agent.log"
_LOG_FORMAT = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_BACKUP_COUNT = 3

_LEVEL_COLORS = {
    "DEBUG": "\033[36m",
    "INFO": "\033[32m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[35m",
}
_RESET = "\033[0m"


class _ColorFormatter(logging.Formatter):
    """ANSI 컬러를 적용하는 콘솔 포맷터."""

    def format(self, record: logging.LogRecord) -> str:
        color = _LEVEL_COLORS.get(record.levelname, "")
        record.levelname = f"{color}{record.levelname}{_RESET}"
        return super().format(record)


def _resolve_level() -> int:
    """환경변수 ADEV_LOG_LEVEL로 레벨을 결정한다."""
    name = os.environ.get("ADEV_LOG_LEVEL", "INFO").upper()
    return getattr(logging, name, logging.INFO)


def _build_console_handler(level: int) -> logging.Handler:
    """컬러 콘솔 핸들러를 생성한다."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(_ColorFormatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    return handler


def _build_file_handler(level: int) -> logging.Handler:
    """로테이팅 파일 핸들러를 생성한다."""
    _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        _LOG_FILE,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    return handler


def _configure_structlog() -> None:
    """structlog을 JSON + 컬러 콘솔 방식으로 초기화한다."""
    try:
        import structlog

        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.dev.ConsoleRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
        )
    except Exception:
        pass


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """프로젝트 표준 로거를 생성한다.

    structlog이 설치되어 있으면 structlog을 초기화하고,
    없으면 stdlib logging으로 폴백한다.

    Args:
        name: 로거 이름 (보통 __name__)
        level: 로그 레벨 (환경변수 ADEV_LOG_LEVEL로 오버라이드 가능)

    Returns:
        설정된 Logger 인스턴스
    """
    effective_level = _resolve_level()

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(effective_level)
    logger.addHandler(_build_console_handler(effective_level))

    with contextlib.suppress(OSError):
        logger.addHandler(_build_file_handler(effective_level))

    with contextlib.suppress(ImportError):
        _configure_structlog()

    return logger
