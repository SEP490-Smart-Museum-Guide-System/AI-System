import os
from pathlib import Path


MODEL_NAME = os.getenv("CLIP_MODEL_NAME", "ViT-B-32")
PRETRAINED = os.getenv("CLIP_PRETRAINED", "laion2b_s34b_b79k")
DATA_DIR = Path(os.getenv("AI_DATA_DIR", "/data"))
MODEL_CACHE_DIR = Path(os.getenv("MODEL_CACHE_DIR", "/models"))
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", str(10 * 1024 * 1024)))
MAX_REFERENCE_IMAGES_PER_ARTIFACT = int(
    os.getenv("MAX_REFERENCE_IMAGES_PER_ARTIFACT", "20")
)
MIN_SIMILARITY = float(os.getenv("MIN_SIMILARITY", "0.72"))
MIN_MARGIN = float(os.getenv("MIN_MARGIN", "0.04"))
SERVICE_API_KEY = os.getenv("AI_SERVICE_API_KEY", "")
