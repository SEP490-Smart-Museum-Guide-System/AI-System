from functools import lru_cache
import hashlib
import io
import logging
import math
import struct
from threading import Lock
import unicodedata
import wave

import sherpa_onnx

from app.config import get_settings
from app.audio_cache import AudioCache

LOGGER = logging.getLogger(__name__)


class SpeechBusy(RuntimeError):
    pass


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
        # A replaced model must not reuse audio from the previous voice weights/tokens.
        identity = hashlib.sha256()
        for path in (settings.model_path, settings.tokens_path):
            with path.open('rb') as file:
                while chunk := file.read(1024 * 1024):
                    identity.update(chunk)
        identity.update(str(getattr(sherpa_onnx, '__version__', 'unknown')).encode())
        self._model_identity = identity.hexdigest()
        self._cache = AudioCache(settings.cache_dir, settings.cache_max_bytes, settings.cache_max_files)
        self._queue_timeout = settings.queue_timeout
        self._generation_lock = Lock()

    def generate(self, text: str, speed: float) -> tuple[bytes, bool]:
        normalized_text = unicodedata.normalize("NFC", " ".join(text.split()))
        cache_key = hashlib.sha256(
            f"{self._voice}\0{self._model_identity}\0{float(speed).hex()}\0{normalized_text}".encode("utf-8")
        ).hexdigest()
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached, True
        if not self._generation_lock.acquire(timeout=self._queue_timeout):
            raise SpeechBusy("Bộ đọc đang bận. Vui lòng thử lại.")
        try:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached, True

            result = self._tts.generate(
                text=normalized_text,
                sid=0,
                speed=speed,
            )
            if len(result.samples) == 0:
                raise RuntimeError("Piper generated an empty audio result")

            wav_bytes = _to_pcm_wav(result.samples, result.sample_rate)
            try:
                self._cache.put(cache_key, wav_bytes)
            except OSError:
                LOGGER.warning("Không ghi được cache; vẫn trả audio vừa tạo", exc_info=True)
            return wav_bytes, False
        finally:
            self._generation_lock.release()


def _to_pcm_wav(samples: object, sample_rate: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        pcm = bytearray()
        for sample in samples:  # type: ignore[union-attr]
            if not math.isfinite(float(sample)):
                raise ValueError("Bộ đọc trả mẫu âm thanh không hợp lệ.")
            value = max(-1.0, min(1.0, float(sample)))
            pcm.extend(struct.pack("<h", round(value * 32767)))
        wav_file.writeframes(pcm)
    return output.getvalue()


@lru_cache(maxsize=1)
def get_synthesizer() -> PiperSynthesizer:
    LOGGER.info("Loading Piper voice model")
    return PiperSynthesizer()
