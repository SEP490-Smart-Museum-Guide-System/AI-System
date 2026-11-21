import asyncio
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from app import main, jobs


class CancellationTests(unittest.TestCase):
    def test_cancel_requires_auth_and_is_idempotent_but_rejects_finished_jobs(self):
        identifier = str(uuid4())
        record = dict(id=identifier, artifact_id=7, status='PROCESSING', progress=45,
                      image_count=180, model_path=None, error=None, created_at=None)
        def cancel(_id):
            if record['status'] not in {'QUEUED', 'PROCESSING', 'FINALIZING'}:
                return False
            record['status'] = 'CANCELLED'
            return True
        with patch.object(main, 'SERVICE_API_KEY', 'test-key'), patch.object(jobs, 'get', return_value=record), \
                patch.object(jobs, 'cancel', side_effect=cancel) as cancelled:
            client = TestClient(main.app)
            url = f'/api/v1/scans/{identifier}/cancel'
            self.assertEqual(client.post(url).status_code, 401)
            cancelled.assert_not_called()
            headers = {'X-Service-Key': 'test-key'}
            response = client.post(url, headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['status'], 'CANCELLED')
            self.assertEqual(response.json()['progress'], 45)
            self.assertEqual(client.post(url, headers=headers).status_code, 200)
            self.assertEqual(cancelled.call_count, 1)
            record['status'] = 'REVIEW_REQUIRED'
            self.assertEqual(client.post(url, headers=headers).status_code, 409)
            with patch.object(jobs, 'get', return_value=None):
                self.assertEqual(client.post(url, headers=headers).status_code, 404)

    def test_late_worker_writes_cannot_change_terminal_states(self):
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        with patch.object(jobs, '_connect', return_value=connection):
            jobs.update(str(uuid4()), status='REVIEW_REQUIRED', progress=100, model_path='/output/model.glb')
        query = connection.execute.call_args.args[0].as_string()
        self.assertIn("AND status IN ('QUEUED','PROCESSING','FINALIZING')", query)

    def test_cancelled_partial_model_cannot_be_downloaded(self):
        with patch.object(main, 'SERVICE_API_KEY', 'test-key'), \
                patch.object(jobs, 'get', return_value={'status': 'CANCELLED', 'model_path': '/partial/model.glb'}):
            result = TestClient(main.app).get(f'/api/v1/scans/{uuid4()}/model', headers={'X-Service-Key': 'test-key'})
            self.assertEqual(result.status_code, 404)

    @unittest.skipUnless(os.name == 'posix', 'Azure/Linux process-group test')
    def test_termination_stops_native_descendants_not_just_worker_parent(self):
        async def check():
            with tempfile.TemporaryDirectory() as directory:
                marker = Path(directory) / 'pid'
                # The parent reaps its child on TERM, as the real job runner does.
                code = '''import pathlib,subprocess,signal,sys,time
p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(90)'])
def stop(*_):
 p.wait(timeout=4)
 raise SystemExit(0)
signal.signal(signal.SIGTERM,stop)
pathlib.Path(sys.argv[1]).write_text(str(p.pid))
time.sleep(90)
'''
                child = await asyncio.create_subprocess_exec(sys.executable, '-c', code, str(marker), start_new_session=True)
                try:
                    for _ in range(100):
                        if marker.exists(): break
                        await asyncio.sleep(.02)
                    self.assertTrue(marker.exists())
                    native_pid = int(marker.read_text())
                    await main._stop_process_group(child)
                    with self.assertRaises(ProcessLookupError): os.kill(native_pid, 0)
                    self.assertIsNotNone(child.returncode)
                finally:
                    if child.returncode is None: await main._stop_process_group(child)
        asyncio.run(check())
