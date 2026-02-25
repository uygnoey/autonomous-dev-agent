"""구조화된 로깅 설정."""

import logging
import sys


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """프로젝트 표준 로거를 생성한다.

    Args:
        name: 로거 이름 (보통 __name__)
        level: 로그 레벨

    Returns:
        설정된 Logger 인스턴스
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(level)

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)

        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
