import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.scan_folder import folder_path, inspect_folder
from app import reconstruction


class LocalFolderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def images(self, folder, count=5, benchmark=False):
        folder.mkdir(exist_ok=True)
        for number in range(1, count + 1):
            name = f'sample_CAM1_1.{number:04d}.png' if benchmark else f'{number}.jpg'
            (folder / name).write_bytes(b'fixture')

    def test_images_subfolder_excludes_reference_texture(self):
        self.images(self.root / 'images')
        (self.root / 'reference.jpeg').write_bytes(b'texture-not-a-photo')
        _, config = inspect_folder(self.root)
        self.assertEqual(config['image_count'], 5)
        self.assertEqual(config['mode'], 'photos')
        self.assertTrue(all(p.startswith('images/') for p in config['images']))

    def test_auto_benchmark_and_explicit_photos(self):
        self.images(self.root / 'images', benchmark=True)
        (self.root / 'different-object.obj').write_text('v 0 0 0')
        (self.root / 'metadata.json').write_text(json.dumps({'object_center_world': {}, 'frames': []}))
        source, config = inspect_folder(self.root / 'images')
        self.assertEqual(source, self.root)
        self.assertEqual(config['mode'], 'benchmark')
        self.assertEqual(inspect_folder(self.root, 'photos')[1]['mode'], 'photos')

    def test_nested_photos_and_spaces(self):
        self.images(self.root / 'ring one')
        self.images(self.root / 'ring two')
        self.assertEqual(inspect_folder(self.root)[1]['image_count'], 10)
        self.assertEqual(folder_path('"' + str(self.root) + '"'), self.root)

    def test_insufficient_photos_and_missing_metadata_fail(self):
        with self.assertRaisesRegex(ValueError, 'Found 0'):
            inspect_folder(self.root)
        self.images(self.root)
        with self.assertRaisesRegex(ValueError, 'Benchmark mode requires'):
            inspect_folder(self.root, 'benchmark')

    def test_local_updates_do_not_write_database(self):
        updates = []
        with patch.object(reconstruction, 'openmvs_available', return_value=False), \
                patch.object(reconstruction.jobs, 'update') as database:
            reconstruction.process('local', self.root, on_update=lambda _id, **kw: updates.append(kw))
        database.assert_not_called()
        self.assertEqual(updates[-1]['status'], 'FAILED')
        self.assertFalse(updates[-1]['model_path'])


if __name__ == '__main__':
    unittest.main()
