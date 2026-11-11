import asyncio
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image
import psycopg
from app import main, reconstruction, jobs


class InitializationTests(unittest.TestCase):
    def test_json_default_is_literal_not_a_second_sql_format_placeholder(self):
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        with patch.object(jobs, '_connect', return_value=connection):
            jobs.initialize()
        statements = [call.args[0].as_string() for call in connection.execute.call_args_list]
        self.assertEqual(len(statements), 4)
        self.assertIn("DEFAULT '{}'::jsonb", statements[1])


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='smgs-scan-test-')
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        image = io.BytesIO(); Image.new('RGB', (4, 4)).save(image, format='PNG')
        self.png = image.getvalue()
        self.job = str(uuid4())
        self.headers = {'X-Service-Key': 'server-key'}
        self.run_job = AsyncMock()
        patcher = patch.multiple(main.jobs, initialize=Mock(), queued_ids=Mock(return_value=[]))
        patcher.start(); self.addCleanup(patcher.stop)
        for target, values in [(main, {'DATA_DIR': self.root, 'SERVICE_API_KEY': 'server-key', '_run_job': self.run_job, 'openmvs_available': Mock(return_value=True)}), (main.shutil, {'which': Mock(return_value='/fake/colmap')})]:
            patcher = patch.multiple(target, **values); patcher.start(); self.addCleanup(patcher.stop)
        self.client = TestClient(main.app)

    def upload(self, count=5, content=None, name='photo.png', metadata='{}'):
        content = self.png if content is None else content
        return self.client.post('/api/v1/scans', headers=self.headers,
            data={'artifact_id': '7', 'capture_metadata': metadata},
            files=[('images', (name, content, 'image/png')) for _ in range(count)])

    def test_accepts_real_images_persists_then_schedules(self):
        with patch.object(main.jobs, 'create') as create:
            response = self.upload()
        self.assertEqual(response.status_code, 202)
        identifier = response.json()['scanJobId']
        self.assertEqual(len(list((self.root / 'scan-jobs' / identifier / 'input').glob('*.png'))), 5)
        self.assertEqual(create.call_args.args[1:3], (7, 5))
        self.run_job.assert_awaited_once()

    def test_bad_image_or_db_failure_cleans_upload_and_never_schedules(self):
        with patch.object(main.jobs, 'create') as create:
            self.assertEqual(self.upload(content=b'not an image').status_code, 415)
            self.assertEqual(self.upload(name='disguised.jpg').status_code, 415)
            create.assert_not_called()
        with patch.object(main.jobs, 'create', side_effect=psycopg.OperationalError('private DB secret')):
            response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private DB secret', response.text)
        self.assertEqual(list((self.root / 'scan-jobs').iterdir()), [])
        self.run_job.assert_not_awaited()

    def test_limits_validate_before_persisting(self):
        with patch.object(main.jobs, 'create') as create:
            self.assertEqual(self.upload(count=4).status_code, 422)
            self.assertEqual(self.upload(count=81).status_code, 422)
            self.assertEqual(self.upload(metadata='[]').status_code, 422)
            with patch.object(main, 'MAX_METADATA_BYTES', 3):
                self.assertEqual(self.upload(metadata='{"x":1}').status_code, 413)
            with patch.object(main, 'MAX_IMAGE_BYTES', 2):
                self.assertEqual(self.upload().status_code, 413)
            with patch('app.validation.MAX_IMAGE_PIXELS', 4):
                self.assertEqual(self.upload().status_code, 415)
            create.assert_not_called()
        self.run_job.assert_not_awaited()

    def test_missing_colmap_is_unavailable_and_health_is_accurate(self):
        with patch.object(main.shutil, 'which', return_value=None):
            self.assertEqual(self.upload().status_code, 503)
            result = self.client.get('/health')
            self.assertEqual(result.status_code, 503)
            self.assertFalse(result.json()['colmap_available'])
        with patch.object(main.app.state, 'worker_ready', True), patch.object(main.jobs, 'ping'):
            self.assertEqual(self.client.get('/ready').status_code, 200)
        self.assertEqual(self.client.get('/live').status_code, 200)

    def test_missing_openmvs_cpu_pipeline_blocks_scan_upload(self):
        with patch.object(main, 'openmvs_available', return_value=False):
            response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertIn('OpenMVS CPU', response.json()['detail'])
        self.run_job.assert_not_awaited()

    def test_invalid_ids_and_unauthorized_calls_never_reach_database(self):
        self.assertEqual(self.client.post('/api/v1/scans', content=b'broken body', headers={'Content-Type': 'multipart/form-data; boundary=x'}).status_code, 401)
        with patch.object(main.jobs, 'get') as get:
            self.assertEqual(self.client.get('/api/v1/scans/not-a-uuid', headers=self.headers).status_code, 422)
            self.assertEqual(self.client.get(f'/api/v1/scans/{self.job}').status_code, 401)
            get.assert_not_called()

    def test_model_requires_safe_job_output_and_glb_extension(self):
        output = self.root / 'scan-jobs' / self.job / 'output'; output.mkdir(parents=True)
        inside = output / 'model.glb'; inside.write_bytes(b'glTF-fixture')
        with patch.object(main.jobs, 'get', return_value={'model_path': str(inside)}):
            result = self.client.get(f'/api/v1/scans/{self.job}/model', headers=self.headers)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.headers['content-type'], 'model/gltf-binary')
        outside = self.root / 'secret.glb'; outside.write_bytes(b'secret')
        with patch.object(main.jobs, 'get', return_value={'model_path': str(outside)}):
            self.assertEqual(self.client.get(f'/api/v1/scans/{self.job}/model', headers=self.headers).status_code, 404)

    def test_only_reviewed_jobs_can_approve(self):
        with patch.object(main.jobs, 'approve', return_value={'status': 'QUEUED'}):
            self.assertEqual(self.client.post(f'/api/v1/scans/{self.job}/approve', headers=self.headers).status_code, 409)
        with patch.object(main.jobs, 'approve', return_value={'status': 'COMPLETED', 'artifact_id': 7}):
            self.assertEqual(self.client.post(f'/api/v1/scans/{self.job}/approve', headers=self.headers).status_code, 200)


