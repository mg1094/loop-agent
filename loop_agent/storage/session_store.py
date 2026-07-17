from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_DB_PATH = Path.cwd() / ".sessions" / "sessions.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT,
    tool_calls TEXT,
    tool_call_id TEXT,
    name TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_session_seq
    ON session_messages(session_id, seq);
"""


def _row_to_message(row: sqlite3.Row) -> Dict[str, Any]:
    role = row["role"]
    msg: Dict[str, Any] = {"role": role}
    if row["content"] is not None:
        msg["content"] = row["content"]
    if row["tool_calls"] is not None:
        msg["tool_calls"] = json.loads(row["tool_calls"])
    if row["tool_call_id"] is not None:
        msg["tool_call_id"] = row["tool_call_id"]
    if row["name"] is not None:
        msg["name"] = row["name"]
    return msg


class SessionStore:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    def load_messages(self, session_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT role, content, tool_calls, tool_call_id, name "
                "FROM session_messages WHERE session_id = ? ORDER BY seq ASC",
                (session_id,),
            )
            return [_row_to_message(row) for row in cur.fetchall()]

    def save_turn(self, session_id: str, messages: List[Dict[str, Any]]) -> None:
        if not messages:
            return
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions(session_id, created_at, updated_at) "
                "VALUES(?, ?, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET updated_at = excluded.updated_at",
                (session_id, now, now),
            )
            cur = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS max_seq FROM session_messages WHERE session_id = ?",
                (session_id,),
            )
            next_seq = cur.fetchone()["max_seq"] + 1
            rows = []
            for msg in messages:
                role = msg.get("role", "")
                if role not in ("user", "assistant", "tool"):
                    continue
                rows.append((
                    session_id,
                    next_seq,
                    role,
                    msg.get("content"),
                    json.dumps(msg["tool_calls"], ensure_ascii=False) if msg.get("tool_calls") is not None else None,
                    msg.get("tool_call_id"),
                    msg.get("name"),
                ))
                next_seq += 1
            if rows:
                conn.executemany(
                    "INSERT INTO session_messages(session_id, seq, role, content, tool_calls, tool_call_id, name) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?)",
                    rows,
                )
            conn.commit()

    def delete_session(self, session_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()
            return cur.rowcount > 0

    def list_sessions(self) -> List[str]:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT session_id FROM sessions ORDER BY updated_at DESC"
            )
            return [row["session_id"] for row in cur.fetchall()]

    def list_sessions_with_meta(self) -> List[Dict[str, Any]]:
        """Return ``{session_id, message_count, updated_at, created_at}`` for every session.

        Cheap to compute because SQLite gives us COUNT and ORDER BY in one
        scan, with the existing ``session_messages`` index on
        ``(session_id, seq)``.
        """
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT s.session_id, s.created_at, s.updated_at,
                       COUNT(m.id) AS message_count
                FROM sessions s
                LEFT JOIN session_messages m ON m.session_id = s.session_id
                GROUP BY s.session_id
                ORDER BY s.updated_at DESC
                """
            )
            return [
                {
                    "session_id": row["session_id"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "message_count": row["message_count"],
                }
                for row in cur.fetchall()
            ]

    def search_sessions(
        self, query: str, limit: int = 25
    ) -> List[Dict[str, Any]]:
        """Find sessions whose messages contain ``query`` as a substring.

        Substring-based: we trade FTS5 speed for portability (no extra
        ``pysqlite3-binary`` install) and call out the limit in the response.
        ``limit`` caps the number of distinct sessions returned, not the
        number of messages scanned.
        """
        if not query or not query.strip():
            return []
        limit = max(1, min(200, int(limit)))
        like = f"%{query.strip()}%"
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT s.session_id, s.updated_at, COUNT(m.id) AS hits
                FROM sessions s
                JOIN session_messages m ON m.session_id = s.session_id
                WHERE m.content LIKE ?
                GROUP BY s.session_id
                ORDER BY hits DESC, s.updated_at DESC
                LIMIT ?
                """,
                (like, limit),
            )
            return [
                {
                    "session_id": row["session_id"],
                    "updated_at": row["updated_at"],
                    "match_count": row["hits"],
                }
                for row in cur.fetchall()
            ]
