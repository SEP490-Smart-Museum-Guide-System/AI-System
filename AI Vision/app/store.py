import sqlite3
from pathlib import Path


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
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_artifact_references_artifact_id "
                "ON artifact_references(artifact_id)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=15)
        connection.row_factory = sqlite3.Row
        return connection

    def count(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM artifact_references").fetchone()[0])

    def count_for_artifact(self, artifact_id: int) -> int:
        with self._connect() as connection:
            return int(connection.execute(
                "SELECT COUNT(*) FROM artifact_references WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()[0])

    def add(self, artifact_id: int, image_name: str, embedding: bytes, dimensions: int) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO artifact_references (artifact_id, image_name, embedding, dimensions)
                VALUES (?, ?, ?, ?)
                """,
                (artifact_id, image_name[:255], embedding, dimensions),
            )
            return int(cursor.lastrowid)

    def list_embeddings(self) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT id, artifact_id, image_name, embedding, dimensions "
                "FROM artifact_references ORDER BY id"
            ).fetchall()

    def delete_artifact(self, artifact_id: int) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM artifact_references WHERE artifact_id = ?", (artifact_id,)
            )
            return cursor.rowcount
