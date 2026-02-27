#!/bin/bash
# 원클릭 설치 스크립트 - 모든 필수 요구사항 자동 설치
# 사용법:
#   1. git clone 후: cd autonomous-dev-agent && ./scripts/install.sh
#   2. 원격 설치: curl -fsSL https://raw.githubusercontent.com/uygnoey/autonomous-dev-agent/main/scripts/install.sh | bash
#   3. 또는: wget -qO- https://raw.githubusercontent.com/uygnoey/autonomous-dev-agent/main/scripts/install.sh | bash

set -e

PROJECT_NAME="autonomous-dev-agent"
PYTHON_VERSION="3.12"
REPO_URL="https://github.com/uygnoey/autonomous-dev-agent.git"
INSTALL_DIR="$HOME/$PROJECT_NAME"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  🤖 Autonomous Dev Agent - 완전 자동 설치${NC}"
echo -e "${CYAN}     모든 필수 요구사항을 자동으로 설치합니다${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# 운영체제 감지
OS="$(uname -s)"
case "${OS}" in
    Linux*)     PLATFORM=Linux;;
    Darwin*)    PLATFORM=macOS;;
    *)          PLATFORM="UNKNOWN:${OS}"
esac

echo -e "${BLUE}🖥️  플랫폼: ${PLATFORM}${NC}"
echo ""

# ============================================================================
# 설치 모드 감지
# ============================================================================
if [ -f "pyproject.toml" ] && [ -d "src" ]; then
    # 로컬 모드: 이미 git clone된 디렉토리에서 실행
    INSTALL_MODE="local"
    PROJECT_DIR="$(pwd)"
    echo -e "${GREEN}📂 로컬 설치 모드${NC}"
    echo -e "   프로젝트 디렉토리: ${PROJECT_DIR}"
else
    # 원격 모드: curl/wget으로 스크립트만 다운로드하여 실행
    INSTALL_MODE="remote"
    PROJECT_DIR="$INSTALL_DIR"
    echo -e "${GREEN}🌐 원격 설치 모드${NC}"
    echo -e "   설치 위치: ${PROJECT_DIR}"
fi
echo ""

# ============================================================================
# 필수 도구 자동 설치 함수
# ============================================================================

install_homebrew_if_needed() {
    if [ "$PLATFORM" = "macOS" ]; then
        if ! command -v brew &> /dev/null; then
            echo -e "${YELLOW}🍺 Homebrew 설치 중...${NC}"
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

            # Homebrew PATH 추가
            if [ -f "/opt/homebrew/bin/brew" ]; then
                eval "$(/opt/homebrew/bin/brew shellenv)"
            elif [ -f "/usr/local/bin/brew" ]; then
                eval "$(/usr/local/bin/brew shellenv)"
            fi

            echo -e "${GREEN}✅ Homebrew 설치 완료${NC}"
        fi
    fi
}

install_git() {
    if ! command -v git &> /dev/null; then
        echo -e "${YELLOW}📦 Git 설치 중...${NC}"

        if [ "$PLATFORM" = "macOS" ]; then
            install_homebrew_if_needed
            brew install git
        elif [ "$PLATFORM" = "Linux" ]; then
            if command -v apt-get &> /dev/null; then
                sudo apt-get update
                sudo apt-get install -y git
            elif command -v yum &> /dev/null; then
                sudo yum install -y git
            elif command -v dnf &> /dev/null; then
                sudo dnf install -y git
            else
                echo -e "${RED}❌ 패키지 매니저를 찾을 수 없습니다. Git을 수동으로 설치해주세요.${NC}"
                exit 1
            fi
        fi

        echo -e "${GREEN}✅ Git 설치 완료: $(git --version)${NC}"
    else
        echo -e "${GREEN}✅ Git이 이미 설치되어 있습니다: $(git --version)${NC}"
    fi
}

