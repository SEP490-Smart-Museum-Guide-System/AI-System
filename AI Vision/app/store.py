from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg import sql

from app import settings


def _table(name: str) -> sql.Composed:
    return sql.SQL("{}.{}").format(sql.Identifier(settings.DB_SCHEMA), sql.Identifier(name))


def _connect() -> psycopg.Connection:
    return psycopg.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        dbname=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        connect_timeout=5,
        row_factory=dict_row,
    )


class ReferenceStore:
    """Derived CLIP embeddings in the same PostgreSQL database used by SMGS BE."""

    def initialize(self) -> None:
        with _connect() as connection:
            connection.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {} ").format(sql.Identifier(settings.DB_SCHEMA))
            )
            connection.execute(sql.SQL("""
                CREATE TABLE IF NOT EXISTS {} (
                    id BIGSERIAL PRIMARY KEY,
                    artifact_id INTEGER NOT NULL,
                    image_name VARCHAR(255) NOT NULL,
                    embedding BYTEA NOT NULL,
                    dimensions INTEGER NOT NULL,
                    model_id TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """).format(_table("artifact_reference_embeddings")))
            connection.execute(sql.SQL(
                "CREATE INDEX IF NOT EXISTS ix_ai_vision_embeddings_artifact_id "
                "ON {} (artifact_id)"
            ).format(_table("artifact_reference_embeddings")))
            connection.execute(sql.SQL(
                "CREATE INDEX IF NOT EXISTS ix_ai_vision_embeddings_model_id "
                "ON {} (model_id)"
            ).format(_table("artifact_reference_embeddings")))

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection]:
        with _connect() as connection:
            yield connection

    def count(self, model_id: str) -> int:
        with self._connection() as connection:
            row = connection.execute(
                sql.SQL("SELECT COUNT(*) AS count FROM {} WHERE model_id = %s").format(
                    _table("artifact_reference_embeddings")
                ), (model_id,),
            ).fetchone()
            return int(row["count"])

    def count_for_artifact(self, artifact_id: int, model_id: str) -> int:
        with self._connection() as connection:
            row = connection.execute(
                sql.SQL("SELECT COUNT(*) AS count FROM {} WHERE artifact_id = %s AND model_id = %s").format(
                    _table("artifact_reference_embeddings")
                ), (artifact_id, model_id),
            ).fetchone()
            return int(row["count"])

    def add(self, artifact_id: int, image_name: str, embedding: bytes, dimensions: int,
            model_id: str) -> int:
        with self._connection() as connection:
            row = connection.execute(
                sql.SQL("""
                    INSERT INTO {} (artifact_id, image_name, embedding, dimensions, model_id)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                """).format(_table("artifact_reference_embeddings")),
                (artifact_id, image_name[:255], embedding, dimensions, model_id),
            ).fetchone()
            return int(row["id"])

    def list_embeddings(self, model_id: str) -> list[dict[str, object]]:
        with self._connection() as connection:
            rows = connection.execute(
                sql.SQL("""
                    SELECT id, artifact_id, image_name, embedding, dimensions
                    FROM {} WHERE model_id = %s ORDER BY id
                """).format(_table("artifact_reference_embeddings")), (model_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def delete_artifact(self, artifact_id: int) -> int:
        with self._connection() as connection:
            cursor = connection.execute(
                sql.SQL("DELETE FROM {} WHERE artifact_id = %s").format(
                    _table("artifact_reference_embeddings")
                ), (artifact_id,),
            )
            return cursor.rowcount
