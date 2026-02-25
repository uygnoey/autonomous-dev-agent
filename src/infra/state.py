"""SQLite 기반 프로젝트 상태 관리.

aiosqlite로 비동기 접근. 원자적 저장(트랜잭션).
기존 ProjectState API를 유지하면서 SQLite 백엔드를 추가한다.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime

import aiosqlite

from src.utils.state import PhaseType, ProjectState

__all__ = ["PhaseType", "ProjectState", "StateStore"]

_CREATE_PROJECT_STATE = """
CREATE TABLE IF NOT EXISTS project_state (
    id INTEGER PRIMARY KEY,
    spec_hash TEXT UNIQUE,
    state_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_CREATE_AGENT_SESSIONS = """
CREATE TABLE IF NOT EXISTS agent_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_type TEXT NOT NULL,
    task_prompt TEXT NOT NULL,
    result_summary TEXT,
    success INTEGER NOT NULL DEFAULT 1,
    iteration INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


def _now_iso() -> str:
    """현재 시각을 ISO 8601 UTC 문자열로 반환한다."""
    return datetime.now(tz=UTC).isoformat()


def _spec_hash(spec: str) -> str:
    """스펙 문자열의 SHA-256 해시를 반환한다."""
    return hashlib.sha256(spec.encode()).hexdigest()


def _state_to_json(state: ProjectState) -> str:
    """ProjectState를 JSON 문자열로 직렬화한다."""
    data = asdict(state)
    data["phase"] = state.phase.value
    return json.dumps(data, ensure_ascii=False)


def _state_from_json(text: str) -> ProjectState:
    """JSON 문자열에서 ProjectState를 역직렬화한다."""
    data = json.loads(text)
    data["phase"] = PhaseType(data["phase"])
    data.setdefault("language", "")
    data.setdefault("framework", "")
    return ProjectState(**data)


class StateStore:
    """SQLite 기반 프로젝트 상태 저장소.

    비동기 aiosqlite를 사용하여 트랜잭션으로 원자적 저장을 보장한다.
    """

    def __init__(self, db_path: str) -> None:
        """저장소를 초기화한다.

        Args:
            db_path: SQLite 데이터베이스 파일 경로
        """
        self._db_path = db_path

    async def init_db(self) -> None:
        """데이터베이스 스키마를 초기화한다."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(_CREATE_PROJECT_STATE)
            await db.execute(_CREATE_AGENT_SESSIONS)
            await db.commit()

    async def save_state(self, state: ProjectState) -> None:
        """ProjectState를 JSON으로 직렬화하여 SQLite에 저장한다.

        spec_hash를 기준으로 UPSERT한다.

        Args:
            state: 저장할 ProjectState 인스턴스
        """
        hash_val = _spec_hash(state.spec)
        state_json = _state_to_json(state)
        updated_at = _now_iso()

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO project_state (spec_hash, state_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(spec_hash) DO UPDATE SET
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (hash_val, state_json, updated_at),
            )
            await db.commit()

    async def load_state(self, spec: str) -> ProjectState | None:
        """스펙 해시로 ProjectState를 복원한다.

        Args:
            spec: 스펙 문자열 (해시 키로 사용)

        Returns:
            복원된 ProjectState, 없으면 None
        """
        hash_val = _spec_hash(spec)
        async with aiosqlite.connect(self._db_path) as db, db.execute(
            "SELECT state_json FROM project_state WHERE spec_hash = ?",
            (hash_val,),
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            return None
        return _state_from_json(row[0])

    async def record_session(
        self,
        agent_type: str,
        task: str,
        result_summary: str,
        success: bool,
        iteration: int,
    ) -> None:
        """에이전트 세션 실행 기록을 저장한다.

        Args:
            agent_type: 에이전트 종류 (예: "coder", "tester")
            task: 실행한 작업 프롬프트
            result_summary: 결과 요약 문자열
            success: 성공 여부
            iteration: 현재 반복 횟수
        """
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO agent_sessions
                    (agent_type, task_prompt, result_summary, success, iteration, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (agent_type, task, result_summary, int(success), iteration, _now_iso()),
            )
            await db.commit()

    async def get_recent_sessions(self, n: int = 10) -> list[dict[str, object]]:
        """최근 n개의 세션 기록을 반환한다.

        Args:
            n: 조회할 세션 수

        Returns:
            세션 기록 딕셔너리 리스트 (최신순)
        """
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT agent_type, task_prompt, result_summary, success, iteration, created_at
                FROM agent_sessions
                ORDER BY id DESC
                LIMIT ?
                """,
                (n,),
            ) as cursor:
                rows = await cursor.fetchall()

        return [dict(row) for row in rows]
