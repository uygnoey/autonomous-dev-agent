---
name: testing-strategy
description: 테스트 작성 전략과 규칙. 테스트 코드 작성, 테스트 실행, 커버리지 확인 시 참조. 테스트 100% 통과가 목표.
---

# Testing Strategy

## 테스트 원칙
1. 모든 비즈니스 로직에 유닛 테스트 필수
2. 모든 API 엔드포인트에 통합 테스트 필수
3. 커버리지 목표: 90% 이상
4. 테스트 실패 시 코드를 수정하고 재실행. 100% 통과할 때까지 반복.

## 테스트 구조 (AAA 패턴)
```python
async def test_get_user_returns_user_when_exists():
    # Arrange (준비)
    user_repo = FakeUserRepository()
    user_repo.add(User(id="u1", name="Alice", email="alice@test.com"))
    service = UserService(user_repo)
    
    # Act (실행)
    result = await service.get_user("u1")
    
    # Assert (검증)
    assert result.name == "Alice"
    assert result.email == "alice@test.com"
```

## 테스트 네이밍
```python
# 패턴: test_{대상}_{상황}_{기대결과}
def test_create_user_with_duplicate_email_raises_conflict_error():
def test_calculate_total_with_discount_returns_discounted_price():
def test_login_with_expired_token_returns_unauthorized():
```

## 필수 테스트 케이스
모든 함수에 대해 최소한 다음을 테스트:
1. **Happy path**: 정상 입력 → 정상 출력
2. **Edge case**: 빈 값, None, 경계값
3. **Error case**: 잘못된 입력 → 적절한 에러

## Mock/Fake 사용 규칙
- Repository는 Fake 구현 사용 (인메모리)
- 외부 API는 Mock 사용
- 내부 Service는 가능하면 실제 객체 사용

## 테스트 실행 명령어
```bash
# 전체 테스트
pytest tests/ -v

# 커버리지 포함
pytest tests/ -v --cov=src --cov-report=term-missing

# 특정 파일
pytest tests/test_user_service.py -v

# 실패한 테스트만 재실행
pytest tests/ --lf
```

## 테스트 실패 시 자율 해결 절차
1. 에러 메시지 분석
2. 실패 원인 파악 (코드 버그 vs 테스트 오류)
3. 코드 수정
4. 테스트 재실행
5. 통과할 때까지 반복 (사람에게 물어보지 않는다)
