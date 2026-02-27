#!/bin/bash
# 자율 개발 에이전트 개발 환경 설정 스크립트
# 이미 clone된 프로젝트에서 개발 환경을 빠르게 구성합니다.

set -e

echo "=== Autonomous Dev Agent — 개발 환경 설정 ==="

# 1. uv 설치 확인
if ! command -v uv &> /dev/null; then
    echo "uv 설치 중..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# 2. Python 가상환경 생성
if [ ! -d ".venv" ]; then
    echo "Python 가상환경 생성..."
    uv venv --python 3.12
fi

# 3. .env 파일 확인
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
    else
        cat > .env << 'EOF'
# Autonomous Dev Agent 설정
CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
CLAUDE_CODE_SUBAGENT_MODEL=claude-sonnet-4-6
EOF
    fi
    chmod 600 .env
    echo "  .env 파일을 생성했습니다."
    echo "  ANTHROPIC_API_KEY를 설정하세요: vim .env"
fi

# 4. 의존성 설치
echo "의존성 설치..."
uv pip install -e ".[dev]"

# 5. adev CLI 전역 설치
echo "adev CLI 전역 설치..."
pip install -e "." 2>/dev/null || pip3 install -e "." 2>/dev/null || {
    echo "  전역 설치 실패. 가상환경 내에서만 adev 사용 가능합니다."
}

# 6. 검증
echo ""
echo "환경 검증..."
uv run python -c "import anthropic; print('  anthropic SDK: OK')" 2>/dev/null || echo "  anthropic 미설치"
uv run python -c "import claude_agent_sdk; print('  Agent SDK: OK')" 2>/dev/null || echo "  Agent SDK 미설치"
uv run python -c "import textual; print('  textual TUI: OK')" 2>/dev/null || echo "  textual 미설치"

echo ""
echo "=== 설정 완료 ==="
echo ""
echo "실행: adev"
echo "삭제: ./scripts/uninstall.sh"
echo ""
