import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.performance import ordered_pairs, settings
from app import reconstruction as pipeline


class PerformanceTests(unittest.TestCase):
    def test_ordered_pairs_cover_all_photos_and_connect_capture_rings(self):
        names = [f'image_{i:05d}.jpg' for i in range(180)]
        pairs = ordered_pairs(names)
        self.assertLess(len(pairs), 180*179//2 / 3)
        self.assertEqual(len(pairs), len(set(pairs)))
        self.assertTrue(all(a != b for a, b in pairs))
        reached = {names[0]}
        while True:
            expanded = reached | {b for a, b in pairs if a in reached} | {a for a, b in pairs if b in reached}
            if expanded == reached: break
            reached = expanded
        self.assertEqual(reached, set(names))
        self.assertTrue(any(a in names[:90] and b in names[90:] for a, b in pairs))
        self.assertEqual(len(ordered_pairs(names[:5])), 10)

    def test_presets_keep_legacy_jobs_detailed_and_validate_input(self):
        self.assertEqual(settings()['quality'], 'detailed')
        self.assertEqual(settings('balanced')['min_resolution'], 320)
        self.assertFalse(settings('preview')['refine'])
        for args in [('unknown', 'ordered'), ('balanced', 'random')]:
            with self.assertRaises(ValueError): settings(*args)

    def test_dense_quality_flags_and_preview_refinement(self):
        for quality, resolution, minimum, refine, texture in [
                ('detailed', '0', '640', True, '4096'),
                ('balanced', '1', '320', True, '4096'),
                ('preview', '2', '256', False, '2048')]:
            with self.subTest(quality=quality), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                (root/'input').mkdir()
                for i in range(5): (root/'input'/f'{i}.jpg').touch()
                updates = []
                with patch.object(pipeline, 'openmvs_available', return_value=True), \
                        patch.object(pipeline, '_registered_image_count', return_value=5), \
                        patch.object(pipeline, '_validate_camera_calibration'), \
                        patch.object(pipeline, '_ply_vertex_count', return_value=100), \
                        patch.object(pipeline, '_embed_glb_textures'), \
                        patch.object(pipeline, 'normalize_capture_orientation', return_value={'applied': True}), \
                        patch.object(pipeline, '_validate_surface_glb') as validate, \
                        patch.object(pipeline, '_run') as run:
                    pipeline.process('test', root, sparse_model=root, dense_method='patchmatch', quality=quality,
                                     on_update=lambda _, **kw: updates.append(kw))
                self.assertEqual(updates[-1]['status'], 'REVIEW_REQUIRED')
                commands = [call.args[0] for call in run.call_args_list]
                dense = next(c for c in commands if Path(c[0]).name == 'DensifyPointCloud')
                self.assertEqual(dense[dense.index('--resolution-level')+1], resolution)
                self.assertEqual(dense[dense.index('--min-resolution')+1], minimum)
                self.assertEqual(any(Path(c[0]).name == 'RefineMesh' for c in commands), refine)
                tex = next(c for c in commands if Path(c[0]).name == 'TextureMesh')
                self.assertEqual(tex[tex.index('--max-texture-size')+1], texture)
                if not refine: self.assertTrue(tex[tex.index('-m')+1].endswith('scene_dense_mesh.ply'))
                validate.assert_called_once()
                self.assertEqual(json.loads((root/'performance.json').read_text())['quality'], quality)

    def test_ordered_matching_falls_back_without_reextracting_features(self):
        for count, fallback in [(8, False), (6, True)]:
            with self.subTest(registered=count), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); images = root/'input'; images.mkdir()
                work = root/'colmap'; work.mkdir()
                for i in range(10): (images/f'{i:05d}.jpg').touch()
                def fake_run(args, cwd, label):
                    if args[1] == 'mapper':
                        output = Path(args[args.index('--output_path')+1])/'0'
                        output.mkdir(); (output/'images.bin').touch()
                audit = {}
                with patch.object(pipeline, '_run', side_effect=fake_run) as run, \
                        patch.object(pipeline, '_registered_image_count', return_value=count):
                    models = pipeline._ordered_sfm(images, work, root, audit)
                commands = [c.args[0][1] for c in run.call_args_list]
                self.assertEqual(commands.count('feature_extractor'), 1)
                self.assertEqual('exhaustive_matcher' in commands, fallback)
                self.assertEqual(audit['exhaustive_fallback'], fallback)
                self.assertEqual(models[0].parent.name, 'fallback-sparse' if fallback else 'ordered-sparse')

    def test_failed_ordered_match_also_uses_exhaustive_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); images = root/'input'; images.mkdir(); work = root/'work'; work.mkdir()
            for i in range(5): (images/f'{i}.jpg').touch()
            def fake(args, cwd, label):
                if args[1] == 'matches_importer': raise pipeline.ReconstructionFailure('failed')
            audit = {}
            with patch.object(pipeline, '_run', side_effect=fake) as run:
                self.assertEqual(pipeline._ordered_sfm(images, work, root, audit), [])
            self.assertTrue(audit['exhaustive_fallback'])
            self.assertIn('exhaustive_matcher', [c.args[0][1] for c in run.call_args_list])

    def test_fast_matching_never_bypasses_registration_guard_or_runs_when_unordered(self):
        for order in ('ordered', 'unordered'):
            with self.subTest(order=order), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); images = root/'input'; images.mkdir()
                for i in range(10): (images/f'{i}.jpg').touch()
                def fake_run(args, cwd, label):
                    if args[1] == 'automatic_reconstructor':
                        model = root/'colmap/sparse/0'; model.mkdir(parents=True); (model/'images.bin').touch()
                updates = []
                with patch.object(pipeline, 'openmvs_available', return_value=True), \
                        patch.object(pipeline, '_ordered_sfm', return_value=[root]) as ordered, \
                        patch.object(pipeline, '_registered_image_count', return_value=6), \
                        patch.object(pipeline, '_run', side_effect=fake_run) as run:
                    pipeline.process('test', root, dense_method='patchmatch', quality='balanced', capture_order=order,
                                     on_update=lambda _, **kw: updates.append(kw))
                self.assertEqual(bool(ordered.call_count), order == 'ordered')
                self.assertEqual(updates[-1]['status'], 'FAILED')
                self.assertIn('6/10', updates[-1]['error'])
                self.assertFalse(any(Path(c.args[0][0]).name == 'DensifyPointCloud' for c in run.call_args_list))


if __name__ == '__main__': unittest.main()
