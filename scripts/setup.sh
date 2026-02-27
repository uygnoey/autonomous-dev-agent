#!/bin/bash
# 자율 개발 에이전트 환경 설정 스크립트

set -e

echo "=== 자율 개발 에이전트 환경 설정 ==="

# 1. uv 설치 확인
if ! command -v uv &> /dev/null; then
    echo "📦 uv 설치..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# 2. Python 가상환경 생성 (uv 사용)
if [ ! -d ".venv" ]; then
    echo "🐍 Python 가상환경 생성..."
    uv venv --python 3.12
fi

# 3. .env 파일 확인
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
    else
        echo "ANTHROPIC_API_KEY=" > .env
    fi
    chmod 600 .env
    echo "⚠️  .env 파일을 생성했습니다."
    echo "   ANTHROPIC_API_KEY (API 키 사용 시) 또는 claude init (subscription 사용 시) 중 선택:"
    echo "   - API 키: vim .env"
    echo "   - subscription: claude init"
fi

# 4. 의존성 설치 (uv 사용)
echo "📦 의존성 설치..."
uv pip install -e ".[dev]"

# 5. 시스템 전역 CLI 설치 (어디서든 adev 실행 가능)
echo "🔧 adev CLI 전역 설치..."
pip install -e "." 2>/dev/null || pip3 install -e "." 2>/dev/null || {
    echo "   ⚠️  전역 설치 실패. 가상환경 내에서만 adev 사용 가능합니다."
}

# 6. Claude Code 설치 확인
if ! command -v claude &> /dev/null; then
    echo "📦 Claude Code 설치..."
    npm install -g @anthropic-ai/claude-code
fi

# 7. Claude Agent SDK 설치 확인
uv pip show claude-agent-sdk &>/dev/null || {
    echo "📦 Claude Agent SDK 설치..."
    uv pip install claude-agent-sdk
}

# 8. Agent Teams 환경변수 확인
echo "✅ Agent Teams 설정 확인..."
grep -q "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS" .claude/settings.json && \
    echo "   Agent Teams: 활성화됨" || \
    echo "   ⚠️  .claude/settings.json에 Agent Teams 설정이 없습니다"

# 9. tmux 설치 확인 (Agent Teams에 필요)
if ! command -v tmux &> /dev/null; then
    echo "⚠️  tmux가 설치되어 있지 않습니다. Agent Teams의 split-pane 모드에 필요합니다."
    echo "   sudo apt install tmux  (Ubuntu/Debian)"
    echo "   brew install tmux      (macOS)"
fi

# 10. 검증
echo ""
echo "🔍 환경 검증..."
claude doctor 2>/dev/null && echo "   Claude Code: OK" || echo "   ⚠️  claude doctor 실행 실패"
uv run python -c "import anthropic; print('   anthropic SDK: OK')" 2>/dev/null || echo "   ⚠️  anthropic 미설치"
uv run python -c "import claude_agent_sdk; print('   Agent SDK: OK')" 2>/dev/null || echo "   ⚠️  Agent SDK 미설치"

echo ""
echo "=== 설정 완료 ==="
echo ""
echo "인증 방법 선택:"
echo "  A. API 키 방식: .env 파일에 ANTHROPIC_API_KEY 설정"
echo "  B. Subscription 방식: claude init 으로 로그인 (API 키 불필요)"
echo ""
echo "실행 방법:"
echo "  1. 스펙 파일 작성: spec.md"
echo "  2. 실행: ./scripts/run.sh spec.md"
echo "  3. 또는: uv run python -m src.orchestrator.main spec.md"
