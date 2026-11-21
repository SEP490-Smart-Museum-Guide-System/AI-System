from pathlib import Path
import tempfile
import unittest

from app.activity import activity


class ActivityTests(unittest.TestCase):
    def test_matching_counts_completed_blocks_not_started_block(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'logs').mkdir()
            log = root/'logs/COLMAP_SfM.log'
            log.write_text('Matching block [3/4, 2/4]\n')
            result = activity(root, 'PROCESSING', 10)
            self.assertEqual((result['stage'], result['completed'], result['total'], result['percent']), ('matching', 9, 16, 56.2))
            log.write_text(log.read_text() + 'feature_matching.cc:46]  in 59.584s\n')
            self.assertEqual(activity(root, 'PROCESSING', 10)['completed'], 10)

    def test_camera_stage_has_no_invented_percent_and_terminal_job_stays_stopped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'logs').mkdir()
            (root/'logs/COLMAP_SfM.log').write_text('Matching block [4/4, 4/4]\n in 3.2s\nBundle adjustment report\n')
            result = activity(root, 'PROCESSING', 10)
            self.assertEqual(result['stage'], 'cameras')
            self.assertIsNone(result['percent'])
            self.assertIsNotNone(result['lastActivityAt'])
            self.assertEqual(activity(root, 'CANCELLED', 45)['stage'], 'stopped')
            self.assertEqual(activity(root, 'REVIEW_REQUIRED', 100)['percent'], 100)

    def test_missing_log_uses_an_indeterminate_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(activity(Path(directory), 'PROCESSING', 10)['percent'])

    def test_native_depth_counter_is_per_stage_not_overall(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'openmvs/logs').mkdir(parents=True)
            (root/'openmvs/logs/OpenMVS_CPU_PatchMatch_densification.log').write_text('Estimated depth-maps 90 (50.00%, 4m, ETA 4m)...\r')
            result = activity(root, 'PROCESSING', 45)
            self.assertEqual((result['phase'], result['completed'], result['percent']), (3, 90, 50))

    def test_individual_depth_completions_are_unique_without_guessed_total(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'openmvs').mkdir()
            (root/'openmvs/DensifyPointCloud-run.log').write_text('Depth-map for image 90 estimated using 5 images\nDepth-map for image 3 estimated using 5 images\nDepth-map for image 90 estimated using 5 images\n')
            result = activity(root, 'PROCESSING', 45)
            self.assertEqual(result['completed'], 2)
            self.assertEqual(result['operations'], 3)
            self.assertIsNone(result['total'])
            self.assertIsNone(result['percent'])
            (root/'openmvs/RefineMesh-run.log').write_text('Processed iterations 4 (18.18%, 55s)...')
            result = activity(root, 'PROCESSING', 70)
            self.assertEqual((result['depthImages'], result['depthOperations']), (2, 3))
            self.assertEqual(activity(root, 'REVIEW_REQUIRED', 100)['depthImages'], 2)
