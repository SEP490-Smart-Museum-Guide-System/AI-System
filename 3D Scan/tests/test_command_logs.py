import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app.reconstruction import _run, ReconstructionFailure


class LiveCommandLogTests(unittest.TestCase):
    def test_output_is_readable_while_the_command_is_still_running(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            errors = []
            def run():
                try:
                    _run([sys.executable, '-u', '-c', 'import time; print("stage is live"); time.sleep(1.5)'], root, 'live test')
                except Exception as error:
                    errors.append(error)
            thread = threading.Thread(target=run)
            thread.start()
            log = root / 'logs/live_test.log'
            try:
                deadline = time.monotonic() + 1.3
                while time.monotonic() < deadline:
                    if log.exists() and 'stage is live' in log.read_text(encoding='utf8'):
                        break
                    time.sleep(.02)
                self.assertIn('stage is live', log.read_text(encoding='utf8'))
                self.assertTrue(thread.is_alive(), 'Output must be visible before command completion')
            finally:
                thread.join(5)
            self.assertFalse(errors)
            self.assertIn('EXIT: 0', log.read_text(encoding='utf8'))

    def test_native_failure_is_logged_but_not_returned_as_private_details(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(ReconstructionFailure) as raised:
                _run([sys.executable, '-u', '-c', 'print("private native diagnostic"); raise SystemExit(7)'], root, 'failure test')
            self.assertNotIn('private native diagnostic', str(raised.exception))
            log = (root / 'logs/failure_test.log').read_text(encoding='utf8')
            self.assertIn('private native diagnostic', log)
            self.assertIn('EXIT: 7', log)

    def test_timeout_kills_child_and_leaves_a_readable_log(self):
        with tempfile.TemporaryDirectory() as folder, patch('app.reconstruction.COMMAND_TIMEOUT_SECONDS', .2):
            root = Path(folder)
            with self.assertRaises(ReconstructionFailure):
                _run([sys.executable, '-u', '-c', 'import time; print("started"); time.sleep(60)'], root, 'timeout test')
            self.assertIn('STATUS: TIMEOUT', (root / 'logs/timeout_test.log').read_text(encoding='utf8'))


if __name__ == '__main__':
    unittest.main()
