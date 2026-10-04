import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models.signal import Signal


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class SignalConflict(ValueError):
    pass


class QueueFull(ValueError):
    pass


class Store:
    def __init__(self, path: Path, initial_balance: str):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS signals (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL,
                    received_at TEXT NOT NULL, result TEXT
                );
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
                    event TEXT NOT NULL, fields TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS signals_status ON signals(status);
            """)
            conn.execute("INSERT OR IGNORE INTO state VALUES ('balance', ?)", (initial_balance,))
            conn.execute("INSERT OR IGNORE INTO state VALUES ('enabled', 'true')")

    @contextmanager
    def transaction(self):
        conn = sqlite3.connect(self.path, timeout=1, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout=1000")
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def get(conn: sqlite3.Connection, key: str) -> str | None:
        row = conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    @staticmethod
    def set(conn: sqlite3.Connection, key: str, value: str) -> None:
        conn.execute(
            "INSERT INTO state VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    @staticmethod
    def audit(conn: sqlite3.Connection, event: str, fields: dict[str, Any]) -> None:
        conn.execute(
            "INSERT INTO audit(timestamp,event,fields) VALUES(?,?,?)",
            (now_iso(), event, json.dumps(fields, default=str)),
        )

    def enqueue(self, signal: Signal, limit: int) -> tuple[str, bool]:
        payload = json.dumps(signal.model_dump(mode="json"), sort_keys=True)
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT payload,status FROM signals WHERE id=?", (signal.signal_id,)
            ).fetchone()
            if row:
                if row["payload"] != payload:
                    raise SignalConflict("signal_id already used with different content")
                return row["status"], True
            count = conn.execute("SELECT COUNT(*) FROM signals WHERE status='QUEUED'").fetchone()[0]
            if count >= limit:
                raise QueueFull("signal queue is full")
            conn.execute(
                "INSERT INTO signals VALUES(?,?, 'QUEUED', ?, NULL)",
                (signal.signal_id, payload, now_iso()),
            )
        return "QUEUED", False

    def signal_status(self, signal_id: str) -> dict[str, Any] | None:
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT id,status,received_at,result FROM signals WHERE id=?", (signal_id,)
            ).fetchone()
            if not row:
                return None
            return {**dict(row), "result": json.loads(row["result"]) if row["result"] else None}
