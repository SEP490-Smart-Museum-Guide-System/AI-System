from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .settings import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, DB_SCHEMA


def _table() -> sql.Composed:
    return sql.SQL("{}.{}").format(sql.Identifier(DB_SCHEMA), sql.Identifier("scan_jobs"))


def _connect() -> psycopg.Connection:
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=5,
        row_factory=dict_row,
    )


def initialize() -> None:
    with _connect() as db:
        db.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(DB_SCHEMA)))
        db.execute(sql.SQL("""
            CREATE TABLE IF NOT EXISTS {} (
                id UUID PRIMARY KEY,
                artifact_id INTEGER NOT NULL,
                status VARCHAR(32) NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                image_count INTEGER NOT NULL,
                model_path TEXT,
                error TEXT,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                capture_metadata JSONB NOT NULL DEFAULT '{}'::jsonb
            )
        """).format(_table()))
        db.execute(sql.SQL(
            "CREATE INDEX IF NOT EXISTS ix_scan_jobs_status_created "
            "ON {} (status, created_at)"
        ).format(_table()))
        db.execute(sql.SQL(
            "UPDATE {} SET status='QUEUED', progress=0, updated_at=%s WHERE status='PROCESSING'"
        ).format(_table()), (_now(),))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create(job_id: str, artifact_id: int, image_count: int, metadata: dict[str, Any]) -> None:
    now = _now()
    with _connect() as db:
        db.execute(sql.SQL("""
            INSERT INTO {} (id, artifact_id, status, image_count, created_at, updated_at, capture_metadata)
            VALUES (%s, %s, 'QUEUED', %s, %s, %s, %s)
        """).format(_table()), (UUID(job_id), artifact_id, image_count, now, now, Jsonb(metadata)))


def update(job_id: str, *, status: str | None = None, progress: int | None = None,
           model_path: str | None = None, error: str | None = None) -> None:
    assignments = [sql.SQL("updated_at = %s")]
    values: list[Any] = [_now()]
    for key, value in (("status", status), ("progress", progress),
                       ("model_path", model_path), ("error", error)):
        if value is not None:
            assignments.append(sql.SQL("{} = %s").format(sql.Identifier(key)))
            values.append(value)
    values.append(UUID(job_id))
    query = sql.SQL("UPDATE {} SET {} WHERE id = %s").format(
        _table(), sql.SQL(", ").join(assignments)
    )
    with _connect() as db:
        db.execute(query, values)


def get(job_id: str) -> dict[str, Any] | None:
    with _connect() as db:
        row = db.execute(sql.SQL("SELECT * FROM {} WHERE id = %s").format(_table()), (UUID(job_id),)).fetchone()
    return dict(row) if row else None


def queued_ids() -> list[str]:
    with _connect() as db:
        rows = db.execute(
            sql.SQL("SELECT id FROM {} WHERE status='QUEUED' ORDER BY created_at").format(_table())
        ).fetchall()
    return [str(row["id"]) for row in rows]


def approve(job_id: str) -> dict[str, Any] | None:
    with _connect() as db:
        db.execute(sql.SQL("""
            UPDATE {} SET status='COMPLETED', updated_at=%s
            WHERE id=%s AND status='REVIEW_REQUIRED'
        """).format(_table()), (_now(), UUID(job_id)))
    return get(job_id)
