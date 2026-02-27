#!/bin/bash
# 원클릭 설치 스크립트 - adev 자율 개발 에이전트
# 사용법:
#   1. git clone 후: cd autonomous-dev-agent && ./scripts/install.sh
#   2. 원격 설치: curl -fsSL https://raw.githubusercontent.com/uygnoey/autonomous-dev-agent/main/scripts/install.sh | bash
#   3. 또는: wget -qO- https://raw.githubusercontent.com/uygnoey/autonomous-dev-agent/main/scripts/install.sh | bash

set -e

PROJECT_NAME="autonomous-dev-agent"
PYTHON_VERSION="3.12"
REPO_URL="https://github.com/uygnoey/autonomous-dev-agent.git"
INSTALL_DIR="$HOME/$PROJECT_NAME"

# 색상 정의 / Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  Autonomous Dev Agent — 설치${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# 운영체제 감지 / Detect OS
OS="$(uname -s)"
case "${OS}" in
    Linux*)     PLATFORM=Linux;;
    Darwin*)    PLATFORM=macOS;;
    *)          PLATFORM="UNKNOWN:${OS}"
esac

echo -e "${BLUE}플랫폼: ${PLATFORM}${NC}"
echo ""

# ============================================================================
# 설치 모드 감지 / Detect install mode
# ============================================================================
if [ -f "pyproject.toml" ] && [ -d "src" ]; then
    INSTALL_MODE="local"
    PROJECT_DIR="$(pwd)"
    echo -e "${GREEN}로컬 설치 모드${NC} — ${PROJECT_DIR}"
else
    INSTALL_MODE="remote"
    PROJECT_DIR="$INSTALL_DIR"
    echo -e "${GREEN}원격 설치 모드${NC} — ${PROJECT_DIR}"
fi
echo ""

# ============================================================================
# 필수 도구 설치 함수 / Tool installation functions
# ============================================================================

install_homebrew_if_needed() {
    if [ "$PLATFORM" = "macOS" ] && ! command -v brew &> /dev/null; then
        echo -e "${YELLOW}Homebrew 설치 중...${NC}"
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        if [ -f "/opt/homebrew/bin/brew" ]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        elif [ -f "/usr/local/bin/brew" ]; then
            eval "$(/usr/local/bin/brew shellenv)"
        fi
    fi
}

install_git() {
    if command -v git &> /dev/null; then
        echo -e "${GREEN}✅ Git: $(git --version)${NC}"
        return
    fi

    echo -e "${YELLOW}Git 설치 중...${NC}"
    if [ "$PLATFORM" = "macOS" ]; then
        install_homebrew_if_needed
        brew install git
    elif [ "$PLATFORM" = "Linux" ]; then
        if command -v apt-get &> /dev/null; then
            sudo apt-get update && sudo apt-get install -y git
        elif command -v dnf &> /dev/null; then
            sudo dnf install -y git
        elif command -v yum &> /dev/null; then
            sudo yum install -y git
        else
            echo -e "${RED}Git을 수동으로 설치해주세요.${NC}"
            exit 1
        fi
    fi
    echo -e "${GREEN}✅ Git 설치 완료: $(git --version)${NC}"
}

install_python() {
    if command -v python3.12 &> /dev/null; then
        PYTHON_CMD="python3.12"
        echo -e "${GREEN}✅ Python: $($PYTHON_CMD --version)${NC}"
        return
    elif command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
        PYTHON_VER=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
        PYTHON_MAJOR=$(echo "$PYTHON_VER" | cut -d. -f1)
        PYTHON_MINOR=$(echo "$PYTHON_VER" | cut -d. -f2)
        if [ "$PYTHON_MAJOR" -ge 3 ] && [ "$PYTHON_MINOR" -ge 12 ]; then
            echo -e "${GREEN}✅ Python: $($PYTHON_CMD --version)${NC}"
            return
        fi
    fi

    echo -e "${YELLOW}Python 3.12 설치 중...${NC}"
    if [ "$PLATFORM" = "macOS" ]; then
        install_homebrew_if_needed
        brew install python@3.12
        PYTHON_CMD="python3.12"
    elif [ "$PLATFORM" = "Linux" ]; then
        if command -v apt-get &> /dev/null; then
            sudo apt-get update
            sudo apt-get install -y software-properties-common
            sudo add-apt-repository -y ppa:deadsnakes/ppa
            sudo apt-get update
            sudo apt-get install -y python3.12 python3.12-venv python3.12-dev
            PYTHON_CMD="python3.12"
        elif command -v yum &> /dev/null; then
            sudo yum install -y python312
            PYTHON_CMD="python3.12"
        else
            echo -e "${RED}Python 3.12을 수동으로 설치해주세요.${NC}"
            exit 1
        fi
    fi
    echo -e "${GREEN}✅ Python 설치 완료: $($PYTHON_CMD --version)${NC}"
}

