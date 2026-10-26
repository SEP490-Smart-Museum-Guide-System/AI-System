import os
import unittest
from uuid import uuid4

try:
    from app import settings
    from app.store import ReferenceStore, _connect
    from psycopg import sql
except ModuleNotFoundError:
    settings = ReferenceStore = _connect = sql = None


@unittest.skipUnless(
    ReferenceStore is not None and os.getenv("AI_SYSTEM_DB_PASSWORD"),
    "requires psycopg and the shared PostgreSQL test database",
)
class ReferenceStoreModelVersionTests(unittest.TestCase):
    def setUp(self):
        self.original_schema = settings.DB_SCHEMA
        settings.DB_SCHEMA = f"test_vision_{uuid4().hex[:12]}"
        self.store = ReferenceStore()
        self.store.initialize()

    def tearDown(self):
        with _connect() as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(settings.DB_SCHEMA))
            )
        settings.DB_SCHEMA = self.original_schema

    def test_embeddings_are_isolated_by_model_version(self):
        self.store.add(7, "onnx.jpg", b"\x00", 1, "clip-onnx-commit-a")
        self.store.add(7, "other.jpg", b"\x00", 1, "clip-onnx-commit-b")

        self.assertEqual(self.store.count("clip-onnx-commit-a"), 1)
        self.assertEqual(self.store.count_for_artifact(7, "clip-onnx-commit-a"), 1)
        rows = self.store.list_embeddings("clip-onnx-commit-a")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["image_name"], "onnx.jpg")
        self.assertEqual(self.store.delete_artifact(7), 2)


if __name__ == "__main__":
    unittest.main()
