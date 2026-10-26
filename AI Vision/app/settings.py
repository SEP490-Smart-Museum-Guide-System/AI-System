import os
from pathlib import Path


MODEL_REPO_ID = os.getenv("CLIP_ONNX_REPO_ID", "infinilabs/pizza-clip-base-v1")
MODEL_REVISION = os.getenv("CLIP_ONNX_REVISION", "main")
MODEL_FILENAME = os.getenv("CLIP_ONNX_FILENAME", "clip-vit-base-patch32-vision.onnx")
MODEL_CACHE_DIR = Path(os.getenv("MODEL_CACHE_DIR", "/models"))
DB_HOST = os.getenv("AI_SYSTEM_DB_HOST", "host.docker.internal")
DB_PORT = int(os.getenv("AI_SYSTEM_DB_PORT", "5432"))
DB_NAME = os.getenv("AI_SYSTEM_DB_NAME", "smgs_db")
DB_USER = os.getenv("AI_SYSTEM_DB_USER", "postgres")
DB_PASSWORD = os.getenv("AI_SYSTEM_DB_PASSWORD", "")
DB_SCHEMA = os.getenv("AI_VISION_DB_SCHEMA", "ai_vision")
MODEL_INPUT_SIZE = 224
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", str(10 * 1024 * 1024)))
MAX_REFERENCE_IMAGES_PER_ARTIFACT = int(
    os.getenv("MAX_REFERENCE_IMAGES_PER_ARTIFACT", "20")
)
MIN_SIMILARITY = float(os.getenv("MIN_SIMILARITY", "0.72"))
MIN_MARGIN = float(os.getenv("MIN_MARGIN", "0.04"))
SERVICE_API_KEY = os.getenv("AI_SERVICE_API_KEY", "")
