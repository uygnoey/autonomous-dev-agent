"""검증기.

Claude Agent SDK를 사용하여 테스트, 린트, 타입체크, 빌드를 실행하고
결과를 구조화된 형태로 반환한다.

언어/프레임워크는 .claude/project-info.json 에서 우선 읽고,
파일이 없으면 에이전트가 프로젝트 파일을 탐지하여 자동 결정한다.
"""

import json
from pathlib import Path

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class Verifier:
    """프로젝트 검증을 수행하는 검증기."""

    def __init__(self, project_path: str):
        self._project_path = project_path

    def _load_project_info(self) -> dict[str, str]:
        """architect가 저장한 project-info.json 을 읽는다. 없으면 빈 dict 반환."""
        info_path = Path(self._project_path) / ".claude" / "project-info.json"
        if not info_path.exists():
            return {}
        try:
            data = json.loads(info_path.read_text())
            return dict(data) if isinstance(data, dict) else {}
        except Exception:
            return {}

    async def verify_all(self) -> dict:
        """모든 검증을 수행하고 결과를 반환한다.

        .claude/project-info.json 에 언어 정보가 있으면 그걸 사용하고,
        없으면 에이전트가 프로젝트 파일을 분석하여 언어를 자동 감지한다.

        Returns:
            {
                "tests_total": int,
                "tests_passed": int,
                "tests_failed": int,
                "lint_errors": int,
                "type_errors": int,
                "build_success": bool,
                "issues": list[str],
            }
        """
        info = self._load_project_info()
        language = info.get("language", "")
        test_tool = info.get("test_tool", "")
        lint_tool = info.get("lint_tool", "")
        build_command = info.get("build_command", "")

        if language:
            lang_hint = (
                f"이 프로젝트는 언어={language}, "
                f"테스트={test_tool or '자동 감지'}, "
                f"린트={lint_tool or '자동 감지'}, "
                f"빌드={build_command or '자동 감지'} 로 설정되어 있습니다.\n"
                "위 도구를 그대로 사용하세요."
            )
        else:
            lang_hint = (
                "project-info.json 가 없습니다. "
                "pyproject.toml, package.json, go.mod, Cargo.toml 등 "
                "프로젝트 파일을 확인하여 언어와 도구를 직접 감지하세요."
            )

        options = ClaudeAgentOptions(
            system_prompt=(
                "당신은 프로젝트 검증 전문가입니다. "
                "테스트, 린트, 타입체크, 빌드를 실행하고 결과를 정확히 보고하세요. "
                "수정은 하지 마세요."
            ),
            allowed_tools=["Read", "Bash", "Glob", "Grep"],
            permission_mode="acceptEdits",
            cwd=self._project_path,
            max_turns=30,
        )

        verify_prompt = f"""
프로젝트를 검증하세요.

## 언어/도구 정보
{lang_hint}

## 언어별 검증 명령어 참고

### Python
```
pytest tests/ -v --tb=short 2>&1 || true
ruff check src/ 2>&1 || true
mypy src/ --ignore-missing-imports 2>&1 || true
python -c "import src" 2>&1 || true
```

### JavaScript / TypeScript
```
npm test 2>&1 || true
npx eslint src/ 2>&1 || true
npx tsc --noEmit 2>&1 || true
npm run build 2>&1 || true
```

### Go
```
go test ./... 2>&1 || true
go vet ./... 2>&1 || true
golangci-lint run 2>&1 || true
go build ./... 2>&1 || true
```

### Rust
```
cargo test 2>&1 || true
cargo clippy -- -D warnings 2>&1 || true
cargo build 2>&1 || true
```

### Java (Maven)
```
mvn test 2>&1 || true
mvn checkstyle:check 2>&1 || true
mvn compile 2>&1 || true
```

### Java (Gradle)
```
./gradlew test 2>&1 || true
./gradlew check 2>&1 || true
./gradlew build 2>&1 || true
```

### Ruby
```
bundle exec rspec 2>&1 || true
bundle exec rubocop 2>&1 || true
```

## 결과 출력

검증 완료 후 반드시 아래 JSON 형식으로 마지막에 출력하세요:
```json
{{
    "tests_total": <숫자>,
    "tests_passed": <숫자>,
    "tests_failed": <숫자>,
    "lint_errors": <숫자>,
    "type_errors": <숫자>,
    "build_success": <true/false>,
    "issues": ["이슈1", "이슈2"]
}}
```
"""

        results = []
        async for message in query(prompt=verify_prompt, options=options):
            results.append(message)

        return self._parse_results(results)

    def _parse_results(self, messages: list) -> dict:
        """Agent SDK 결과에서 검증 정보를 추출한다."""
        default = {
            "tests_total": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "lint_errors": 0,
            "type_errors": 0,
            "build_success": False,
            "issues": [],
        }

        for msg in messages:
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        text = block.text
                        if "```json" in text:
                            try:
                                json_str = text.split("```json")[1].split("```")[0]
                                parsed = json.loads(json_str.strip())
                                return {**default, **parsed}
                            except (json.JSONDecodeError, IndexError):
                                continue

        logger.warning("검증 결과 파싱 실패. 기본값 반환.")
        return default
