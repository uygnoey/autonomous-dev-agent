# Agent Teams 사용 가이드

## 개요

이 프로젝트는 Claude Code의 Agent Teams 기능을 사용하여 여러 전문 에이전트가 협업하는 자율 개발 시스템을 구현합니다.

## 설정 확인

### 1. Agent Teams 활성화

`.claude/settings.json`에서 다음 설정이 활성화되어 있어야 합니다:

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

✅ **현재 상태**: 이미 활성화됨

### 2. 커스텀 에이전트 정의

`.claude/agents/` 디렉토리에 정의된 커스텀 에이전트:

| 에이전트 | 파일 | 역할 | 모델 |
|---------|------|------|------|
| `architect` | architect.md | 아키텍처 설계 | opus |
| `coder` | coder.md | 코드 구현 | sonnet |
| `tester` | tester.md | 테스트 작성/실행 | sonnet |
| `reviewer` | reviewer.md | 코드 리뷰 | sonnet |
| `documenter` | documenter.md | 문서화 | sonnet |

## 커스텀 에이전트 사용 방법

### 방법 1: Task 도구에서 직접 사용 (실험적)

커스텀 에이전트는 파일명을 `subagent_type`으로 사용할 수 있습니다:

```python
# 예제: architect 에이전트 호출
task_result = Task(
    subagent_type="architect",
    description="아키텍처 설계",
    prompt="새로운 인증 모듈의 아키텍처를 설계해주세요"
)
```

**참고**: 현재 Task 도구는 빌트인 에이전트 타입만 공식 지원합니다. 커스텀 에이전트가 인식되지 않으면 방법 2를 사용하세요.

### 방법 2: 빌트인 에이전트로 매핑

커스텀 에이전트의 역할에 맞는 빌트인 에이전트를 사용:

| 커스텀 | 빌트인 대체 | 이유 |
|--------|-------------|------|
| `architect` | `system-architect` | 시스템 설계 전문 |
| `coder` | `python-expert` | 코드 구현 전문 |
| `tester` | `quality-engineer` | 테스트 전문 |
| `reviewer` | `refactoring-expert` | 코드 품질 분석 |
| `documenter` | `technical-writer` | 문서 작성 전문 |

```python
# 예제: coder 역할을 python-expert로 실행
task_result = Task(
    subagent_type="python-expert",
    description="인증 모듈 구현",
    prompt="""
    .claude/skills/design-patterns/SKILL.md와
    .claude/skills/code-standards/SKILL.md를 참조하여
    인증 모듈을 구현해주세요.
    """
)
```

### 방법 3: TeamCreate와 함께 사용

팀을 생성하고 역할을 할당:

```python
# 1. 팀 생성
TeamCreate(
    team_name="auth-development",
    description="인증 시스템 개발 팀"
)

# 2. 작업 생성
TaskCreate(
    subject="인증 모듈 아키텍처 설계",
    description="JWT 기반 인증 시스템의 아키텍처를 설계",
    activeForm="아키텍처 설계 중"
)

# 3. architect 역할 에이전트 스폰 (system-architect 사용)
Task(
    team_name="auth-development",
    name="architect-agent",
    subagent_type="system-architect",
    description="아키텍처 설계",
    prompt=".claude/agents/architect.md의 지침을 따라 인증 모듈을 설계하세요"
)

# 4. coder 역할 에이전트 스폰
Task(
    team_name="auth-development",
    name="coder-agent",
    subagent_type="python-expert",
    description="코드 구현",
    prompt=".claude/agents/coder.md의 지침을 따라 인증 모듈을 구현하세요"
)
```

## 에이전트별 작업 지침

### Architect (설계)

```python
Task(
    subagent_type="system-architect",
    description="모듈 설계",
    prompt="""
    다음 순서로 설계를 진행하세요:
    1. .claude/skills/design-patterns/SKILL.md 확인
    2. .claude/skills/project-architecture/SKILL.md 확인
    3. 기존 코드 구조 분석
    4. 디렉토리 구조, 모듈 의존성, API 설계
    5. 결과를 docs/architecture/에 저장

    [구체적인 설계 요구사항]
    """
)
```

### Coder (구현)

```python
Task(
    subagent_type="python-expert",
    description="기능 구현",
    prompt="""
    다음 순서로 구현하세요:
    1. .claude/skills/design-patterns/SKILL.md 확인
    2. .claude/skills/code-standards/SKILL.md 확인
    3. 기존 유사 코드 패턴 검색 (rag-search 스킬)
    4. 코드 구현 + 테스트 코드 작성
    5. ruff check --fix 실행
    6. mypy 타입 체크
    7. 에러 있으면 수정하고 반복

    절대 사람에게 빌드/테스트 실패를 묻지 말고 스스로 해결하세요.

    [구체적인 구현 요구사항]
    """
)
```

### Tester (테스트)

```python
Task(
    subagent_type="quality-engineer",
    description="테스트 작성 및 실행",
    prompt="""
    다음 목표를 달성하세요:
    1. .claude/skills/testing-strategy/SKILL.md 확인
    2. 테스트 케이스 작성 (happy path + edge case + error case)
    3. pytest 실행하여 커버리지 확인
    4. 실패한 테스트 분석 및 수정
    5. 100% 통과할 때까지 반복

    목표 커버리지:
    - 전체: 90% 이상
    - 비즈니스 로직: 95% 이상

    절대 사람에게 테스트 실패를 묻지 말고 스스로 해결하세요.

    [테스트 대상]
    """
)
```