install_python() {
    local needs_install=false

    if command -v python3.12 &> /dev/null; then
        PYTHON_CMD="python3.12"
        echo -e "${GREEN}✅ Python 3.12 발견: $($PYTHON_CMD --version)${NC}"
        return
    elif command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
        PYTHON_VER=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
        PYTHON_MAJOR=$(echo "$PYTHON_VER" | cut -d. -f1)
        PYTHON_MINOR=$(echo "$PYTHON_VER" | cut -d. -f2)

        if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 12 ]); then
            needs_install=true
        else
            echo -e "${GREEN}✅ Python $PYTHON_VER 사용 가능${NC}"
            return
        fi
    else
        needs_install=true
    fi

    if [ "$needs_install" = true ]; then
        echo -e "${YELLOW}🐍 Python 3.12 설치 중...${NC}"

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
                echo -e "${RED}❌ Python 3.12 자동 설치 실패. 수동으로 설치해주세요.${NC}"
                exit 1
            fi
        fi

        echo -e "${GREEN}✅ Python 설치 완료: $($PYTHON_CMD --version)${NC}"
    fi
}

install_nodejs() {
    if ! command -v node &> /dev/null; then
        echo -e "${YELLOW}📦 Node.js 설치 중...${NC}"

        if [ "$PLATFORM" = "macOS" ]; then
            install_homebrew_if_needed
            brew install node
        elif [ "$PLATFORM" = "Linux" ]; then
            if command -v apt-get &> /dev/null; then
                curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
                sudo apt-get install -y nodejs
            elif command -v yum &> /dev/null; then
                curl -fsSL https://rpm.nodesource.com/setup_lts.x | sudo bash -
                sudo yum install -y nodejs
            else
                echo -e "${YELLOW}⚠️  Node.js 자동 설치 실패. Claude Code 설치를 건너뜁니다.${NC}"
                return
            fi
        fi

        echo -e "${GREEN}✅ Node.js 설치 완료: $(node --version)${NC}"
    else
        echo -e "${GREEN}✅ Node.js가 이미 설치되어 있습니다: $(node --version)${NC}"
    fi
}

install_uv() {
    if ! command -v uv &> /dev/null; then
        echo -e "${YELLOW}📦 uv 패키지 매니저 설치 중...${NC}"
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
                echo -e "${GREEN}   PATH를 $SHELL_RC에 추가했습니다.${NC}"
            fi
        fi

        echo -e "${GREEN}✅ uv 설치 완료: $(uv --version)${NC}"
    else
        echo -e "${GREEN}✅ uv가 이미 설치되어 있습니다: $(uv --version)${NC}"
    fi
}

install_claude_code() {
    if ! command -v claude &> /dev/null; then
        echo -e "${YELLOW}📦 Claude Code 설치 중...${NC}"

        if command -v npm &> /dev/null; then
            npm install -g @anthropic-ai/claude-code
            echo -e "${GREEN}✅ Claude Code 설치 완료: $(claude --version)${NC}"
        else
            echo -e "${YELLOW}⚠️  npm이 없어 Claude Code 설치를 건너뜁니다.${NC}"
            echo -e "${YELLOW}   API 키 방식을 사용하시면 문제없습니다.${NC}"
        fi
    else
        echo -e "${GREEN}✅ Claude Code가 이미 설치되어 있습니다: $(claude --version)${NC}"
    fi
}

# ============================================================================
# 0. 필수 도구 설치
# ============================================================================
echo -e "${BLUE}━━━ [0/8] 필수 도구 설치 ━━━${NC}"
echo ""

# 원격 모드에서는 Git 필수
if [ "$INSTALL_MODE" = "remote" ]; then
    install_git
    echo ""
fi

# Python 3.12 설치
install_python
echo ""

# uv 설치
install_uv
echo ""

# Node.js 설치 (Claude Code를 위해)
install_nodejs
echo ""

