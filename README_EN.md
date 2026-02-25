# Autonomous Development Agent

An autonomous infinite-loop development system that uses Claude API for reasoning and Claude Agent SDK for execution.

**[한국어 README](README.md)**

## Overview

Provide a spec, and the agent develops autonomously until all tests pass and all features are complete.

```
Human (provides spec)
    ↓
Orchestrator
    ├── Planner      ← Claude API (brain: decides next task)
    ├── Executor     ← Claude Agent SDK (hands: writes code)
    ├── Verifier     ← Claude Agent SDK (validates: tests/lint/types)
    ├── Classifier   ← Claude API (judges: Critical vs Non-Critical)
    └── RAG MCP      ← Codebase pattern search (ensures consistency)
```

## How It Works

1. **Spec confirmation** — Discuss with human, write to `spec.md`
2. **Autonomous loop** — Orchestrator iterates:
   - Planner decides the next task
   - Executor writes/modifies code
   - Verifier runs pytest + ruff + mypy
   - Failures are fixed autonomously — no human interruption
3. **Documentation** — Documenter agent auto-generates docs after completion

## Installation

### Requirements

**No requirements needed!** 🎉

The installation script automatically installs:
- Python 3.12 (if missing or old version)
- Git (if missing)
- uv package manager
- Node.js (for Claude Code)
- Claude Code CLI (optional)

### 🚀 Fully Automated Installation (Highly Recommended)

**You don't need anything pre-installed!**

```bash
# Remote installation on macOS/Linux
curl -fsSL https://raw.githubusercontent.com/USER/REPO/main/scripts/install.sh | bash

# Or using wget
wget -qO- https://raw.githubusercontent.com/USER/REPO/main/scripts/install.sh | bash
```

**If you already have Git:**

```bash
git clone <repo-url>
cd autonomous-dev-agent
./scripts/install.sh
```

The script automatically:
- ✅ **Installs Git** (if missing)
- ✅ **Installs Python 3.12** (if missing or old version)
- ✅ **Installs Node.js** (if missing)
- ✅ **Installs uv package manager**
- ✅ **Installs Claude Code** (optional)
- ✅ Creates virtual environment
- ✅ Installs dependencies
- ✅ Creates .env file
- ✅ Runs verification tests

### Manual Installation

If you prefer manual installation:

```bash
# Clone the repository
git clone <repo-url>
cd autonomous-dev-agent

# Create virtual environment and install dependencies
uv venv .venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
```

## Usage

### 1. Write the Spec

Write your project specification in `spec.md`:

```markdown
## Functional Requirements
1. User registration/login (email + password)
2. TODO item CRUD
...

## Tech Stack
- Python 3.12
- FastAPI
- PostgreSQL
```

### 2. Run the Agent

```bash
python -m src.orchestrator.main spec.md
```

The agent automatically:
- Creates project structure
- Implements features
- Writes and runs tests
- Fixes lint/type errors
- Generates documentation on completion

### 3. Completion Report

After all tests pass, the agent delivers a completion report along with any accumulated non-critical questions.

## Development

```bash
# Run tests
pytest tests/ -v --cov=src

# Lint
ruff check src/

# Type check
mypy src/
```

## Project Structure

```
autonomous-dev-agent/
├── src/
│   ├── orchestrator/            # Autonomous loop brain
│   │   ├── main.py              # Main loop
│   │   ├── planner.py           # Decides next task (Claude API)
│   │   ├── issue_classifier.py  # Critical/Non-Critical classification
│   │   └── token_manager.py     # Rate limit backoff logic
│   ├── agents/                  # Agent SDK execution layer
│   │   ├── executor.py          # Code writing/modification
│   │   └── verifier.py          # Test/lint/type validation
│   ├── rag/                     # RAG code search system
│   │   ├── indexer.py           # Codebase indexer
│   │   └── mcp_server.py        # MCP server (search_code tool)
│   └── utils/
│       ├── state.py             # Project state (supports resume)
│       └── logger.py            # Structured logging
├── .claude/
│   ├── skills/                  # Coding guidelines for RAG
│   └── agents/                  # Sub-agent definitions
├── tests/                       # Unit/integration tests
├── config/default.yaml          # Default configuration
└── spec.md                      # Project spec to develop
```

## Issue Classification Rules

| Category | Handling |
|----------|----------|
| Ambiguous spec, missing API keys, spec contradictions, security decisions | **Ask human immediately** |
| Build failures, test failures, lint/type errors | **Agent fixes autonomously** |
| UI details, naming choices, performance optimization direction | **Collected and delivered after completion** |

## Architecture Decisions

### Dual Claude Architecture
- **Claude API** (via `anthropic`): Used for reasoning tasks — planning next steps, classifying issues. Stateless, called per iteration.
- **Claude Agent SDK** (via `claude-agent-sdk`): Used for execution tasks — writing code, running commands, verifying results. Stateful, runs multi-turn sessions.

### RAG via In-Process MCP Server
The `search_code` MCP tool runs in-process (no separate server), giving the executor agent the ability to search existing codebase patterns before writing new code. This ensures consistency across implementations.

### Resumable State
`ProjectState` is persisted to `.claude/state.json` after every iteration. If the process is interrupted (token limit, crash), it resumes from where it left off.

## License

MIT