### Reviewer (리뷰)

```python
Task(
    subagent_type="refactoring-expert",
    description="코드 리뷰",
    prompt="""
    다음 체크리스트로 리뷰하세요:
    1. design-patterns 준수 확인
    2. code-standards 준수 확인
    3. error-handling 패턴 확인
    4. 테스트 품질 확인
    5. 보안 취약점 확인

    발견된 문제는 "이렇게 바꿔라"는 구체적 수정 지시로 제공하세요.

    [리뷰 대상 파일들]
    """
)
```

### Documenter (문서화)

```python
Task(
    subagent_type="technical-writer",
    description="문서 생성",
    prompt="""
    다음 문서를 생성/갱신하세요:
    1. README.md (프로젝트 개요, 빠른 시작)
    2. docs/api/ (API 문서)
    3. docs/architecture/ (아키텍처 문서)
    4. docs/setup/ (설치 및 배포)
    5. CHANGELOG.md
    6. docs/contributing.md

    규칙:
    - 코드에서 직접 추출한 정확한 정보만 사용
    - 추측하지 않기
    - 마크다운 형식, 코드 블록에 언어 태그 필수

    [문서화 대상]
    """
)
```

## 전체 워크플로우 예제

```python
# 1. 팀 생성
TeamCreate(
    team_name="feature-auth",
    description="인증 기능 개발"
)

# 2. 태스크 생성
TaskCreate(
    subject="JWT 인증 시스템 구현",
    description="완전한 JWT 기반 인증 시스템 (설계~문서까지)",
    activeForm="인증 시스템 개발 중"
)

# 3. Architect: 설계
Task(
    team_name="feature-auth",
    name="architect",
    subagent_type="system-architect",
    description="설계",
    prompt="JWT 인증 시스템 아키텍처 설계 (.claude/agents/architect.md 참조)"
)

# 4. Coder: 구현
Task(
    team_name="feature-auth",
    name="coder",
    subagent_type="python-expert",
    description="구현",
    prompt="설계에 따라 JWT 인증 구현 (.claude/agents/coder.md 참조)"
)

# 5. Tester: 테스트
Task(
    team_name="feature-auth",
    name="tester",
    subagent_type="quality-engineer",
    description="테스트",
    prompt="인증 시스템 테스트 100% 통과 (.claude/agents/tester.md 참조)"
)

# 6. Reviewer: 리뷰
Task(
    team_name="feature-auth",
    name="reviewer",
    subagent_type="refactoring-expert",
    description="리뷰",
    prompt="코드 품질 검증 (.claude/agents/reviewer.md 참조)"
)

# 7. Documenter: 문서화
Task(
    team_name="feature-auth",
    name="documenter",
    subagent_type="technical-writer",
    description="문서화",
    prompt="전체 문서 생성 (.claude/agents/documenter.md 참조)"
)

# 8. 팀 정리
TeamDelete()
```

## Skills 참조 방법

각 에이전트는 반드시 해당 Skills를 참조해야 합니다:

### 모든 에이전트가 참조
- `.claude/skills/rag-search/SKILL.md` - 기존 코드 패턴 검색

### 역할별 참조
- **Architect**:
  - `design-patterns/SKILL.md`
  - `project-architecture/SKILL.md`

- **Coder**:
  - `design-patterns/SKILL.md`
  - `code-standards/SKILL.md`
  - `testing-strategy/SKILL.md`
  - `error-handling/SKILL.md`

- **Tester**:
  - `testing-strategy/SKILL.md`
  - `error-handling/SKILL.md`

- **Reviewer**:
  - 모든 Skills

- **Documenter**:
  - `project-architecture/SKILL.md`

## 자주 묻는 질문

### Q: 커스텀 에이전트가 인식되지 않아요

A: 현재는 빌트인 에이전트 타입을 사용하고, prompt에서 `.claude/agents/{name}.md`를 참조하도록 지시하세요.

### Q: 에이전트가 Skills를 참조하지 않아요

A: prompt에 명시적으로 "`.claude/skills/design-patterns/SKILL.md`를 먼저 읽고 따르세요"를 포함하세요.

### Q: 에이전트가 빌드 실패 시 사람에게 물어봐요

A: prompt에 "절대 사람에게 묻지 말고 100% 통과할 때까지 스스로 해결하세요"를 명시하세요.

### Q: 테스트가 실패해도 넘어가요

A: `.claude/agents/tester.md`를 참조하도록 하고, "100% 통과가 목표"임을 강조하세요.

## 다음 단계

1. ✅ Agent Teams 활성화 완료
2. ✅ 커스텀 에이전트 정의 완료
3. ⏳ 실제 워크플로우 테스트
4. ⏳ Orchestrator에서 자동 팀 생성 구현

## 참고 문서

- [CLAUDE.md](../../CLAUDE.md) - 프로젝트 전체 규칙
- [Skills 디렉토리](../../.claude/skills/) - 코딩 지식 베이스
- [Agents 디렉토리](../../.claude/agents/) - 에이전트 정의
