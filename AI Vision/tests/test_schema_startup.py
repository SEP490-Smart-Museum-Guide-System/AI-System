import unittest
from unittest.mock import MagicMock, patch
from app.store import ReferenceStore


class SchemaStartupTests(unittest.TestCase):
    def test_existing_schema_does_not_require_database_create_permission(self):
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = {'exists': 1}
        with patch('app.store._connect') as connect:
            connect.return_value.__enter__.return_value = connection
            ReferenceStore().initialize()
        queries = [str(call.args[0]) for call in connection.execute.call_args_list]
        self.assertIn('pg_namespace', queries[0])
        self.assertFalse(any('CREATE SCHEMA' in query for query in queries))
        self.assertTrue(any('CREATE TABLE' in query for query in queries))