# ============================================================================
# 1. 원격 모드인 경우 프로젝트 다운로드
# ============================================================================
if [ "$INSTALL_MODE" = "remote" ]; then
    echo -e "${BLUE}━━━ [1/8] 프로젝트 다운로드 ━━━${NC}"

    # 기존 디렉토리 확인
    if [ -d "$PROJECT_DIR" ]; then
        echo -e "${YELLOW}⚠️  기존 설치가 감지되었습니다: $PROJECT_DIR${NC}"
        read -p "삭제하고 다시 설치하시겠습니까? (y/N): " -n 1 -r < /dev/tty
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$PROJECT_DIR"
            echo -e "${GREEN}✅ 기존 디렉토리 삭제 완료${NC}"
        else
            echo -e "${YELLOW}설치를 중단합니다.${NC}"
            exit 0
        fi
    fi

    echo -e "${YELLOW}📥 프로젝트 다운로드 중...${NC}"
    git clone "$REPO_URL" "$PROJECT_DIR"

    cd "$PROJECT_DIR"
    echo -e "${GREEN}✅ 프로젝트 다운로드 완료${NC}"
    echo ""
else
    echo -e "${BLUE}━━━ [1/8] 프로젝트 다운로드 (건너뜀) ━━━${NC}"
    echo -e "${GREEN}✅ 로컬 디렉토리 사용${NC}"
    echo ""
fi

# ============================================================================
# 2. 가상환경 생성
# ============================================================================
echo -e "${BLUE}━━━ [2/8] Python 가상환경 생성 ━━━${NC}"

if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}🐍 .venv 생성 중...${NC}"
    uv venv --python "$PYTHON_VERSION"
    echo -e "${GREEN}✅ 가상환경 생성 완료${NC}"
else
    echo -e "${GREEN}✅ 가상환경이 이미 존재합니다${NC}"
fi
echo ""

# ============================================================================
# 3. 의존성 설치
# ============================================================================
echo -e "${BLUE}━━━ [3/8] 의존성 설치 ━━━${NC}"

echo -e "${YELLOW}📦 Python 패키지 설치 중...${NC}"
uv pip install -e ".[dev]"

echo -e "${GREEN}✅ 의존성 설치 완료${NC}"
echo ""

# ============================================================================
# 4. 인증 설정 (인터랙티브)
# ============================================================================
echo -e "${BLUE}━━━ [4/8] 인증 설정 ━━━${NC}"

# 기본 .env 파일 생성
if [ ! -f .env ]; then
    cat > .env << 'ENVEOF'
# Agent Teams 활성화
CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1

# 서브에이전트 모델
CLAUDE_CODE_SUBAGENT_MODEL=claude-sonnet-4-6
ENVEOF
    chmod 600 .env
fi

# 이미 API 키가 설정되어 있는지 확인
# 플레이스홀더(your-key-here)가 아닌 실제 키가 설정되어 있는지 확인
if grep -q "^ANTHROPIC_API_KEY=sk-" .env 2>/dev/null && ! grep -q "^ANTHROPIC_API_KEY=.*your-key-here" .env 2>/dev/null; then
    echo -e "${GREEN}✅ API 키가 이미 설정되어 있습니다${NC}"
