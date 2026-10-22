from functools import lru_cache
import io
import os
from pathlib import Path
from threading import Lock

import numpy as np
import onnxruntime as ort
from huggingface_hub import snapshot_download
from PIL import Image, ImageOps, UnidentifiedImageError

from app import settings


class InvalidImage(ValueError):
    pass


class ImageEncoder:
    def __init__(self) -> None:
        settings.MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        snapshot = Path(snapshot_download(
            repo_id=settings.MODEL_REPO_ID,
            revision=settings.MODEL_REVISION,
            cache_dir=str(settings.MODEL_CACHE_DIR),
            allow_patterns=[f"{settings.MODEL_FILENAME}*"],
        ))
        model_path = snapshot / settings.MODEL_FILENAME
        if not model_path.is_file():
            raise RuntimeError("ONNX image encoder was not found in the configured model repository")

        options = ort.SessionOptions()
        options.intra_op_num_threads = max(1, int(os.getenv("MODEL_NUM_THREADS", "2")))
        options.inter_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(model_path), sess_options=options, providers=["CPUExecutionProvider"]
        )
        inputs = self._session.get_inputs()
        if not inputs:
            raise RuntimeError("ONNX image encoder does not expose an input tensor")
        self._input_name = next(
            (item.name for item in inputs if item.name == "pixel_values"), inputs[0].name
        )
        outputs = self._session.get_outputs()
        if not outputs:
            raise RuntimeError("ONNX image encoder does not expose an output tensor")
        self._output_name = next(
            (item.name for item in outputs if item.name in {"image_embeds", "image_embedding", "embeddings"}),
            outputs[0].name,
        )
        self._lock = Lock()
        # Use the immutable Hub commit hash, even when the configured revision is `main`.
        self._model_id = f"{settings.MODEL_REPO_ID}@{snapshot.name}/{settings.MODEL_FILENAME}"

    @property
    def model_id(self) -> str:
        return self._model_id

    def encode(self, image_bytes: bytes) -> np.ndarray:
        try:
            with Image.open(io.BytesIO(image_bytes)) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
                image = ImageOps.fit(
                    image,
                    (settings.MODEL_INPUT_SIZE, settings.MODEL_INPUT_SIZE),
                    method=Image.Resampling.BICUBIC,
                )
                pixels = np.asarray(image, dtype=np.float32) / 255.0
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise InvalidImage("Uploaded file is not a supported image") from exc

        mean = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
        std = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
        pixels = (pixels - mean) / std
        tensor = np.transpose(pixels, (2, 0, 1))[None, ...].astype(np.float32)
        with self._lock:
            result = self._session.run([self._output_name], {self._input_name: tensor})[0]

        vector = np.asarray(result, dtype=np.float32).reshape(-1)
        if vector.size != 512:
            raise RuntimeError(f"Expected a 512-dimensional CLIP embedding, got {vector.size}")
        norm = np.linalg.norm(vector)
        if not np.isfinite(norm) or norm <= 1e-12:
            raise RuntimeError("ONNX image encoder returned an invalid embedding")
        return vector / norm


@lru_cache(maxsize=1)
def get_encoder() -> ImageEncoder:
    return ImageEncoder()


def cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left_norm = np.linalg.norm(left)
    right_norm = np.linalg.norm(right)
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return float(np.dot(left, right) / (left_norm * right_norm))
