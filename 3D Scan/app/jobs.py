import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .settings import DATABASE_PATH


def _connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def initialize() -> None:
    with _connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS scan_jobs (
            id TEXT PRIMARY KEY,
            artifact_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            image_count INTEGER NOT NULL,
            model_path TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            capture_metadata TEXT NOT NULL DEFAULT '{}'
        )""")
        db.execute("UPDATE scan_jobs SET status='QUEUED', progress=0, updated_at=? WHERE status='PROCESSING'",
                   (_now(),))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create(job_id: str, artifact_id: int, image_count: int, metadata: dict[str, Any]) -> None:
    now = _now()
    with _connect() as db:
        db.execute("""INSERT INTO scan_jobs
            (id, artifact_id, status, image_count, created_at, updated_at, capture_metadata)
            VALUES (?, ?, 'QUEUED', ?, ?, ?, ?)""",
                   (job_id, artifact_id, image_count, now, now, json.dumps(metadata)))


def update(job_id: str, *, status: str | None = None, progress: int | None = None,
           model_path: str | None = None, error: str | None = None) -> None:
    fields = ["updated_at=?"]
    values: list[Any] = [_now()]
    for key, value in (("status", status), ("progress", progress),
                       ("model_path", model_path), ("error", error)):
        if value is not None:
            fields.append(f"{key}=?")
            values.append(value)
    values.append(job_id)
    with _connect() as db:
        db.execute(f"UPDATE scan_jobs SET {', '.join(fields)} WHERE id=?", values)


def get(job_id: str) -> dict[str, Any] | None:
    with _connect() as db:
        row = db.execute("SELECT * FROM scan_jobs WHERE id=?", (job_id,)).fetchone()
    return dict(row) if row else None


def queued_ids() -> list[str]:
    with _connect() as db:
        rows = db.execute("SELECT id FROM scan_jobs WHERE status='QUEUED' ORDER BY created_at").fetchall()
    return [row["id"] for row in rows]


def approve(job_id: str) -> dict[str, Any] | None:
    with _connect() as db:
        db.execute("""UPDATE scan_jobs SET status='COMPLETED', updated_at=?
            WHERE id=? AND status='REVIEW_REQUIRED'""", (_now(), job_id))
    return get(job_id)