else
    echo ""
    echo -e "${CYAN}━━━ 인증 방법을 선택하세요 ━━━${NC}"
    echo ""
    echo -e "  ${YELLOW}1)${NC} API 키 입력 (ANTHROPIC_API_KEY)"
    echo -e "  ${YELLOW}2)${NC} Claude 구독 로그인 (브라우저에서 인증)"
    echo -e "  ${YELLOW}3)${NC} 나중에 설정 (건너뛰기)"
    echo ""
    # /dev/tty에서 읽어 curl | bash 파이프 환경에서도 인터랙션 가능
    read -p "선택 (1/2/3): " -n 1 -r AUTH_CHOICE < /dev/tty
    echo ""
    read -r < /dev/tty 2>/dev/null || true  # -n 1 후 남은 개행문자 소비
    echo ""

    case "$AUTH_CHOICE" in
        1)
            echo -e "${YELLOW}🔑 Anthropic API 키를 입력하세요:${NC}"
            echo -e "${CYAN}   (https://console.anthropic.com/settings/keys 에서 발급)${NC}"
            echo ""
            # -s: 입력 내용 화면에 표시 안 함 (보안)
            read -s -r -p "API Key: " API_KEY < /dev/tty
            echo ""

            if [[ "$API_KEY" == sk-ant-* ]]; then
                # 기존 ANTHROPIC_API_KEY 줄이 있으면 교체, 없으면 추가
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
                echo -e "${YELLOW}⚠️  유효하지 않은 키 형식입니다. 나중에 .env 파일에서 설정하세요.${NC}"
            fi
            ;;
        2)
            echo -e "${YELLOW}🌐 브라우저에서 Claude 로그인을 진행합니다...${NC}"
            if command -v claude &> /dev/null; then
                claude init
                echo -e "${GREEN}✅ Claude 구독 인증 완료${NC}"
            else
                echo -e "${YELLOW}⚠️  Claude Code가 아직 설치되지 않았습니다.${NC}"
                echo -e "${YELLOW}   다음 단계에서 Claude Code 설치 후 'claude init'을 실행하세요.${NC}"
            fi
            ;;
        3|*)
            echo -e "${YELLOW}⏭️  인증 설정을 건너뜁니다.${NC}"
            echo -e "${CYAN}   나중에 설정하려면:${NC}"
            echo -e "${CYAN}   - API 키: .env 파일에 ANTHROPIC_API_KEY=sk-ant-... 추가${NC}"
            echo -e "${CYAN}   - 구독: claude init 실행${NC}"
            ;;
    esac
fi
echo ""

# ============================================================================
# 5. Claude Code 설치 (선택)
# ============================================================================
echo -e "${BLUE}━━━ [5/8] Claude Code 설치 (선택) ━━━${NC}"

install_claude_code
echo ""

# ============================================================================
# 6. CLI 명령어 전역 등록
# ============================================================================
echo -e "${BLUE}━━━ [6/8] CLI 명령어 전역 등록 ━━━${NC}"

echo -e "${YELLOW}📦 adev 명령어를 시스템 전역으로 설치 중...${NC}"

# uv tool 또는 pip으로 시스템 전역 설치
if command -v uv &> /dev/null && uv tool install -e "$PROJECT_DIR" 2>/dev/null; then
    echo -e "${GREEN}✅ adev 전역 설치 완료 (uv tool)${NC}"
elif pip install --user -e "$PROJECT_DIR" 2>/dev/null; then
    echo -e "${GREEN}✅ adev 전역 설치 완료 (pip --user)${NC}"
elif pip3 install --user -e "$PROJECT_DIR" 2>/dev/null; then
    echo -e "${GREEN}✅ adev 전역 설치 완료 (pip3 --user)${NC}"
else
    # pip 전역 설치 실패 시 PATH에 가상환경 bin 추가
    echo -e "${YELLOW}⚠️  pip 전역 설치 실패. PATH에 가상환경 추가합니다.${NC}"
    VENV_BIN="$PROJECT_DIR/.venv/bin"

    SHELL_RC=""
    if [ -n "$ZSH_VERSION" ] || [ -f "$HOME/.zshrc" ]; then
        SHELL_RC="$HOME/.zshrc"
    elif [ -f "$HOME/.bashrc" ]; then
        SHELL_RC="$HOME/.bashrc"
    elif [ -f "$HOME/.bash_profile" ]; then
        SHELL_RC="$HOME/.bash_profile"
    fi

    if [ -n "$SHELL_RC" ]; then
        if ! grep -q "$VENV_BIN" "$SHELL_RC" 2>/dev/null; then
            echo "" >> "$SHELL_RC"
            echo "# Autonomous Dev Agent CLI" >> "$SHELL_RC"
            echo "export PATH=\"$VENV_BIN:\$PATH\"" >> "$SHELL_RC"
            echo -e "${GREEN}✅ PATH 추가 완료: $SHELL_RC${NC}"
            echo -e "${YELLOW}   새 터미널에서 adev 명령어를 사용할 수 있습니다.${NC}"
        fi
    fi
