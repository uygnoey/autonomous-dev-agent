#!/bin/bash
# Autonomous Dev Agent 삭제 스크립트
# 사용법:
#   ./scripts/uninstall.sh          — 패키지만 삭제 (소스 유지)
#   ./scripts/uninstall.sh --all    — 패키지 + 프로젝트 디렉토리 전체 삭제

set -e

# 색상 정의 / Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

REMOVE_ALL=false
if [ "$1" = "--all" ]; then
    REMOVE_ALL=true
fi

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  Autonomous Dev Agent — 삭제${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# 프로젝트 디렉토리 감지 / Detect project directory
if [ -f "pyproject.toml" ] && grep -q "autonomous-dev-agent" pyproject.toml 2>/dev/null; then
    PROJECT_DIR="$(pwd)"
elif [ -d "$HOME/autonomous-dev-agent" ]; then
    PROJECT_DIR="$HOME/autonomous-dev-agent"
else
    PROJECT_DIR=""
fi

# ============================================================================
# 1. pip / uv tool 패키지 삭제
# ============================================================================
echo -e "${BLUE}━━━ [1/5] 패키지 삭제 ━━━${NC}"

# uv tool 삭제 시도
if command -v uv &> /dev/null; then
    if uv tool list 2>/dev/null | grep -q "autonomous-dev-agent"; then
        echo -e "${YELLOW}📦 uv tool에서 삭제 중...${NC}"
        uv tool uninstall autonomous-dev-agent 2>/dev/null || true
        echo -e "${GREEN}✅ uv tool 삭제 완료${NC}"
    fi
fi

# pip 삭제 (시스템 + 사용자)
if pip show autonomous-dev-agent &>/dev/null 2>&1; then
    echo -e "${YELLOW}📦 pip에서 삭제 중...${NC}"
    pip uninstall autonomous-dev-agent -y 2>/dev/null || true
    echo -e "${GREEN}✅ pip 삭제 완료${NC}"
fi

if pip3 show autonomous-dev-agent &>/dev/null 2>&1; then
    echo -e "${YELLOW}📦 pip3에서 삭제 중...${NC}"
    pip3 uninstall autonomous-dev-agent -y 2>/dev/null || true
    echo -e "${GREEN}✅ pip3 삭제 완료${NC}"
fi

echo ""

# ============================================================================
# 2. CLI 명령어 확인 및 제거
# ============================================================================
echo -e "${BLUE}━━━ [2/5] CLI 명령어 정리 ━━━${NC}"

ADEV_PATH=$(which adev 2>/dev/null || true)
if [ -n "$ADEV_PATH" ]; then
    echo -e "${YELLOW}⚠️  adev가 아직 존재합니다: ${ADEV_PATH}${NC}"
    # 심볼릭 링크인 경우 삭제
    if [ -L "$ADEV_PATH" ]; then
        rm -f "$ADEV_PATH"
        echo -e "${GREEN}✅ 심볼릭 링크 삭제: ${ADEV_PATH}${NC}"
    else
        echo -e "${YELLOW}   수동 삭제가 필요할 수 있습니다: rm ${ADEV_PATH}${NC}"
    fi
else
    echo -e "${GREEN}✅ adev 명령어가 이미 제거되었습니다${NC}"
fi

AUTODEV_PATH=$(which autonomous-dev 2>/dev/null || true)
if [ -n "$AUTODEV_PATH" ] && [ -L "$AUTODEV_PATH" ]; then
    rm -f "$AUTODEV_PATH"
    echo -e "${GREEN}✅ 심볼릭 링크 삭제: ${AUTODEV_PATH}${NC}"
fi

echo ""

# ============================================================================
# 3. PATH 항목 정리 (쉘 rc 파일)
# ============================================================================
echo -e "${BLUE}━━━ [3/5] PATH 정리 ━━━${NC}"

for RC_FILE in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.bash_profile"; do
    if [ -f "$RC_FILE" ]; then
        if grep -q "Autonomous Dev Agent" "$RC_FILE" 2>/dev/null; then
            # "# Autonomous Dev Agent CLI" 주석과 그 다음 줄(export PATH) 삭제
            sed -i.bak '/# Autonomous Dev Agent/,+1d' "$RC_FILE"
            rm -f "${RC_FILE}.bak"
            echo -e "${GREEN}✅ PATH 항목 제거: ${RC_FILE}${NC}"
        fi
    fi
done

echo ""

# ============================================================================
# 4. 캐시 및 가상환경 삭제
# ============================================================================
echo -e "${BLUE}━━━ [4/5] 캐시 정리 ━━━${NC}"

if [ -n "$PROJECT_DIR" ] && [ -d "$PROJECT_DIR" ]; then
    # .rag_cache 삭제
    if [ -d "$PROJECT_DIR/.rag_cache" ]; then
        rm -rf "$PROJECT_DIR/.rag_cache"
        echo -e "${GREEN}✅ .rag_cache 삭제${NC}"
    fi

    # .venv 삭제
    if [ -d "$PROJECT_DIR/.venv" ]; then
        rm -rf "$PROJECT_DIR/.venv"
        echo -e "${GREEN}✅ .venv 삭제${NC}"
    fi

    # logs 삭제
    if [ -d "$PROJECT_DIR/logs" ]; then
        rm -rf "$PROJECT_DIR/logs"
        echo -e "${GREEN}✅ logs/ 삭제${NC}"
    fi

    # __pycache__ 삭제
    find "$PROJECT_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    echo -e "${GREEN}✅ __pycache__ 삭제${NC}"

    # .egg-info 삭제
    find "$PROJECT_DIR" -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
    echo -e "${GREEN}✅ .egg-info 삭제${NC}"
else
    echo -e "${YELLOW}⚠️  프로젝트 디렉토리를 찾을 수 없습니다${NC}"
fi

echo ""

# ============================================================================
# 5. 프로젝트 디렉토리 삭제 (--all 옵션)
# ============================================================================
echo -e "${BLUE}━━━ [5/5] 프로젝트 디렉토리 ━━━${NC}"

if [ "$REMOVE_ALL" = true ]; then
    if [ -n "$PROJECT_DIR" ] && [ -d "$PROJECT_DIR" ]; then
        echo -e "${RED}⚠️  프로젝트 전체를 삭제합니다: ${PROJECT_DIR}${NC}"
        read -p "정말 삭제하시겠습니까? (y/N): " -n 1 -r < /dev/tty
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$PROJECT_DIR"
            echo -e "${GREEN}✅ 프로젝트 디렉토리 삭제 완료${NC}"
        else
            echo -e "${YELLOW}   디렉토리 삭제를 건너뜁니다${NC}"
        fi
    fi
else
    echo -e "${CYAN}ℹ️  소스 코드는 유지됩니다${NC}"
    echo -e "${CYAN}   전체 삭제: ./scripts/uninstall.sh --all${NC}"
fi

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✅ 삭제 완료${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${CYAN}참고: Claude Code, Node.js, Python, uv 등 공유 도구는 삭제하지 않았습니다.${NC}"
echo -e "${CYAN}필요 시 수동으로 삭제하세요:${NC}"
echo -e "   npm uninstall -g @anthropic-ai/claude-code"
echo ""
