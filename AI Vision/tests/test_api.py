from concurrent.futures import ThreadPoolExecutor
import io
from threading import Event, Lock
import unittest
from unittest.mock import Mock, patch

import numpy as np
import psycopg
from fastapi.testclient import TestClient
from PIL import Image
from app import main, settings
from app.store import ReferenceLimitReached
from app.vision import ImageEncoder, InvalidImage


def row(identity, vector, artifact=None):
    return {'id': identity, 'artifact_id': artifact or identity, 'dimensions': len(vector), 'embedding': np.array(vector, dtype=np.float32).tobytes()}


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.encoder = Mock(model_id='test-model')
        self.encoder.encode.return_value = np.array([1, 0], dtype=np.float32)
        self.store = Mock()
        self.store.list_embeddings.return_value = [row(1, [1, 0]), row(2, [.999, .02])]
        self.store.count.return_value = 2
        self.store.count_for_artifact.return_value = 0
        self.store.add.return_value = 5
        for target, value in [(main, {'store': self.store, 'get_encoder': Mock(return_value=self.encoder)}), (settings, {'SERVICE_API_KEY': 'server-key'})]:
            patcher = patch.multiple(target, **value); patcher.start(); self.addCleanup(patcher.stop)
        self.client = TestClient(main.app)
        self.headers = {'X-Service-Key': 'server-key'}

    def recognize(self, top_k=3, content=b'fixture'):
        return self.client.post(f'/api/v1/recognitions?top_k={top_k}', headers=self.headers, files={'image': ('photo.png', content, 'image/png')})

    def test_top_one_cannot_hide_an_ambiguous_runner_up(self):
        one, three = self.recognize(1), self.recognize(3)
        self.assertEqual(one.status_code, 200)
        self.assertFalse(one.json()['matched'])
        self.assertIsNone(one.json()['artifactId'])
        self.assertTrue(one.json()['requiresConfirmation'])
        self.assertEqual(one.json()['margin'], three.json()['margin'])
        self.assertEqual(len(one.json()['candidates']), 1)

    def test_references_of_same_artifact_do_not_become_competing_candidates(self):
        self.store.list_embeddings.return_value = [row(1, [1, 0], 7), row(2, [.999, .02], 7)]
        response = self.recognize().json()
        self.assertTrue(response['matched'])
        self.assertEqual(response['artifactId'], 7)
        self.assertEqual(len(response['candidates']), 1)

    def test_corrupt_vectors_are_skipped_and_all_invalid_is_unavailable(self):
        corrupt = [row(1, [float('nan'), 0]), row(2, [0, 0]), {'id': 3, 'artifact_id': 3, 'dimensions': 2, 'embedding': b'bad'}]
        self.store.list_embeddings.return_value = corrupt + [row(4, [1, 0])]
        self.assertEqual(self.recognize().json()['artifactId'], 4)
        self.store.list_embeddings.return_value = corrupt
        self.assertEqual(self.recognize().status_code, 503)

    def test_auth_empty_oversize_and_database_errors(self):
        self.assertEqual(self.client.post('/api/v1/recognitions', content=b'broken body', headers={'Content-Type': 'multipart/form-data; boundary=x'}).status_code, 401)
        self.assertEqual(self.client.post('/api/v1/recognitions', files={'image': ('x.png', b'x')}).status_code, 401)
        with patch.object(settings, 'SERVICE_API_KEY', ''):
            self.assertEqual(self.recognize().status_code, 401)
        self.assertEqual(self.recognize(content=b'').status_code, 422)
        with patch.object(settings, 'MAX_IMAGE_BYTES', 2):
            self.assertEqual(self.recognize(content=b'123').status_code, 413)
        self.store.list_embeddings.side_effect = psycopg.OperationalError('private DB credential')
        response = self.recognize()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private DB credential', response.text)

    def test_indexing_quota_race_returns_conflict(self):
        self.store.add.side_effect = ReferenceLimitReached('Đã đủ ảnh')
        response = self.client.post('/api/v1/references?artifact_id=7', headers=self.headers, files={'image': ('x.png', b'x')})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.store.add.call_args.kwargs['limit'], settings.MAX_REFERENCE_IMAGES_PER_ARTIFACT)

    def test_liveness_responds_while_encoding_is_busy(self):
        entered, release = Event(), Event()
        def encode(_):
            entered.set()
            if not release.wait(5): raise TimeoutError('test encoding blocked')
            return np.array([1, 0], dtype=np.float32)
        self.encoder.encode.side_effect = encode
        with ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(self.recognize)
            try:
                self.assertTrue(entered.wait(3))
                self.assertEqual(pool.submit(self.client.get, '/live').result(timeout=2).status_code, 200)
            finally:
                release.set()
            self.assertEqual(future.result(timeout=3).status_code, 200)

    def test_health_reports_real_ready_state_and_reference_count(self):
        with patch.object(main.app.state, 'model_ready', False):
            self.assertEqual(self.client.get('/ready').status_code, 503)
        with patch.object(main.app.state, 'model_ready', True):
            result = self.client.get('/health').json()
            self.assertTrue(result['model_ready'])
            self.assertEqual(result['reference_images'], 2)


class ImageTests(unittest.TestCase):
    def encoder(self):
        encoder = ImageEncoder.__new__(ImageEncoder)
        encoder._session = Mock()
        encoder._session.run.return_value = [np.ones((1, 512), dtype=np.float32)]
        encoder._lock, encoder._input_name, encoder._output_name = Lock(), 'pixels', 'embedding'
        return encoder

    def test_valid_photo_is_normalized_and_wrong_format_or_size_is_rejected(self):
        encoder = self.encoder()
        image = io.BytesIO(); Image.new('RGB', (4, 4)).save(image, format='PNG')
        vector = encoder.encode(image.getvalue())
        self.assertEqual(vector.shape, (512,))
        self.assertAlmostEqual(float(np.linalg.norm(vector)), 1, places=5)
        with patch.object(settings, 'MAX_IMAGE_PIXELS', 4):
            with self.assertRaises(InvalidImage): encoder.encode(image.getvalue())
        image = io.BytesIO(); Image.new('RGB', (4, 4)).save(image, format='GIF')
        with self.assertRaises(InvalidImage): encoder.encode(image.getvalue())
        with self.assertRaises(InvalidImage): encoder.encode(b'not an image')


if __name__ == '__main__':
    unittest.main()
