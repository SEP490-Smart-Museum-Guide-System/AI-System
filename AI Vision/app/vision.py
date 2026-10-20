from functools import lru_cache
import io
import os
from threading import Lock

import numpy as np
import open_clip
from PIL import Image, ImageOps, UnidentifiedImageError
import torch

from app import settings


class InvalidImage(ValueError):
    pass


class ImageEncoder:
    def __init__(self) -> None:
        settings.MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        torch.set_num_threads(max(1, int(os.getenv("MODEL_NUM_THREADS", "2"))))
        self._device = "cpu"
        self._model, _, self._preprocess = open_clip.create_model_and_transforms(
            settings.MODEL_NAME,
            pretrained=settings.PRETRAINED,
            device=self._device,
            cache_dir=str(settings.MODEL_CACHE_DIR),
        )
        self._model.eval()
        self._lock = Lock()

    def encode(self, image_bytes: bytes) -> np.ndarray:
        try:
            with Image.open(io.BytesIO(image_bytes)) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
                image.thumbnail((1600, 1600))
                tensor = self._preprocess(image).unsqueeze(0).to(self._device)
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise InvalidImage("Uploaded file is not a supported image") from exc

        with self._lock, torch.inference_mode():
            vector = self._model.encode_image(tensor)
            vector = vector / vector.norm(dim=-1, keepdim=True).clamp_min(1e-12)
        return vector.cpu().numpy().astype(np.float32).reshape(-1)


@lru_cache(maxsize=1)
def get_encoder() -> ImageEncoder:
    return ImageEncoder()


def cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left_norm = np.linalg.norm(left)
    right_norm = np.linalg.norm(right)
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return float(np.dot(left, right) / (left_norm * right_norm))
