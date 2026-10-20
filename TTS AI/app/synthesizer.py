from functools import lru_cache
import hashlib
import io
import logging
from pathlib import Path
import struct
from threading import Lock
import wave

import sherpa_onnx

from app.config import get_settings

LOGGER = logging.getLogger(__name__)


class PiperSynthesizer:
    def __init__(self) -> None:
        settings = get_settings()
        vits = sherpa_onnx.OfflineTtsVitsModelConfig(
            model=str(settings.model_path),
            tokens=str(settings.tokens_path),
            data_dir=str(settings.espeak_data_dir),
        )
        model = sherpa_onnx.OfflineTtsModelConfig(
            vits=vits,
            num_threads=settings.num_threads,
            debug=False,
        )
        self._tts = sherpa_onnx.OfflineTts(
            sherpa_onnx.OfflineTtsConfig(model=model)
        )
        self._voice = settings.voice
        self._cache_dir = settings.cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._generation_lock = Lock()

    def generate(self, text: str, speed: float) -> tuple[bytes, bool]:
        normalized_text = " ".join(text.split())
        cache_key = hashlib.sha256(
            f"{self._voice}\0{speed:.3f}\0{normalized_text}".encode("utf-8")
        ).hexdigest()
        cached_path = self._cache_dir / f"{cache_key}.wav"
        with self._generation_lock:
            if cached_path.is_file():
                return cached_path.read_bytes(), True

            result = self._tts.generate(
                text=normalized_text,
                sid=0,
                speed=speed,
            )
            if len(result.samples) == 0:
                raise RuntimeError("Piper generated an empty audio result")

            wav_bytes = _to_pcm_wav(result.samples, result.sample_rate)
            temporary_path = cached_path.with_suffix(".wav.part")
            temporary_path.write_bytes(wav_bytes)
            temporary_path.replace(cached_path)
            return wav_bytes, False


def _to_pcm_wav(samples: object, sample_rate: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        pcm = bytearray()
        for sample in samples:  # type: ignore[union-attr]
            value = max(-1.0, min(1.0, float(sample)))
            pcm.extend(struct.pack("<h", round(value * 32767)))
        wav_file.writeframes(pcm)
    return output.getvalue()


@lru_cache(maxsize=1)
def get_synthesizer() -> PiperSynthesizer:
    LOGGER.info("Loading Piper voice model")
    return PiperSynthesizer()
