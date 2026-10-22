import os
from pathlib import Path


MODEL_REPO_ID = os.getenv("CLIP_ONNX_REPO_ID", "infinilabs/pizza-clip-base-v1")
MODEL_REVISION = os.getenv("CLIP_ONNX_REVISION", "main")
MODEL_FILENAME = os.getenv("CLIP_ONNX_FILENAME", "clip-vit-base-patch32-vision.onnx")
DATA_DIR = Path(os.getenv("AI_DATA_DIR", "/data"))
MODEL_CACHE_DIR = Path(os.getenv("MODEL_CACHE_DIR", "/models"))
MODEL_INPUT_SIZE = 224
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", str(10 * 1024 * 1024)))
MAX_REFERENCE_IMAGES_PER_ARTIFACT = int(
    os.getenv("MAX_REFERENCE_IMAGES_PER_ARTIFACT", "20")
)
MIN_SIMILARITY = float(os.getenv("MIN_SIMILARITY", "0.72"))
MIN_MARGIN = float(os.getenv("MIN_MARGIN", "0.04"))
SERVICE_API_KEY = os.getenv("AI_SERVICE_API_KEY", "")
