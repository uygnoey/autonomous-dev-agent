# 프로젝트 스펙 예시

이 파일을 실제 프로젝트 스펙으로 교체하세요.
기획/디자인/UI/UX가 사람과의 논의를 통해 확정된 후,
이 파일에 최종 스펙을 작성합니다.

## 예시: TODO API 서버

### 기능 요구사항
1. 사용자 등록/로그인 (이메일+패스워드)
2. TODO 항목 CRUD
3. TODO 항목에 태그 추가/삭제
4. 마감일 기반 정렬
5. 완료/미완료 필터링

### 기술 스택
- Python 3.12
- FastAPI
- SQLite (개발), PostgreSQL (운영)
- JWT 인증

### API 엔드포인트
- POST /auth/register
- POST /auth/login
- GET /todos
- POST /todos
- PUT /todos/{id}
- DELETE /todos/{id}
- POST /todos/{id}/tags
- DELETE /todos/{id}/tags/{tag}
