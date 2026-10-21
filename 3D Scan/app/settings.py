import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("SCAN_DATA_DIR", ROOT / "state")).resolve()
DATABASE_PATH = DATA_DIR / "scan_jobs.sqlite3"
COLMAP_COMMAND = os.getenv("COLMAP_COMMAND", "colmap")
SERVICE_API_KEY = os.getenv("SCAN_SERVICE_API_KEY", "")
MAX_IMAGES = int(os.getenv("SCAN_MAX_IMAGES", "80"))
MAX_IMAGE_BYTES = int(os.getenv("SCAN_MAX_IMAGE_BYTES", str(20 * 1024 * 1024)))
MAX_TOTAL_BYTES = int(os.getenv("SCAN_MAX_TOTAL_BYTES", str(500 * 1024 * 1024)))