install_uv() {
    if command -v uv &> /dev/null; then
        echo -e "${GREEN}✅ uv: $(uv --version)${NC}"
        return
    fi

    echo -e "${YELLOW}uv 패키지 매니저 설치 중...${NC}"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"

    SHELL_RC=""
    if [ -f "$HOME/.zshrc" ]; then
        SHELL_RC="$HOME/.zshrc"
    elif [ -f "$HOME/.bashrc" ]; then
        SHELL_RC="$HOME/.bashrc"
    fi

    if [ -n "$SHELL_RC" ] && ! grep -q '.cargo/bin' "$SHELL_RC" 2>/dev/null; then
        echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> "$SHELL_RC"
    fi
    echo -e "${GREEN}✅ uv 설치 완료: $(uv --version)${NC}"
}

# ============================================================================
# [1/6] 필수 도구 설치
# ============================================================================
echo -e "${BLUE}━━━ [1/6] 필수 도구 설치 ━━━${NC}"

if [ "$INSTALL_MODE" = "remote" ]; then
    install_git
fi
install_python
install_uv
echo ""

# ============================================================================
# [2/6] 프로젝트 다운로드 (원격 모드만)
# ============================================================================
echo -e "${BLUE}━━━ [2/6] 프로젝트 준비 ━━━${NC}"

if [ "$INSTALL_MODE" = "remote" ]; then
    if [ -d "$PROJECT_DIR" ]; then
        echo -e "${YELLOW}기존 설치 감지: $PROJECT_DIR${NC}"
        read -p "삭제 후 재설치? (y/N): " -n 1 -r < /dev/tty
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$PROJECT_DIR"
        else
            echo -e "${YELLOW}설치 중단.${NC}"
            exit 0
        fi
    fi
    git clone "$REPO_URL" "$PROJECT_DIR"
    cd "$PROJECT_DIR"
    echo -e "${GREEN}✅ 프로젝트 다운로드 완료${NC}"
else
    echo -e "${GREEN}✅ 로컬 디렉토리 사용${NC}"
fi
echo ""

# ============================================================================
# [3/6] 가상환경 + 의존성
# ============================================================================
echo -e "${BLUE}━━━ [3/6] 가상환경 + 의존성 설치 ━━━${NC}"

if [ ! -d ".venv" ]; then
    uv venv --python "$PYTHON_VERSION"
fi
uv pip install -e ".[dev]"
echo -e "${GREEN}✅ 의존성 설치 완료${NC}"
echo ""

# ============================================================================
# [4/6] API 키 설정
# ============================================================================
echo -e "${BLUE}━━━ [4/6] API 키 설정 ━━━${NC}"

# .env 기본 생성
if [ ! -f .env ]; then
    cat > .env << 'ENVEOF'
# Autonomous Dev Agent 설정
CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
CLAUDE_CODE_SUBAGENT_MODEL=claude-sonnet-4-6
ENVEOF
    chmod 600 .env
fi

if grep -q "^ANTHROPIC_API_KEY=sk-" .env 2>/dev/null && ! grep -q "your-key-here" .env 2>/dev/null; then
    echo -e "${GREEN}✅ API 키가 이미 설정되어 있습니다${NC}"
else
    echo ""
    echo -e "  ${YELLOW}1)${NC} API 키 직접 입력"
    echo -e "  ${YELLOW}2)${NC} 브라우저에서 API 키 발급"
    echo -e "  ${YELLOW}3)${NC} 나중에 설정"
    echo ""
    read -p "선택 (1/2/3): " -n 1 -r AUTH_CHOICE < /dev/tty
    echo ""
    read -r < /dev/tty 2>/dev/null || true

    case "$AUTH_CHOICE" in
        1)
            echo -e "${CYAN}https://console.anthropic.com/settings/keys 에서 발급${NC}"
            echo ""
            read -s -r -p "API Key: " API_KEY < /dev/tty
            echo ""

            if [[ "$API_KEY" == sk-ant-* ]]; then
                if grep -q "ANTHROPIC_API_KEY" .env 2>/dev/null; then
                    sed -i.bak "s|.*ANTHROPIC_API_KEY.*|ANTHROPIC_API_KEY=$API_KEY|" .env
                    rm -f .env.bak
                else
                    echo "ANTHROPIC_API_KEY=$API_KEY" >> .env
                fi
                chmod 600 .env
                unset API_KEY
                echo -e "${GREEN}✅ API 키 저장 완료${NC}"
            else
                unset API_KEY
                echo -e "${YELLOW}유효하지 않은 키 형식. 나중에 .env에서 설정하세요.${NC}"
            fi
            ;;
        2)
            CONSOLE_URL="https://console.anthropic.com/settings/keys"
            echo -e "${CYAN}${CONSOLE_URL}${NC}"

            # OS별 브라우저 열기 / Open browser by OS
            if [ "$(uname -s)" = "Darwin" ]; then
                open "$CONSOLE_URL" 2>/dev/null || true
            elif command -v xdg-open &> /dev/null; then
                xdg-open "$CONSOLE_URL" 2>/dev/null || true
            elif command -v wslview &> /dev/null; then
                wslview "$CONSOLE_URL" 2>/dev/null || true
            fi

            echo ""
            echo -e "${YELLOW}API 키를 발급받은 후 입력하세요:${NC}"
            read -s -r -p "API Key: " API_KEY < /dev/tty
            echo ""

            if [[ "$API_KEY" == sk-ant-* ]]; then
                if grep -q "ANTHROPIC_API_KEY" .env 2>/dev/null; then
                    sed -i.bak "s|.*ANTHROPIC_API_KEY.*|ANTHROPIC_API_KEY=$API_KEY|" .env
                    rm -f .env.bak
                else
                    echo "ANTHROPIC_API_KEY=$API_KEY" >> .env
                fi
                chmod 600 .env
                unset API_KEY
                echo -e "${GREEN}✅ API 키 저장 완료${NC}"
            else
                unset API_KEY
                echo -e "${YELLOW}유효하지 않은 키 형식. 나중에 .env에서 설정하세요.${NC}"
            fi
            ;;
        3|*)
            echo -e "${YELLOW}건너뜁니다. 나중에 .env에 ANTHROPIC_API_KEY=sk-ant-... 추가${NC}"
            ;;
    esac
