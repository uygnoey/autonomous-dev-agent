---
name: code-standards
description: 코딩 컨벤션과 스타일 가이드. 코드 작성, 리뷰, 수정 시 반드시 참조. 네이밍, 포맷팅, import 순서, 주석 규칙 등.
---

# Code Standards

## 네이밍 규칙

### Python
- 클래스: `PascalCase` (예: `UserService`, `OrderRepository`)
- 함수/메서드: `snake_case` (예: `get_user_by_id`, `calculate_total`)
- 변수: `snake_case` (예: `user_name`, `order_count`)
- 상수: `UPPER_SNAKE_CASE` (예: `MAX_RETRY_COUNT`, `DEFAULT_TIMEOUT`)
- Private: `_prefix` (예: `_internal_method`, `_cache`)
- 파일명: `snake_case.py` (예: `user_service.py`)

### TypeScript/JavaScript
- 클래스/인터페이스/타입: `PascalCase`
- 함수/변수: `camelCase`
- 상수: `UPPER_SNAKE_CASE`
- 파일명: 컴포넌트는 `PascalCase.tsx`, 그 외 `camelCase.ts`

### 의미 있는 이름
```python
# BAD
d = 30          # 뭔지 모름
lst = []        # 뭔 리스트인지 모름
def proc(x):    # 뭘 처리하는지 모름

# GOOD
timeout_seconds = 30
pending_orders = []
def validate_email(email: str) -> bool:
```

## 함수 규칙

### 단일 책임
- 한 함수는 한 가지 일만
- 20줄 이내 권장, 최대 40줄
- 파라미터 4개 이하 (초과 시 dataclass/dict 사용)

### 타입 힌트 필수 (Python)
```python
# BAD
def get_user(user_id):
    ...

# GOOD
async def get_user(self, user_id: str) -> User | None:
    """사용자 ID로 사용자를 조회한다.
    
    Args:
        user_id: 조회할 사용자의 고유 ID
        
    Returns:
        User 객체. 존재하지 않으면 None.
    """
    ...
```

## Import 순서 (Python)
```python
# 1. 표준 라이브러리
import os
import sys
from datetime import datetime
from pathlib import Path

# 2. 서드파티 라이브러리
import anthropic
from pydantic import BaseModel

# 3. 프로젝트 내부
from src.domain.user import User
from src.repository.user_repository import UserRepository
```

## 주석 규칙

### 모든 모듈 최상단에 목적 설명
```python
"""사용자 인증 서비스.

OAuth2 및 이메일/패스워드 인증을 처리한다.
JWT 토큰 발행 및 검증도 이 모듈에서 담당한다.
"""
```

### WHY 주석 (WHAT이 아닌 WHY)
```python
# BAD: what (코드 자체가 이미 말하고 있음)
# 사용자를 조회한다
user = await repo.find_by_id(user_id)

# GOOD: why (코드만으로는 알 수 없는 이유)
# 캐시 무효화 전에 DB에서 최신 상태를 먼저 확인해야
# race condition을 방지할 수 있다
user = await repo.find_by_id(user_id, use_cache=False)
```

## 에러 메시지 규칙
- 사용자에게 보여줄 메시지와 개발자 로그 메시지를 분리
- 에러 메시지에 디버깅에 필요한 컨텍스트 포함
```python
# BAD
raise ValueError("Invalid input")

# GOOD
raise UserNotFoundError(
    f"User with id '{user_id}' not found in database. "
    f"Searched in table: {self._table_name}"
)
```

## 파일 크기 제한
- 파일당 최대 300줄 (초과 시 분리)
- 클래스당 최대 200줄
- 하나의 파일에 하나의 주요 클래스
