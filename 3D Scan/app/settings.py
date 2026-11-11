import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("SCAN_DATA_DIR", ROOT / "state")).resolve()
DB_HOST = os.getenv("AI_SYSTEM_DB_HOST", "localhost")
DB_PORT = int(os.getenv("AI_SYSTEM_DB_PORT", "5432"))
DB_NAME = os.getenv("AI_SYSTEM_DB_NAME", "smgs_db")
DB_USER = os.getenv("AI_SYSTEM_DB_USER", "postgres")
DB_PASSWORD = os.getenv("AI_SYSTEM_DB_PASSWORD", "")
DB_SCHEMA = os.getenv("SCAN_DB_SCHEMA", "ai_3d_scan")
COLMAP_COMMAND = os.getenv("COLMAP_COMMAND", "colmap")
COLMAP_CAMERA_MODEL = os.getenv("SCAN_COLMAP_CAMERA_MODEL", "SIMPLE_RADIAL")
if COLMAP_CAMERA_MODEL not in {"SIMPLE_RADIAL", "PINHOLE", "SIMPLE_PINHOLE", "OPENCV"}:
    raise ValueError("Unsupported SCAN_COLMAP_CAMERA_MODEL")
OPENMVS_BIN_DIR = os.getenv("OPENMVS_BIN_DIR", "")
OPENMVS_COMMANDS = {
    "InterfaceCOLMAP": os.getenv("OPENMVS_INTERFACE_COLMAP_COMMAND", "InterfaceCOLMAP"),
    "DensifyPointCloud": os.getenv("OPENMVS_DENSIFY_COMMAND", "DensifyPointCloud"),
    "ReconstructMesh": os.getenv("OPENMVS_MESH_COMMAND", "ReconstructMesh"),
    "RefineMesh": os.getenv("OPENMVS_REFINE_COMMAND", "RefineMesh"),
    "TextureMesh": os.getenv("OPENMVS_TEXTURE_COMMAND", "TextureMesh"),
}
SERVICE_API_KEY = os.getenv("SCAN_SERVICE_API_KEY", "")
MIN_IMAGES = 5
MAX_IMAGES = int(os.getenv("SCAN_MAX_IMAGES", "80"))
MAX_IMAGE_BYTES = int(os.getenv("SCAN_MAX_IMAGE_BYTES", str(20 * 1024 * 1024)))
MAX_TOTAL_BYTES = int(os.getenv("SCAN_MAX_TOTAL_BYTES", str(500 * 1024 * 1024)))
MAX_IMAGE_PIXELS = int(os.getenv("SCAN_MAX_IMAGE_PIXELS", "20000000"))
MAX_METADATA_BYTES = int(os.getenv("SCAN_MAX_METADATA_BYTES", "16384"))

