import json
from unittest.mock import patch
import unittest
import test_scan


class DatasetApiTests(unittest.TestCase):
    setUp = test_scan.ApiTests.setUp
    def dataset(self, reference=False, mode='auto', content=None):
        files = [('images', (f'sample_CAM1_1.{i:04d}.png', content or self.png, 'image/png')) for i in range(5)]
        if reference:
            files += [('metadata', ('metadata.json', json.dumps({'frames': [], 'object_center_world': {}}))),
                      ('reference_obj', ('source.obj', b'v 0 0 0'))]
        return self.client.post('/api/v1/scans/dataset', headers=self.headers,
                                data={'artifact_id': '7', 'mode': mode}, files=files)

    def test_dataset_preserves_benchmark_mapping_and_persists_mode(self):
        with patch.object(self.run_job, 'return_value', None), patch('app.main.jobs.create') as create:
            response = self.dataset(reference=True)
        self.assertEqual(response.status_code, 202, response.text)
        root = self.root / 'scan-jobs' / response.json()['scanJobId']
        config = json.loads((root / 'config.json').read_text())
        self.assertEqual(config['mode'], 'benchmark')
        self.assertTrue((root / 'dataset' / config['images'][0]).is_file())
        self.assertEqual(create.call_args.args[3]['mode'], 'benchmark')
        self.run_job.assert_awaited_once()

    def test_bad_dataset_is_cleaned_and_not_scheduled(self):
        with patch('app.main.jobs.create') as create:
            self.assertEqual(self.dataset(mode='benchmark').status_code, 422)
            self.assertEqual(self.dataset(content=b'fake').status_code, 415)
            with patch('app.dataset_upload.MAX_TOTAL_BYTES', 1):
                self.assertEqual(self.dataset().status_code, 413)
            create.assert_not_called()
        self.run_job.assert_not_awaited()
        self.assertEqual(list((self.root / 'scan-jobs').iterdir()), [])

    def test_discard_cannot_interrupt_running_job(self):
        with patch('app.main.jobs.discard', return_value=False):
            self.assertEqual(self.client.post(f'/api/v1/scans/{self.job}/discard', headers=self.headers).status_code, 409)
        with patch('app.main.jobs.discard', return_value=True):
            self.assertEqual(self.client.post(f'/api/v1/scans/{self.job}/discard', headers=self.headers).json()['status'], 'DISCARDED')
