from contextlib import contextmanager
import sqlite3
from pathlib import Path
from typing import Iterator


class ReferenceStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS artifact_references (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artifact_id INTEGER NOT NULL,
                    image_name TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    dimensions INTEGER NOT NULL,
                    model_id TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(artifact_references)")
            }
            if "model_id" not in columns:
                # Existing OpenCLIP vectors are retained but excluded from ONNX matching.
                connection.execute("ALTER TABLE artifact_references ADD COLUMN model_id TEXT")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_artifact_references_artifact_id "
                "ON artifact_references(artifact_id)"
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def count(self, model_id: str) -> int:
        with self._connect() as connection:
            return int(connection.execute(
                "SELECT COUNT(*) FROM artifact_references WHERE model_id = ?", (model_id,)
            ).fetchone()[0])

    def count_for_artifact(self, artifact_id: int, model_id: str) -> int:
        with self._connect() as connection:
            return int(connection.execute(
                "SELECT COUNT(*) FROM artifact_references WHERE artifact_id = ? AND model_id = ?",
                (artifact_id, model_id),
            ).fetchone()[0])

    def add(self, artifact_id: int, image_name: str, embedding: bytes, dimensions: int,
            model_id: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO artifact_references (artifact_id, image_name, embedding, dimensions, model_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (artifact_id, image_name[:255], embedding, dimensions, model_id),
            )
            return int(cursor.lastrowid)

    def list_embeddings(self, model_id: str) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT id, artifact_id, image_name, embedding, dimensions "
                "FROM artifact_references WHERE model_id = ? ORDER BY id",
                (model_id,),
            ).fetchall()

    def delete_artifact(self, artifact_id: int) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM artifact_references WHERE artifact_id = ?", (artifact_id,)
            )
            return cursor.rowcount
