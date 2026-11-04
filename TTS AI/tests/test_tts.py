import io
from pathlib import Path
import struct
import tarfile
import tempfile
from threading import Lock
from types import SimpleNamespace
import unicodedata
import unittest
from unittest.mock import Mock, patch
import wave

from fastapi.testclient import TestClient
from app import main, model_assets
from app.audio_cache import AudioCache
from app.synthesizer import PiperSynthesizer, SpeechBusy, _to_pcm_wav


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='smgs-tts-test-')
        self.addCleanup(self.directory.cleanup)
        self.cache = AudioCache(Path(self.directory.name), 1024, 2)
        self.wav = _to_pcm_wav([0.0, 0.5, -0.5], 16000)

    def test_wav_is_real_pcm_and_clips_amplitude(self):
        with wave.open(io.BytesIO(_to_pcm_wav([-2, 0, 2], 22050))) as audio:
            self.assertEqual((audio.getnchannels(), audio.getsampwidth(), audio.getframerate()), (1, 2, 22050))
            self.assertEqual(struct.unpack('<hhh', audio.readframes(3)), (-32767, 0, 32767))
        with self.assertRaises(ValueError):
            _to_pcm_wav([float('nan')], 16000)

    def test_corrupt_cache_regenerates_and_budget_is_bounded(self):
        for key in ('a' * 64, 'b' * 64, 'c' * 64):
            self.cache.put(key, self.wav)
        self.assertLessEqual(len(list(self.cache.directory.glob('*.wav'))), 2)
        key = 'd' * 64
        self.cache._path(key).write_bytes(b'broken')
        self.assertIsNone(self.cache.get(key))
        self.assertFalse(self.cache._path(key).exists())
        small = AudioCache(self.cache.directory, len(self.wav) - 1, 2)
        small.put(key, self.wav)
        self.assertEqual(list(small.directory.glob('*.wav')), [])
        self.assertEqual(list(small.directory.glob('*.part')), [])

    def synthesizer(self):
        synth = PiperSynthesizer.__new__(PiperSynthesizer)
        synth._voice, synth._model_identity = 'vi_VN-test', 'model-a'
        synth._cache, synth._queue_timeout, synth._generation_lock = self.cache, 0, Lock()
        synth._tts = SimpleNamespace(generate=Mock(return_value=SimpleNamespace(samples=[0.1] * 8, sample_rate=16000)))
        return synth

    def test_speed_and_model_identity_do_not_collide_and_vietnamese_is_normalized(self):
        synth = self.synthesizer()
        self.assertFalse(synth.generate('Bảo tàng', 1.0001)[1])
        self.assertTrue(synth.generate(unicodedata.normalize('NFD', 'Bảo   tàng'), 1.0001)[1])
        self.assertFalse(synth.generate('Bảo tàng', 1.0002)[1])
        synth._model_identity = 'model-b'
        self.assertFalse(synth.generate('Bảo tàng', 1.0002)[1])
        self.assertEqual(synth._tts.generate.call_count, 3)

    def test_busy_synthesis_does_not_block_cached_audio_and_failure_releases_slot(self):
        synth = self.synthesizer()
        synth.generate('Đã có', 1)
        synth._generation_lock.acquire()
        try:
            self.assertTrue(synth.generate('Đã có', 1)[1])
            with self.assertRaises(SpeechBusy):
                synth.generate('Chưa có', 1)
        finally:
            synth._generation_lock.release()
        synth._tts.generate.side_effect = RuntimeError('native failure')
        with self.assertRaises(RuntimeError):
            synth.generate('Lỗi', 1)
        self.assertFalse(synth._generation_lock.locked())


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = Mock()
        self.engine.generate.return_value = (_to_pcm_wav([0.1] * 8, 16000), False)
        self.settings = SimpleNamespace(max_text_chars=12000, voice='vi_VN-vais1000-medium', service_api_key='')
        for target, value in [('ensure_model_assets', Mock()), ('get_synthesizer', Mock(return_value=self.engine)), ('get_settings', Mock(return_value=self.settings))]:
            patcher = patch.object(main, target, value)
            patcher.start(); self.addCleanup(patcher.stop)
        self.client = self.enterContext(TestClient(main.app))

    def test_vietnamese_audio_and_real_readiness(self):
        self.assertTrue(self.client.get('/ready').json()['model_ready'])
        result = self.client.post('/api/v1/speech', json={'text': 'Di sản Việt Nam', 'language': 'vi-VN'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.headers['content-type'], 'audio/wav')
        self.assertEqual(result.content[:4], b'RIFF')
        self.assertEqual(result.headers['x-tts-cache'], 'MISS')
        main.app.state.model_ready = False
        self.assertEqual(self.client.get('/ready').status_code, 503)
        self.assertEqual(self.client.get('/live').status_code, 200)

    def test_invalid_requests_never_reach_engine(self):
        for payload in [{'text': ' '}, {'text': 'x', 'language': 'en'}, {'text': 'x', 'speed': 3}, {'text': 'x', 'extra': True}]:
            self.assertEqual(self.client.post('/api/v1/speech', json=payload).status_code, 422)
        self.settings.max_text_chars = 2
        self.assertEqual(self.client.post('/api/v1/speech', json={'text': 'abc'}).status_code, 413)
        self.engine.generate.assert_not_called()

    def test_service_key_and_busy_errors(self):
        self.settings.service_api_key = 'server-only'
        self.assertEqual(self.client.post('/api/v1/speech', content=b'not json').status_code, 401)
        payload = {'text': 'Lịch sử'}
        self.assertEqual(self.client.post('/api/v1/speech', json=payload).status_code, 401)
        self.engine.generate.side_effect = SpeechBusy('Bộ đọc đang bận.')
        response = self.client.post('/api/v1/speech', json=payload, headers={'X-Service-Key': 'server-only'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers['retry-after'], '3')
        self.engine.generate.side_effect = RuntimeError('private native details')
        response = self.client.post('/api/v1/speech', json=payload, headers={'X-Service-Key': 'server-only'})
        self.assertNotIn('private native details', response.text)


class ModelAssetTests(unittest.TestCase):
    def test_archive_accepts_regular_files_and_rejects_traversal_and_links(self):
        with tempfile.TemporaryDirectory(prefix='smgs-model-test-') as folder:
            root = Path(folder); destination = root / 'models'; destination.mkdir()
            for name, kind in [('voice/tokens.txt', tarfile.REGTYPE), ('../escape', tarfile.REGTYPE), ('link', tarfile.SYMTYPE), ('hard', tarfile.LNKTYPE)]:
                archive_path = root / 'test.tar.bz2'
                with tarfile.open(archive_path, 'w:bz2') as archive:
                    entry = tarfile.TarInfo(name); entry.type = kind
                    if kind == tarfile.REGTYPE:
                        entry.size = 2; archive.addfile(entry, io.BytesIO(b'ok'))
                    else:
                        entry.linkname = '../escape'; archive.addfile(entry)
                if name.startswith('voice'):
                    model_assets._safe_extract(archive_path, destination)
                    self.assertEqual((destination / name).read_bytes(), b'ok')
                else:
                    with self.assertRaises(RuntimeError):
                        model_assets._safe_extract(archive_path, destination)
                self.assertFalse((root / 'escape').exists())

    def test_failed_download_preserves_original_and_cleans_temporary(self):
        class Broken(io.BytesIO):
            def read(self, size=-1):
                raise TimeoutError('timeout')
        with tempfile.TemporaryDirectory(prefix='smgs-download-test-') as folder:
            target = Path(folder) / 'model.tar.bz2'; target.write_bytes(b'original')
            with patch.object(model_assets, 'urlopen', return_value=Broken()):
                with self.assertRaises(TimeoutError):
                    model_assets._download('https://example.invalid/model', target)
            self.assertEqual(target.read_bytes(), b'original')
            self.assertEqual(list(target.parent.glob('*.part')), [])


if __name__ == '__main__':
    unittest.main()
