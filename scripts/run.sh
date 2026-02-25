#!/bin/bash
# 자율 개발 에이전트 실행 스크립트
# 토큰 한도 도달 시에도 재시작하여 이어서 진행한다.

set -e

SPEC_FILE="${1:?스펙 파일 경로를 입력하세요. 예: ./scripts/run.sh spec.md}"

if [ ! -f "$SPEC_FILE" ]; then
    echo "❌ 스펙 파일이 없습니다: $SPEC_FILE"
    exit 1
fi

# .env 로드
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Agent Teams 활성화
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1

echo "=== 자율 개발 에이전트 시작 ==="
echo "스펙 파일: $SPEC_FILE"
echo "프로젝트: $(pwd)"
echo ""

# 메인 루프: 프로세스가 종료되면 재시작 (토큰 한도 대기 포함)
MAX_RESTARTS=50
RESTART_COUNT=0

while [ $RESTART_COUNT -lt $MAX_RESTARTS ]; do
    echo "[시작 #$((RESTART_COUNT + 1))]"
    
    python -m src.orchestrator.main "$SPEC_FILE"
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ]; then
        echo "✅ 정상 완료!"
        break
    fi
    
    RESTART_COUNT=$((RESTART_COUNT + 1))
    echo ""
    echo "⚠️  프로세스 종료 (코드: $EXIT_CODE). 60초 후 재시작..."
    echo "   재시작 횟수: $RESTART_COUNT / $MAX_RESTARTS"
    echo ""
    sleep 60
done

if [ $RESTART_COUNT -ge $MAX_RESTARTS ]; then
    echo "❌ 최대 재시작 횟수 초과."
fi