fi

# 설치 확인
if command -v adev &> /dev/null; then
    echo -e "${GREEN}✅ adev 명령어 사용 가능${NC}"
    echo -e "${CYAN}   어디서든 실행: adev 또는 autonomous-dev${NC}"
else
    echo -e "${YELLOW}   새 터미널을 열면 adev 명령어를 사용할 수 있습니다.${NC}"
fi
echo ""

# ============================================================================
# 7. 환경 검증
# ============================================================================
echo -e "${BLUE}━━━ [7/8] 설치 검증 ━━━${NC}"

echo -e "${YELLOW}🔍 환경 검증 중...${NC}"

# Python 패키지 확인
if uv run python -c "import anthropic" 2>/dev/null; then
    echo -e "${GREEN}✅ anthropic SDK${NC}"
else
    echo -e "${RED}❌ anthropic SDK${NC}"
fi

if uv run python -c "import claude_agent_sdk" 2>/dev/null; then
    echo -e "${GREEN}✅ claude-agent-sdk${NC}"
else
    echo -e "${RED}❌ claude-agent-sdk${NC}"
fi

if uv run python -c "import textual" 2>/dev/null; then
    echo -e "${GREEN}✅ textual (TUI)${NC}"
else
    echo -e "${RED}❌ textual (TUI)${NC}"
fi

if uv run python -c "import pytest" 2>/dev/null; then
    echo -e "${GREEN}✅ pytest${NC}"
else
    echo -e "${RED}❌ pytest${NC}"
fi

echo ""

# ============================================================================
# 8. 테스트 실행
# ============================================================================
echo -e "${BLUE}━━━ [8/8] 테스트 실행 ━━━${NC}"

echo -e "${YELLOW}🧪 테스트 실행 중...${NC}"
if uv run pytest tests/ -q --tb=no 2>/dev/null; then
    echo -e "${GREEN}✅ 모든 테스트 통과${NC}"
else
    echo -e "${YELLOW}⚠️  일부 테스트 실패 (개발에는 문제 없음)${NC}"
fi

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✅ 설치 완료!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# 설치된 도구 요약
echo -e "${CYAN}📦 설치된 도구:${NC}"
echo -e "   ✅ Python: $($PYTHON_CMD --version)"
echo -e "   ✅ uv: $(uv --version)"
if command -v git &> /dev/null; then
    echo -e "   ✅ Git: $(git --version)"
fi
if command -v node &> /dev/null; then
    echo -e "   ✅ Node.js: $(node --version)"
fi
if command -v claude &> /dev/null; then
    echo -e "   ✅ Claude Code: $(claude --version)"
fi
echo ""

echo -e "${BLUE}📖 다음 단계:${NC}"
echo ""
echo "1. 인증 설정 (둘 중 하나 선택):"
echo -e "   ${YELLOW}- API 키: vim .env  (ANTHROPIC_API_KEY 설정)${NC}"
echo -e "   ${YELLOW}- Subscription: claude init${NC}"
echo ""
echo "2. 실행 방법:"
if [ "$INSTALL_MODE" = "remote" ]; then
    echo -e "   ${GREEN}cd $PROJECT_DIR${NC}"
fi
echo -e "   ${GREEN}- TUI 모드: adev${NC}"
echo -e "   ${GREEN}- 또는: autonomous-dev${NC}"
echo -e "   ${GREEN}- 프로젝트 지정: adev /path/to/project${NC}"
echo -e "   ${GREEN}- 스펙 파일 지정: adev /path/to/project spec.md${NC}"
echo ""
echo "3. 개발 명령어:"
echo -e "   ${YELLOW}- 테스트: uv run pytest tests/ -v --cov${NC}"
echo -e "   ${YELLOW}- 린트: uv run ruff check src/${NC}"
echo -e "   ${YELLOW}- 타입 체크: uv run mypy src/${NC}"
echo ""
echo -e "${BLUE}📚 문서: ${PROJECT_DIR}/docs/setup/development.md${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
