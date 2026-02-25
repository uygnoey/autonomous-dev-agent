#!/bin/bash
# 자율 개발 에이전트 환경 설정 스크립트

set -e

echo "=== 자율 개발 에이전트 환경 설정 ==="

# 1. Python 버전 확인
python3 --version || { echo "Python 3.12+ 필요"; exit 1; }

# 2. .env 파일 확인
if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚠️  .env 파일을 생성했습니다. ANTHROPIC_API_KEY를 설정하세요."
    echo "   vim .env"
fi

# 3. 의존성 설치
echo "📦 의존성 설치..."
pip install -e ".[dev]" --break-system-packages 2>/dev/null || pip install -e ".[dev]"

# 4. Claude Code 설치 확인
if ! command -v claude &> /dev/null; then
    echo "📦 Claude Code 설치..."
    npm install -g @anthropic-ai/claude-code
fi

# 5. Claude Code Agent SDK 설치 확인
pip show claude-agent-sdk &>/dev/null || {
    echo "📦 Claude Agent SDK 설치..."
    pip install claude-agent-sdk --break-system-packages 2>/dev/null || pip install claude-agent-sdk
}

# 6. Agent Teams 환경변수 확인
echo "✅ Agent Teams 설정 확인..."
grep -q "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS" .claude/settings.json && \
    echo "   Agent Teams: 활성화됨" || \
    echo "   ⚠️  .claude/settings.json에 Agent Teams 설정이 없습니다"

# 7. tmux 설치 확인 (Agent Teams에 필요)
if ! command -v tmux &> /dev/null; then
    echo "⚠️  tmux가 설치되어 있지 않습니다. Agent Teams의 split-pane 모드에 필요합니다."
    echo "   sudo apt install tmux  (Ubuntu/Debian)"
    echo "   brew install tmux      (macOS)"
fi

# 8. 검증
echo ""
echo "🔍 환경 검증..."
claude doctor 2>/dev/null && echo "   Claude Code: OK" || echo "   ⚠️  claude doctor 실행 실패"
python -c "import anthropic; print('   anthropic SDK: OK')" 2>/dev/null || echo "   ⚠️  anthropic 미설치"
python -c "import claude_agent_sdk; print('   Agent SDK: OK')" 2>/dev/null || echo "   ⚠️  Agent SDK 미설치"

echo ""
echo "=== 설정 완료 ==="
echo ""
echo "실행 방법:"
echo "  1. 스펙 파일 작성: spec.md"
echo "  2. 실행: ./scripts/run.sh spec.md"
echo "  3. 또는: python -m src.orchestrator.main spec.md"