class WorkerTests(unittest.TestCase):
    def test_missing_openmvs_fails_instead_of_packaging_sparse_cloud_as_artifact(self):
        with tempfile.TemporaryDirectory(prefix='smgs-scan-worker-test-') as folder:
            with patch.object(reconstruction, 'openmvs_available', return_value=False), \
                    patch.object(reconstruction.jobs, 'update') as update:
                reconstruction.process(str(uuid4()), Path(folder))
            self.assertEqual(update.call_args.kwargs['status'], 'FAILED')
            self.assertIn('OpenMVS CPU', update.call_args.kwargs['error'])

    def test_job_not_claimed_is_never_processed(self):
        with patch.object(main.jobs, 'claim', return_value=False), patch.object(main, 'process') as process:
            asyncio.run(main._run_job(str(uuid4()), Path('unused')))
            process.assert_not_called()
        with patch.object(main.jobs, 'claim', return_value=True), patch.object(main, 'process') as process:
            asyncio.run(main._run_job(str(uuid4()), Path('unused')))
            process.assert_called_once()

    def test_native_errors_are_not_returned_as_job_messages(self):
        with tempfile.TemporaryDirectory(prefix='smgs-worker-test-') as folder:
            with patch.object(reconstruction, '_run', side_effect=RuntimeError('private native path')), patch.object(reconstruction.jobs, 'update') as update:
                reconstruction.process(str(uuid4()), Path(folder))
            message = update.call_args.kwargs
            self.assertEqual(message['status'], 'FAILED')
            self.assertNotIn('private native path', message['error'])


if __name__ == '__main__':
    unittest.main()
