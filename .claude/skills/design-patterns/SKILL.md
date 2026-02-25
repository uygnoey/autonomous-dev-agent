---
name: design-patterns
description: 프로젝트의 디자인 패턴과 아키텍처 규칙. 코드 작성, 리팩토링, 새 모듈 생성, 구조 결정 시 반드시 참조. 새 파일을 만들기 전에 이 스킬을 먼저 읽을 것.
---

# Design Pattern Guide

## 아키텍처: Layered Clean Architecture

모든 코드는 다음 레이어 구조를 따른다. 의존성은 반드시 안쪽으로만.

```
Controller/API (진입점)
    ↓ 호출만
Service (비즈니스 로직)
    ↓ 호출만
Repository (데이터 접근)
    ↓ 호출만
Domain (엔티티, 값 객체)
```

### 레이어별 책임

**Domain**: 순수 데이터 구조. 외부 의존성 없음.
```python
# domain/user.py
@dataclass
class User:
    id: str
    name: str
    email: str
    created_at: datetime
```

**Repository**: 데이터 접근 인터페이스 + 구현. 반드시 인터페이스(Protocol/ABC) 정의.
```python
# repository/user_repository.py
class UserRepository(Protocol):
    async def find_by_id(self, user_id: str) -> User | None: ...
    async def save(self, user: User) -> User: ...
    async def delete(self, user_id: str) -> bool: ...

# repository/impl/user_repository_impl.py
class UserRepositoryImpl:
    def __init__(self, db: Database):
        self._db = db
    
    async def find_by_id(self, user_id: str) -> User | None:
        ...
```

**Service**: 비즈니스 로직. Repository를 주입받아 사용. 절대로 DB 직접 접근 금지.
```python
# service/user_service.py
class UserService:
    def __init__(self, user_repo: UserRepository):
        self._user_repo = user_repo
    
    async def get_user(self, user_id: str) -> User:
        user = await self._user_repo.find_by_id(user_id)
        if not user:
            raise UserNotFoundError(user_id)
        return user
```

**Controller/API**: 진입점. 요청 파싱 → Service 호출 → 응답 포맷팅만.
```python
# controller/user_controller.py
class UserController:
    def __init__(self, user_service: UserService):
        self._user_service = user_service
    
    async def get_user(self, request: Request) -> Response:
        user_id = request.path_params["user_id"]
        user = await self._user_service.get_user(user_id)
        return Response(UserDTO.from_domain(user))
```

## 필수 패턴

### 1. Dependency Injection
모든 의존성은 생성자 주입. 전역 상태 금지.

### 2. DTO (Data Transfer Object)
레이어 간 데이터 전달은 반드시 DTO. Domain 객체를 외부에 직접 노출 금지.

### 3. Result Pattern (에러 처리)
비즈니스 에러는 예외 대신 Result 패턴 사용 권장.
```python
@dataclass
class Result(Generic[T]):
    success: bool
    data: T | None = None
    error: str | None = None
    
    @classmethod
    def ok(cls, data: T) -> "Result[T]":
        return cls(success=True, data=data)
    
    @classmethod
    def fail(cls, error: str) -> "Result[T]":
        return cls(success=False, error=error)
```

### 4. Factory Pattern
복잡한 객체 생성은 Factory 사용.

### 5. Strategy Pattern
동일 인터페이스, 다른 구현이 필요한 경우 Strategy.

## 금지 사항
- Controller에 비즈니스 로직 작성 금지
- Repository에서 다른 Repository 직접 호출 금지
- Domain 객체에 외부 라이브러리 의존 금지
- 전역 변수 / 싱글톤 남용 금지
- God Class (하나의 클래스가 모든 것을 하는 것) 금지
