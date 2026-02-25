# 배포 가이드

Autonomous Dev Agent를 서버 또는 다른 환경에 배포하는 방법.

---

## 요구사항

| 항목 | 최소 사양 |
|------|-----------|
| Python | 3.12 이상 |
| 메모리 | 2GB 이상 권장 (RAG 벡터 검색 사용 시 4GB+) |
| 디스크 | 500MB (의존성 포함) |
| 네트워크 | Anthropic API 접근 가능 |

---

## 1. 로컬 설치

```bash
git clone <repo-url>
cd autonomous-dev-agent
./scripts/install.sh
```

설치 완료 후:
```bash
adev /path/to/project
```

---

## 2. 원격 서버 (SSH) 배포

### 2-1. 서버에서 직접 설치

```bash
# 서버 접속
ssh user@server

# 저장소 클론
git clone <repo-url>
cd autonomous-dev-agent

# 원클릭 설치
./scripts/install.sh

# API 키 설정
echo "ANTHROPIC_API_KEY=sk-ant-..." >> .env
```

### 2-2. TUI 실행 (tmux 권장)

SSH 환경에서 TUI를 사용하려면 tmux 세션을 사용한다:

```bash
tmux new-session -s adev

# tmux 내에서
adev /path/to/project spec.md
```

### 2-3. TUI 없이 CLI 모드로 실행

서버에서 TUI 없이 Orchestrator만 실행:

```bash
# spec.md 파일 준비
cat > spec.md << 'SPEC'
# 프로젝트 이름
...스펙 내용...
SPEC

# CLI 모드 실행 (토큰 한도 대기 자동 포함)
./scripts/run.sh spec.md
```

---

## 3. Docker 배포

### Dockerfile 예시

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# uv 설치
RUN pip install uv

# 의존성 설치
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

# 소스 코드 복사
COPY src/ ./src/
COPY .claude/ ./.claude/
COPY config/ ./config/

# 환경 변수 (런타임 주입)
ENV ANTHROPIC_API_KEY=""

CMD ["uv", "run", "python", "-m", "src.orchestrator.main", "spec.md"]
```

```bash
# 빌드
docker build -t autonomous-dev-agent .

# 실행 (spec.md를 볼륨으로 마운트)
docker run -it \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -v $(pwd)/spec.md:/app/spec.md \
  -v $(pwd)/output:/app/output \
  autonomous-dev-agent
```

---

## 4. 인증 방법

### 방법 A: Anthropic API 키

```bash
# .env 파일에 설정
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

- Planner, IssueClassifier, SpecBuilder, TokenManager가 직접 API 호출
- AgentExecutor, Verifier는 claude-agent-sdk가 동일 키 사용

### 방법 B: Claude Code 세션 (Subscription)

```bash
# 인증 (최초 1회)
claude init

# .env에서 API 키 제거 (또는 주석 처리)
# ANTHROPIC_API_KEY=...
```

- `call_claude_for_text`가 자동으로 SDK 경로 사용
- `claude-agent-sdk`가 로컬 claude 세션 활용

---

## 5. 환경 변수 전체 목록

| 변수명 | 필수 | 기본값 | 설명 |
|--------|------|--------|------|
| `ANTHROPIC_API_KEY` | 선택 | — | Anthropic API 키. 없으면 Claude Code 세션 사용 |
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | 선택 | `0` | `1`로 설정 시 Agent Teams 활성화 (`.claude/settings.json`에 이미 설정됨) |
| `CLAUDE_CODE_SUBAGENT_MODEL` | 선택 | `claude-sonnet-4-6` | 서브에이전트 모델 ID |

---

## 6. 프로덕션 권장 설정

### 재시작 자동화 (systemd)

```ini
# /etc/systemd/system/adev.service
[Unit]
Description=Autonomous Dev Agent
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/autonomous-dev-agent
ExecStart=/home/ubuntu/autonomous-dev-agent/scripts/run.sh /home/ubuntu/project/spec.md
Restart=on-failure
RestartSec=60
Environment="ANTHROPIC_API_KEY=sk-ant-..."

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable adev
sudo systemctl start adev
sudo journalctl -u adev -f  # 로그 확인
```

### 로그 확인

에이전트 로그는 Python logging 모듈로 출력된다:

```bash
# 실시간 로그
./scripts/run.sh spec.md 2>&1 | tee agent.log

# 로그 레벨 조정
LOG_LEVEL=DEBUG ./scripts/run.sh spec.md
```
