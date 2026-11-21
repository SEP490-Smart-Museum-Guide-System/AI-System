import unittest
from unittest.mock import patch
from uuid import uuid4
from fastapi.testclient import TestClient
from app import main, read_api


class StatusApiTests(unittest.TestCase):
    def test_status_reader_never_initializes_or_claims_work_and_has_no_post_routes(self):
        identifier = str(uuid4())
        record = dict(id=identifier, artifact_id=7, status='PROCESSING', progress=10,
                      image_count=180, model_path=None, error=None, created_at=None)
        with patch.object(main, 'SERVICE_API_KEY', 'status-test'), \
                patch.object(main.jobs, 'get', return_value=record), \
                patch.object(main.jobs, 'initialize') as initialize, patch.object(main.jobs, 'claim') as claim:
            with TestClient(read_api.app) as client:
                path = f'/api/v1/scans/{identifier}'
                self.assertEqual(client.get(path).status_code, 401)
                response = client.get(path, headers={'X-Service-Key': 'status-test'})
                self.assertEqual(response.status_code, 200)
                self.assertIn('activity', response.json())
                self.assertEqual(client.post(path+'/cancel', headers={'X-Service-Key': 'status-test'}).status_code, 404)
            initialize.assert_not_called()
            claim.assert_not_called()
