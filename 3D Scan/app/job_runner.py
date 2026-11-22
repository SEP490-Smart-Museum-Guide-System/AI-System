"""One isolated process group per scan, including all native descendants."""
import logging
import os
from pathlib import Path
import signal
import sys
import threading

from . import jobs
from .reconstruction import process


def watch_cancellation(job_id, stopped):
    while not stopped.wait(1):
        try:
            record = jobs.get(job_id)
            if record and record['status'] == 'CANCELLED':
                # The API starts this process in its own POSIX session. Never
                # signal the web server's group if invoked by hand incorrectly.
                if os.name == 'posix' and os.getpgrp() == os.getpid():
                    os.killpg(os.getpgrp(), signal.SIGTERM)
                else:
                    os.kill(os.getpid(), signal.SIGTERM)
                return
        except Exception:
            logging.exception('Unable to check scan cancellation')


def run(job_id, root):
    def terminate(_signum, _frame):
        # Unwind _run's finally so its native child is reaped before exiting.
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, terminate)
    record = jobs.get(job_id)
    if not record or record['status'] != 'PROCESSING':
        return
    stopped = threading.Event()
    watcher = threading.Thread(target=watch_cancellation, args=(job_id, stopped), daemon=True)
    watcher.start()
    try:
        if (root / 'config.json').is_file():
            from tools.local_scan_worker import run as run_dataset
            run_dataset(root / 'dataset', root, managed_upload=True,
                        on_update=lambda **changes: jobs.update(job_id, **changes))
        else:
            process(job_id, root)
    finally:
        stopped.set()
        watcher.join(timeout=6)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    run(sys.argv[1], Path(sys.argv[2]))
