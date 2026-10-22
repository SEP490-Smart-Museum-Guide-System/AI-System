import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.store import ReferenceStore


class ReferenceStoreModelVersionTests(unittest.TestCase):
    def test_legacy_rows_are_not_mixed_with_new_model_embeddings(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            database = Path(directory) / "references.sqlite3"
            connection = sqlite3.connect(database)
            try:
                connection.execute("""CREATE TABLE artifact_references (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artifact_id INTEGER NOT NULL,
                    image_name TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    dimensions INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )""")
                connection.execute("""INSERT INTO artifact_references
                    (artifact_id, image_name, embedding, dimensions)
                    VALUES (7, 'legacy.jpg', X'00', 1)""")
                connection.commit()
            finally:
                connection.close()

            store = ReferenceStore(database)
            self.assertEqual(store.count("clip-onnx-commit-a"), 0)
            store.add(7, "onnx.jpg", b"\x00", 1, "clip-onnx-commit-a")
            store.add(7, "other.jpg", b"\x00", 1, "clip-onnx-commit-b")

            self.assertEqual(store.count_for_artifact(7, "clip-onnx-commit-a"), 1)
            self.assertEqual(len(store.list_embeddings("clip-onnx-commit-a")), 1)
            self.assertEqual(store.list_embeddings("clip-onnx-commit-a")[0]["image_name"], "onnx.jpg")
            self.assertEqual(store.delete_artifact(7), 3)


if __name__ == "__main__":
    unittest.main()
