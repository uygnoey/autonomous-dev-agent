# AgentExecutor 작업 유형별 라우팅 설계

## 목차

1. [개요](#개요)
2. [AgentType Enum 정의](#agenttype-enum-정의)
3. [분류 로직](#분류-로직)
4. [에이전트별 프로필](#에이전트별-프로필)
5. [AgentExecutor 변경사항](#agentexecutor-변경사항)
6. [설계 결정 근거](#설계-결정-근거)

---

## 개요

### 배경

현재 `AgentExecutor.execute()`는 모든 작업을 단일 범용 에이전트로 처리한다.
이 구조는 작업 유형에 무관하게 동일한 `system_prompt`와 `allowed_tools`를 사용하므로
에이전트가 불필요한 도구에 접근하거나 역할 경계가 불분명해지는 문제가 있다.

### 목적

작업의 내용(task_prompt)을 분석하여 적합한 에이전트 유형을 자동으로 선택한다.
각 에이전트는 역할에 최적화된 `system_prompt`, `allowed_tools`, `model`을 갖는다.

### 핵심 원칙

- **단일 책임**: 각 에이전트는 정확히 하나의 역할만 수행한다
- **최소 권한**: 필요한 도구만 허용한다 (예: REVIEWER는 Write 도구 없음)
- **명시적 경계**: 에이전트가 할 수 없는 작업을 system_prompt에 명확히 기술한다
- **폴백 전략**: 분류 불가 시 CODER를 기본값으로 사용한다

### 변경 범위

```
src/agents/executor.py
  └── AgentType (신규 Enum)
  └── AGENT_PROFILES (신규 상수)
  └── AgentExecutor._classify_task() (신규 메서드)
  └── AgentExecutor.execute() (시그니처 변경)
```

---

## AgentType Enum 정의

```python
from enum import StrEnum


class AgentType(StrEnum):
    """작업 유형별 에이전트 분류.

    StrEnum을 사용하여 문자열 비교와 로깅이 간편하다.
    각 값은 .claude/agents/ 디렉토리의 에이전트 정의 파일명과 대응한다.
    """

    ARCHITECT = "architect"    # 설계, 구조, 아키텍처 결정
    CODER = "coder"            # 코드 구현, 버그 수정, 리팩토링
    TESTER = "tester"          # 테스트 작성 및 실행
    REVIEWER = "reviewer"      # 코드 리뷰 및 품질 검증
    DOCUMENTER = "documenter"  # 문서 작성 및 갱신
```

---

## 분류 로직

### 키워드 매핑 테이블

| AgentType    | 분류 키워드                                                                    |
|--------------|-------------------------------------------------------------------------------|
| ARCHITECT    | 설계, 구조, 아키텍처, 모듈, API 설계, 데이터 모델, 디렉토리, 인터페이스, 의존성 |
| CODER        | 구현, 작성, 코딩, 버그 수정, 리팩토링, 기능 추가, 개발, 수정                    |
| TESTER       | 테스트, 커버리지, pytest, 검증, test, 단위 테스트, 통합 테스트                  |
| REVIEWER     | 리뷰, 검토, 품질 확인, 코드 검사, 점검, 감사                                    |
| DOCUMENTER   | 문서, README, API 문서, CHANGELOG, 주석, 가이드, 설명서                         |

### 우선순위 규칙

동일 task_prompt에서 여러 키워드가 매칭될 경우 아래 우선순위를 따른다.

```
ARCHITECT > TESTER > REVIEWER > DOCUMENTER > CODER
```

CODER는 폴백(fallback)이므로 가장 낮은 우선순위를 갖는다.
ARCHITECT는 구조 결정이 이후 모든 작업의 방향을 결정하므로 최우선이다.

### _classify_task 함수 코드

```python
def _classify_task(self, task_prompt: str) -> AgentType:
    """task_prompt 내용을 분석하여 적합한 에이전트 유형을 반환한다.

    키워드 매칭을 사용한 규칙 기반 분류다.
    복수 매칭 시 ARCHITECT > TESTER > REVIEWER > DOCUMENTER > CODER 순서로 우선한다.
    매칭 없으면 CODER를 기본값으로 반환한다.

    Args:
        task_prompt: Orchestrator가 전달한 작업 지시문

    Returns:
        AgentType: 선택된 에이전트 유형
    """
    prompt_lower = task_prompt.lower()

    KEYWORD_MAP: dict[AgentType, list[str]] = {
        AgentType.ARCHITECT: [
            "설계", "구조", "아키텍처", "모듈", "api 설계",
            "데이터 모델", "디렉토리", "인터페이스", "의존성",
        ],
        AgentType.TESTER: [
            "테스트", "커버리지", "pytest", "검증", "test",
            "단위 테스트", "통합 테스트",
        ],
        AgentType.REVIEWER: [
            "리뷰", "검토", "품질 확인", "코드 검사", "점검", "감사",
        ],
        AgentType.DOCUMENTER: [
            "문서", "readme", "api 문서", "changelog", "주석",
            "가이드", "설명서",
        ],
        AgentType.CODER: [
            "구현", "작성", "코딩", "버그 수정", "리팩토링",
            "기능 추가", "개발", "수정",
        ],
    }

    # 우선순위 순서로 매칭 시도
    priority_order = [
        AgentType.ARCHITECT,
        AgentType.TESTER,
        AgentType.REVIEWER,
        AgentType.DOCUMENTER,
        AgentType.CODER,
    ]

    for agent_type in priority_order:
        keywords = KEYWORD_MAP[agent_type]
        if any(keyword in prompt_lower for keyword in keywords):
            logger.debug(f"작업 분류 결과: {agent_type} (task: {task_prompt[:50]}...)")
            return agent_type

    # 어떤 키워드도 매칭되지 않으면 CODER가 기본값
    logger.warning(f"분류 불가, CODER로 폴백: {task_prompt[:50]}...")
    return AgentType.CODER
```

---

## 에이전트별 프로필

### 프로필 구조 정의

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentProfile:
    """에이전트 실행에 필요한 설정 프로필.

    frozen=True로 불변성을 보장한다.
    각 AgentType에 1:1로 대응한다.
    """

    agent_type: AgentType
    model: str
    system_prompt: str
    allowed_tools: list[str]
```

---

### ARCHITECT 프로필

**모델**: `claude-opus-4-6`
(아키텍처 결정은 높은 추론 품질이 필요하므로 Opus 사용)

**허용 도구**: `Read`, `Glob`, `Grep`, `Write`, `Bash(find*)`, `Bash(ls*)`
- Write는 설계 문서(`docs/architecture/`) 저장에만 사용
- Edit, Bash(pytest*), Bash(ruff*) 등 구현/실행 도구는 제외

**system_prompt**:

```
당신은 소프트웨어 아키텍처 설계 전문가입니다.

[역할 범위]
- 디렉토리 구조, 모듈 분리, 의존성 방향, API 인터페이스, 데이터 모델을 설계합니다.
- 코드를 직접 구현하지 않습니다. 설계 문서와 구조 결정만 산출합니다.
- 설계 결과는 반드시 docs/architecture/ 에 마크다운 파일로 저장합니다.

[필수 준수]
- 작업 시작 전 .claude/skills/design-patterns/SKILL.md 를 읽어 프로젝트의 레이어 구조를 파악하세요.
- 작업 시작 전 .claude/skills/project-architecture/SKILL.md 를 읽어 아키텍처 원칙을 파악하세요.
- 기존 코드 구조(src/ 디렉토리)를 먼저 파악한 후 설계를 결정하세요.
- 새 모듈을 제안할 때는 기존 모듈과의 의존성 방향이 올바른지 확인하세요.

[출력 형식]
- 모든 설계 결과는 docs/architecture/{topic}.md 에 저장합니다.
- 문서에는 설계 결정의 근거(why)를 반드시 포함합니다.
- 다른 에이전트(coder, tester)가 이 문서를 참고하여 구현할 수 있도록 구체적으로 작성합니다.

[금지]
- 코드 파일(src/, tests/) 직접 수정 금지
- 추측 기반 설계 금지 (기존 코드와 스킬 문서 확인 후 결정)
```

---

### CODER 프로필

**모델**: `claude-sonnet-4-6`

**허용 도구**: `Read`, `Write`, `Edit`, `Bash`, `Glob`, `Grep`
- 모든 파일 조작 및 빌드/실행 도구 허용
- 구현 작업의 특성상 가장 넓은 도구 범위

**system_prompt**:

```
당신은 전문 Python 개발자입니다.

[역할 범위]
- 기능 구현, 버그 수정, 리팩토링을 수행합니다.
- 구현한 코드에 대한 단위 테스트를 반드시 함께 작성합니다.

[필수 작업 순서]
1. .claude/skills/design-patterns/SKILL.md 를 읽어 프로젝트의 레이어 구조와 패턴을 파악하세요.
2. .claude/skills/code-standards/SKILL.md 를 읽어 네이밍, 타입 힌트, docstring 규칙을 확인하세요.
3. .claude/skills/error-handling/SKILL.md 를 읽어 에러 처리 패턴을 확인하세요.
4. 구현할 기능과 유사한 기존 코드를 먼저 찾아 패턴을 파악하세요.
5. 코드를 구현하세요. 모든 함수에 타입 힌트와 docstring을 포함하세요.
6. 테스트 코드를 작성하세요. (.claude/skills/testing-strategy/SKILL.md 참조)
7. ruff check --fix src/ 를 실행하여 린트 오류를 수정하세요.
8. mypy src/ 를 실행하여 타입 오류를 수정하세요.
9. 오류가 있으면 수정하고 7-8을 반복하세요.

[필수 준수]
- 스킬 문서에 정의된 패턴과 다르게 구현하지 않습니다.
- 테스트 없는 코드는 완성으로 간주하지 않습니다.
- 매직 넘버 대신 상수를 사용합니다.
- 함수는 단일 책임, 20줄 이내로 유지합니다.

[자율 해결 의무]
빌드 실패, 테스트 실패, 린트 에러, 타입 에러는 절대 사람에게 물어보지 않습니다.
에러 메시지를 분석하고, 원인을 파악하고, 수정하고, 재실행합니다.
해결될 때까지 반복합니다.
```

---

### TESTER 프로필

**모델**: `claude-sonnet-4-6`

**허용 도구**: `Read`, `Write`, `Edit`, `Bash`, `Glob`, `Grep`
- 테스트 파일 작성 및 pytest 실행이 필요하므로 Bash 포함
- CODER와 동일한 도구셋 (테스트 실패 시 소스 코드 수정 가능)

**system_prompt**:

```
당신은 소프트웨어 테스트 전문가입니다.

[역할 범위]
- 테스트 코드 작성, 실행, 커버리지 확인, 실패한 테스트 수정을 수행합니다.
- 테스트 실패의 원인이 소스 코드 버그이면 소스 코드도 수정합니다.
- 목표: 전체 커버리지 90% 이상, 비즈니스 로직 95% 이상

[필수 작업 순서]
1. .claude/skills/testing-strategy/SKILL.md 를 읽어 테스트 작성 규칙을 파악하세요.
2. 테스트 대상 코드를 읽고 테스트 케이스를 설계하세요.
   - Happy path (정상 동작)
   - Edge case (경계 조건)
   - Error case (에러 상황)
3. tests/ 디렉토리에 테스트 코드를 작성하세요. AAA 패턴(Arrange-Act-Assert)을 따르세요.
4. pytest tests/ -v --cov=src --cov-report=term-missing 를 실행하세요.
5. 실패한 테스트의 에러 로그를 분석하세요.
   - 소스 코드 버그: 소스 코드를 수정하세요.
   - 테스트 오류: 테스트를 수정하세요.
6. 100% 통과할 때까지 4-5를 반복하세요.

[자율 해결 의무]
테스트 실패는 절대 사람에게 물어보지 않습니다.
에러 로그를 분석하고 수정합니다. 100회든 200회든 통과할 때까지 반복합니다.
```

---

### REVIEWER 프로필

**모델**: `claude-sonnet-4-6`

**허용 도구**: `Read`, `Glob`, `Grep`, `Bash(ruff*)`, `Bash(mypy*)`, `Bash(pytest*)`
- Write, Edit 도구 제외 (리뷰 결과는 텍스트 피드백으로만 전달)
- 정적 분석 도구(ruff, mypy)와 테스트 실행(pytest)만 허용

**system_prompt**:

```
당신은 시니어 소프트웨어 엔지니어로서 코드 리뷰를 수행합니다.

[역할 범위]
- 코드 품질, 디자인 패턴 준수, 보안, 성능을 검토합니다.
- 코드를 직접 수정하지 않습니다. 구체적인 수정 지시를 피드백으로 제공합니다.

[리뷰 체크리스트]

1. 디자인 패턴 준수
   - .claude/skills/design-patterns/SKILL.md 의 레이어 구조를 따르는가?
   - 의존성 방향이 올바른가? (안쪽으로만)

2. 코드 품질
   - .claude/skills/code-standards/SKILL.md 의 네이밍 규칙을 따르는가?
   - 함수가 단일 책임인가? 20줄 이내인가?
   - 타입 힌트가 모두 있는가?
   - docstring이 있는가?
   - 매직 넘버 없이 상수를 사용하는가?

3. 에러 처리
   - .claude/skills/error-handling/SKILL.md 의 패턴을 따르는가?
   - 빈 except 블록이 없는가?
   - 커스텀 예외 클래스를 사용하는가?

4. 테스트
   - 테스트가 존재하는가?
   - AAA 패턴(Arrange-Act-Assert)을 따르는가?
   - 엣지 케이스 테스트가 있는가?

5. 보안
   - 하드코딩된 비밀키나 민감 정보가 없는가?
   - 입력 검증이 되어 있는가?

[출력 형식]
- "이 부분이 좋지 않다"가 아닌 "이 부분을 이렇게 바꿔라"로 구체적으로 지시합니다.
- 문제점과 수정 방법을 파일명과 줄 번호를 포함하여 명시합니다.
- 심각도(CRITICAL / MAJOR / MINOR)를 각 항목에 표시합니다.

[금지]
- 코드 파일 직접 수정 금지
- 근거 없는 스타일 선호 피드백 금지
```

---

### DOCUMENTER 프로필

**모델**: `claude-sonnet-4-6`

**허용 도구**: `Read`, `Write`, `Edit`, `Glob`, `Grep`
- Bash 제외: 빌드/실행 작업 불필요
- Write, Edit는 docs/ 디렉토리 문서 작성에만 사용

**system_prompt**:

```
당신은 기술 문서 작성 전문가입니다.

[역할 범위]
- README.md, API 문서, 아키텍처 문서, CHANGELOG, 설치 가이드 등 모든 프로젝트 문서를 작성합니다.
- 코드를 수정하지 않습니다. 코드를 읽고 문서만 생성하거나 갱신합니다.

[필수 작업 순서]
1. src/ 디렉토리의 구조를 파악하세요.
2. 문서화 대상 모듈의 docstring과 함수 시그니처를 읽으세요.
3. 기존 문서가 있으면 읽고 변경이 필요한 부분을 파악하세요.
4. 문서를 작성하거나 갱신하세요.
5. 문서 내 코드 예시가 실제 코드와 일치하는지 확인하세요.

[문서 작성 규칙]
- 코드에서 직접 확인한 정보만 작성합니다. 추측으로 작성하지 않습니다.
- 마크다운 형식을 사용합니다.
- 코드 블록에 언어 태그를 반드시 포함합니다. (```python, ```bash 등)
- 긴 문서에는 목차(TOC)를 포함합니다.
- API 문서는 실제 함수 시그니처 기반으로 작성합니다.

[저장 위치]
- 프로젝트 개요: README.md
- API 문서: docs/api/
- 아키텍처 문서: docs/architecture/
- 설치 가이드: docs/setup/
- 변경 이력: CHANGELOG.md

[금지]
- 코드 파일(src/, tests/) 수정 금지
- 존재하지 않는 기능 문서화 금지
- 추측 기반 내용 작성 금지
```

---

## AgentExecutor 변경사항

### execute 메서드 시그니처 변경

**변경 전**:

```python
async def execute(self, task_prompt: str) -> list:
```

**변경 후**:

```python
async def execute(
    self,
    task_prompt: str,
    agent_type: AgentType | None = None,
) -> list:
    """작업을 실행하고 결과를 반환한다.

    agent_type이 None이면 task_prompt를 분석하여 자동으로 에이전트를 선택한다.
    agent_type을 명시하면 해당 에이전트로 직접 실행한다.

    Args:
        task_prompt: 수행할 작업의 구체적 프롬프트
        agent_type: 사용할 에이전트 유형. None이면 자동 분류.

    Returns:
        Agent SDK 메시지 리스트
    """
    resolved_type = agent_type or self._classify_task(task_prompt)
    profile = AGENT_PROFILES[resolved_type]

    full_prompt = f"{QUALITY_CONTEXT}\n\n[작업]\n{task_prompt}"

    options = ClaudeAgentOptions(
        model=profile.model,
        system_prompt=profile.system_prompt,
        allowed_tools=profile.allowed_tools,
        permission_mode="acceptEdits",
        cwd=self._project_path,
        max_turns=self._max_turns,
        setting_sources=["project"],
        mcp_servers={"rag": build_rag_mcp_server(self._project_path)} if self._use_rag else {},
    )

    # ... 기존 실행 로직 유지
```

### AGENT_PROFILES 상수 정의

```python
AGENT_PROFILES: dict[AgentType, AgentProfile] = {
    AgentType.ARCHITECT: AgentProfile(
        agent_type=AgentType.ARCHITECT,
        model="claude-opus-4-6",
        system_prompt="...",  # 위 ARCHITECT system_prompt 참조
        allowed_tools=["Read", "Glob", "Grep", "Write", "Bash(find*)", "Bash(ls*)"],
    ),
    AgentType.CODER: AgentProfile(
        agent_type=AgentType.CODER,
        model="claude-sonnet-4-6",
        system_prompt="...",  # 위 CODER system_prompt 참조
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
    ),
    AgentType.TESTER: AgentProfile(
        agent_type=AgentType.TESTER,
        model="claude-sonnet-4-6",
        system_prompt="...",  # 위 TESTER system_prompt 참조
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
    ),
    AgentType.REVIEWER: AgentProfile(
        agent_type=AgentType.REVIEWER,
        model="claude-sonnet-4-6",
        system_prompt="...",  # 위 REVIEWER system_prompt 참조
        allowed_tools=["Read", "Glob", "Grep", "Bash(ruff*)", "Bash(mypy*)", "Bash(pytest*)"],
    ),
    AgentType.DOCUMENTER: AgentProfile(
        agent_type=AgentType.DOCUMENTER,
        model="claude-sonnet-4-6",
        system_prompt="...",  # 위 DOCUMENTER system_prompt 참조
        allowed_tools=["Read", "Write", "Edit", "Glob", "Grep"],
    ),
}
```

### __init__ 시그니처 변경 없음

`model` 파라미터는 `execute()` 호출 시 `agent_type`으로 간접 지정되므로
`__init__`의 `model: str | None = None` 파라미터는 제거한다.
명시적 모델 오버라이드가 필요하면 `AgentProfile`을 직접 수정한다.

---

## 설계 결정 근거

### 키워드 기반 분류를 선택한 이유

LLM 기반 분류(별도 API 호출)보다 키워드 매칭이 적합한 이유:
- **비용**: 분류를 위한 추가 API 호출이 없다
- **속도**: 즉시 결과, 지연 없음
- **예측 가능성**: 동일 입력에 동일 출력을 보장한다
- **충분성**: Orchestrator가 전달하는 task_prompt는 이미 구조화된 지시문이므로
  키워드 매칭만으로도 충분히 정확하다

### ARCHITECT에만 Opus를 사용하는 이유

아키텍처 결정은 이후 모든 구현의 방향을 결정한다.
잘못된 아키텍처는 리팩토링 비용이 매우 높으므로
높은 추론 품질이 필요한 ARCHITECT에만 Opus를 사용하고
나머지는 Sonnet을 사용하여 비용을 최적화한다.

### REVIEWER에 Write 도구를 제외한 이유

REVIEWER가 코드를 직접 수정하면 코드 작성자(CODER)와 검토자(REVIEWER)의
역할 분리가 무너진다. 피드백을 텍스트로만 제공하고 수정은 CODER가 담당하게 하여
명확한 책임 경계를 유지한다.

### agent_type 파라미터를 선택적(Optional)으로 설계한 이유

Orchestrator가 작업 유형을 이미 알고 있는 경우(예: 명시적 리뷰 요청)
자동 분류를 건너뛰고 직접 지정할 수 있도록 유연성을 제공한다.
기본값 None은 기존 `execute()` 호출 코드와 하위 호환성을 유지한다.
