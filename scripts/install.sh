#!/bin/bash
# 원클릭 설치 스크립트 - 모든 필수 요구사항 자동 설치
# 사용법:
#   1. git clone 후: cd autonomous-dev-agent && ./scripts/install.sh
#   2. 원격 설치: curl -fsSL https://raw.githubusercontent.com/USER/REPO/main/scripts/install.sh | bash
#   3. 또는: wget -qO- https://raw.githubusercontent.com/USER/REPO/main/scripts/install.sh | bash

set -e

PROJECT_NAME="autonomous-dev-agent"
PYTHON_VERSION="3.12"
REPO_URL="https://github.com/USER/REPO.git"  # 실제 GitHub 저장소 URL로 교체 필요
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
        read -p "삭제하고 다시 설치하시겠습니까? (y/N): " -n 1 -r
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
# 4. .env 파일 생성
# ============================================================================
echo -e "${BLUE}━━━ [4/8] 환경 설정 파일 생성 ━━━${NC}"

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo -e "${GREEN}✅ .env 파일 생성됨 (.env.example에서 복사)${NC}"
    else
        cat > .env << 'EOF'
# Anthropic API Key (선택 - 없으면 Claude Code 세션 사용)
# ANTHROPIC_API_KEY=sk-ant-your-key-here

# Agent Teams 활성화
CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1

# 서브에이전트 모델
CLAUDE_CODE_SUBAGENT_MODEL=claude-sonnet-4-6
EOF
        echo -e "${GREEN}✅ .env 파일 생성됨 (기본 템플릿)${NC}"
    fi
else
    echo -e "${GREEN}✅ .env 파일이 이미 존재합니다${NC}"
fi
echo ""

# ============================================================================
# 5. Claude Code 설치 (선택)
# ============================================================================
echo -e "${BLUE}━━━ [5/8] Claude Code 설치 (선택) ━━━${NC}"

install_claude_code
echo ""

# ============================================================================
# 6. CLI 명령어 등록
# ============================================================================
echo -e "${BLUE}━━━ [6/8] CLI 명령어 등록 ━━━${NC}"

echo -e "${YELLOW}📦 adev 명령어 설치 중...${NC}"

# CLI 바이너리 위치 확인
VENV_BIN="$PROJECT_DIR/.venv/bin"
if [ -d "$VENV_BIN" ]; then
    if [ -f "$VENV_BIN/adev" ]; then
        echo -e "${GREEN}✅ adev 명령어 등록 완료${NC}"
        echo -e "${CYAN}   실행: adev 또는 autonomous-dev${NC}"
    else
        echo -e "${YELLOW}⚠️  명령어 등록 실패. 'uv run python -m src.cli' 사용${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  가상환경 bin 디렉토리를 찾을 수 없습니다.${NC}"
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