fi
echo ""

# ============================================================================
# [5/6] CLI 전역 등록
# ============================================================================
echo -e "${BLUE}━━━ [5/6] adev CLI 전역 등록 ━━━${NC}"

if command -v uv &> /dev/null && uv tool install -e "$PROJECT_DIR" 2>/dev/null; then
    echo -e "${GREEN}✅ adev 전역 설치 완료 (uv tool)${NC}"
elif pip install --user -e "$PROJECT_DIR" 2>/dev/null; then
    echo -e "${GREEN}✅ adev 전역 설치 완료 (pip)${NC}"
elif pip3 install --user -e "$PROJECT_DIR" 2>/dev/null; then
    echo -e "${GREEN}✅ adev 전역 설치 완료 (pip3)${NC}"
else
    VENV_BIN="$PROJECT_DIR/.venv/bin"
    SHELL_RC=""
    if [ -n "$ZSH_VERSION" ] || [ -f "$HOME/.zshrc" ]; then
        SHELL_RC="$HOME/.zshrc"
    elif [ -f "$HOME/.bashrc" ]; then
        SHELL_RC="$HOME/.bashrc"
    elif [ -f "$HOME/.bash_profile" ]; then
        SHELL_RC="$HOME/.bash_profile"
    fi

    if [ -n "$SHELL_RC" ] && ! grep -q "$VENV_BIN" "$SHELL_RC" 2>/dev/null; then
        echo "" >> "$SHELL_RC"
        echo "# Autonomous Dev Agent CLI" >> "$SHELL_RC"
        echo "export PATH=\"$VENV_BIN:\$PATH\"" >> "$SHELL_RC"
        echo -e "${GREEN}✅ PATH 추가: $SHELL_RC${NC}"
    fi
fi

if command -v adev &> /dev/null; then
    echo -e "${GREEN}✅ adev 사용 가능${NC}"
else
    echo -e "${YELLOW}새 터미널에서 adev 명령어를 사용할 수 있습니다.${NC}"
fi
echo ""

# ============================================================================
# [6/6] 검증
# ============================================================================
echo -e "${BLUE}━━━ [6/6] 설치 검증 ━━━${NC}"

PASS=0
FAIL=0

for pkg in anthropic claude_agent_sdk textual pytest; do
    if uv run python -c "import $pkg" 2>/dev/null; then
        echo -e "${GREEN}  ✅ ${pkg}${NC}"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}  ❌ ${pkg}${NC}"
        FAIL=$((FAIL + 1))
    fi
done

echo ""
if uv run pytest tests/ -q --tb=no 2>/dev/null; then
    echo -e "${GREEN}✅ 테스트 전체 통과${NC}"
else
    echo -e "${YELLOW}일부 테스트 실패 (실행에는 문제 없음)${NC}"
fi

# ============================================================================
# 완료
# ============================================================================
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✅ 설치 완료${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${CYAN}실행:${NC}"
if [ "$INSTALL_MODE" = "remote" ]; then
    echo -e "  cd $PROJECT_DIR"
fi
echo -e "  ${GREEN}adev${NC}                          — TUI 모드"
echo -e "  ${GREEN}adev /path/to/project${NC}         — 프로젝트 지정"
echo -e "  ${GREEN}adev /path/to/project spec.md${NC} — 스펙 파일 지정"
echo ""
echo -e "${CYAN}삭제:${NC}"
echo -e "  ${YELLOW}./scripts/uninstall.sh${NC}"
echo ""
