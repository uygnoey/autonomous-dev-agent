---
name: error-handling
description: 에러 처리 패턴과 규칙. 예외 처리, 에러 클래스, 로깅, 재시도 로직 작성 시 참조.
---

# Error Handling

## 커스텀 에러 클래스 계층
```python
# errors/base.py
class AppError(Exception):
    """애플리케이션 기본 에러."""
    def __init__(self, message: str, code: str = "UNKNOWN"):
        self.message = message
        self.code = code
        super().__init__(self.message)

class NotFoundError(AppError):
    """리소스를 찾을 수 없음."""
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            message=f"{resource} '{identifier}' not found",
            code="NOT_FOUND"
        )

class ValidationError(AppError):
    """입력 검증 실패."""
    def __init__(self, field: str, reason: str):
        super().__init__(
            message=f"Validation failed for '{field}': {reason}",
            code="VALIDATION_ERROR"
        )

class ConflictError(AppError):
    """리소스 충돌."""
    def __init__(self, message: str):
        super().__init__(message=message, code="CONFLICT")

class ExternalServiceError(AppError):
    """외부 서비스 호출 실패."""
    def __init__(self, service: str, reason: str):
        super().__init__(
            message=f"External service '{service}' failed: {reason}",
            code="EXTERNAL_ERROR"
        )
```

## 에러 처리 규칙
1. 빈 catch/except 금지. 반드시 구체적 에러 타입 지정
2. 에러 삼킴 금지. 최소한 로깅
3. 비즈니스 에러는 커스텀 에러 클래스 사용
4. 시스템 에러(DB, 네트워크)는 재시도 후 래핑하여 전파

## 재시도 패턴
```python
import asyncio

async def retry_with_backoff(
    func,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
):
    """지수 백오프 재시도."""
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            delay = min(base_delay * (2 ** attempt), max_delay)
            logger.warning(f"Retry {attempt + 1}/{max_retries} after {delay}s: {e}")
            await asyncio.sleep(delay)
```

## 레이어별 에러 처리
- **Repository**: DB 에러 → 커스텀 에러로 래핑
- **Service**: 비즈니스 검증 에러 발생, Repository 에러 전파
- **Controller**: 에러 → HTTP 응답 코드 매핑, 로깅
