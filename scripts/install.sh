#!/bin/bash
# 원클릭 설치 스크립트 - 다른 컴퓨터에서 쉽게 설치하기 위한 스크립트

set -e

PROJECT_NAME="autonomous-dev-agent"
PYTHON_VERSION="3.12"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🤖 Autonomous Dev Agent - 원클릭 설치"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 운영체제 감지
OS="$(uname -s)"
case "${OS}" in
    Linux*)     PLATFORM=Linux;;
    Darwin*)    PLATFORM=macOS;;
    *)          PLATFORM="UNKNOWN:${OS}"
esac

echo "🖥️  플랫폼: ${PLATFORM}"
echo ""

# ============================================================================
# 1. Python 3.12 이상 확인
# ============================================================================
echo "━━━ [1/7] Python 버전 확인 ━━━"

if command -v python3.12 &> /dev/null; then
    PYTHON_CMD="python3.12"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
    PYTHON_VER=$(python3 --version | grep -oP '\d+\.\d+' || echo "0.0")
    if (( $(echo "$PYTHON_VER < 3.12" | bc -l) )); then
        echo "❌ Python 3.12 이상이 필요합니다. 현재: Python $PYTHON_VER"
        echo ""
        echo "설치 방법:"
        if [ "$PLATFORM" = "macOS" ]; then
            echo "  brew install python@3.12"
        elif [ "$PLATFORM" = "Linux" ]; then
            echo "  sudo apt update && sudo apt install python3.12"
        fi
        exit 1
    fi
else
    echo "❌ Python이 설치되어 있지 않습니다."
    exit 1
fi

echo "✅ Python: $($PYTHON_CMD --version)"
echo ""

# ============================================================================
# 2. uv 설치 확인 및 설치
# ============================================================================
echo "━━━ [2/7] uv 패키지 매니저 확인 ━━━"

if ! command -v uv &> /dev/null; then
    echo "📦 uv 설치 중..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # PATH 업데이트
    export PATH="$HOME/.cargo/bin:$PATH"

    # 쉘 설정 파일에 PATH 추가
    SHELL_RC=""
    if [ -f "$HOME/.bashrc" ]; then
        SHELL_RC="$HOME/.bashrc"
    elif [ -f "$HOME/.zshrc" ]; then
        SHELL_RC="$HOME/.zshrc"
    fi

    if [ -n "$SHELL_RC" ]; then
        if ! grep -q '.cargo/bin' "$SHELL_RC"; then
            echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> "$SHELL_RC"
            echo "   PATH를 $SHELL_RC에 추가했습니다."
        fi
    fi
fi

echo "✅ uv: $(uv --version)"
echo ""

# ============================================================================
# 3. 가상환경 생성
# ============================================================================
echo "━━━ [3/7] Python 가상환경 생성 ━━━"

if [ ! -d ".venv" ]; then
    echo "🐍 .venv 생성 중..."
    uv venv --python "$PYTHON_VERSION"
    echo "✅ 가상환경 생성 완료"
else
    echo "✅ 가상환경이 이미 존재합니다"
fi
echo ""

# ============================================================================
# 4. 의존성 설치
# ============================================================================
echo "━━━ [4/7] 의존성 설치 ━━━"

echo "📦 패키지 설치 중..."
uv pip install -e ".[dev]"

echo "✅ 의존성 설치 완료"
echo ""

# ============================================================================
# 5. .env 파일 생성
# ============================================================================
echo "━━━ [5/7] 환경 설정 파일 생성 ━━━"

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✅ .env 파일 생성됨 (.env.example에서 복사)"
    else
        cat > .env << 'EOF'
# Anthropic API Key (선택 - 없으면 Claude Code 세션 사용)
# ANTHROPIC_API_KEY=sk-ant-your-key-here

# Agent Teams 활성화
CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1

# 서브에이전트 모델
CLAUDE_CODE_SUBAGENT_MODEL=claude-sonnet-4-6
EOF
        echo "✅ .env 파일 생성됨 (기본 템플릿)"
    fi
    echo ""
    echo "⚠️  인증 방법 선택:"
    echo "   A. API 키: .env 파일에 ANTHROPIC_API_KEY 설정"
    echo "   B. Subscription: claude init 으로 로그인 (API 키 불필요)"
else
    echo "✅ .env 파일이 이미 존재합니다"
fi
echo ""

# ============================================================================
# 6. Claude Code 확인 (선택)
# ============================================================================
echo "━━━ [6/7] Claude Code 확인 (선택) ━━━"

if command -v claude &> /dev/null; then
    echo "✅ Claude Code: $(claude --version)"
else
    echo "⚠️  Claude Code가 설치되어 있지 않습니다"
    echo ""
    echo "Claude Code Subscription 사용 시 필요합니다."
    echo "설치 방법:"
    echo "  npm install -g @anthropic-ai/claude-code"
    echo ""
    echo "API 키 방식을 사용한다면 Claude Code 설치는 선택사항입니다."
fi
echo ""

# ============================================================================
# 7. 검증
# ============================================================================
echo "━━━ [7/7] 설치 검증 ━━━"

echo "🔍 환경 검증 중..."

# Python 패키지 확인
if uv run python -c "import anthropic" 2>/dev/null; then
    echo "✅ anthropic SDK"
else
    echo "❌ anthropic SDK"
fi

if uv run python -c "import claude_agent_sdk" 2>/dev/null; then
    echo "✅ claude-agent-sdk"
else
    echo "❌ claude-agent-sdk"
fi

if uv run python -c "import textual" 2>/dev/null; then
    echo "✅ textual (TUI)"
else
    echo "❌ textual (TUI)"
fi

if uv run python -c "import pytest" 2>/dev/null; then
    echo "✅ pytest"
else
    echo "❌ pytest"
fi

echo ""

# 테스트 실행
echo "🧪 테스트 실행 중..."
if uv run pytest tests/ -q --tb=no 2>/dev/null; then
    echo "✅ 모든 테스트 통과"
else
    echo "⚠️  일부 테스트 실패 (개발에는 문제 없음)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ 설치 완료!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📖 다음 단계:"
echo ""
echo "1. 인증 설정 (둘 중 하나 선택):"
echo "   - API 키: vim .env  (ANTHROPIC_API_KEY 설정)"
echo "   - Subscription: claude init"
echo ""
echo "2. 실행 방법:"
echo "   - TUI 모드: adev"
echo "   - 또는: autonomous-dev"
echo "   - 프로젝트 지정: adev /path/to/project"
echo "   - 스펙 파일 지정: adev /path/to/project spec.md"
echo ""
echo "3. 개발 명령어:"
echo "   - 테스트: uv run pytest tests/ -v --cov"
echo "   - 린트: uv run ruff check src/"
echo "   - 타입 체크: uv run mypy src/"
echo ""
echo "📚 문서: docs/setup/development.md"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
