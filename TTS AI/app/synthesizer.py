from functools import lru_cache
from array import array
import hashlib
import io
import logging
import math
import re
import struct
from threading import Lock
import unicodedata
import wave

import sherpa_onnx

from app.config import get_settings
from app.audio_cache import AudioCache

LOGGER = logging.getLogger(__name__)
PROSODY_VERSION = "museum-v4"


def normalize_narration(text: str) -> str:
    """Keep punctuation and blank-line paragraphs; fold layout-only whitespace."""
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [" ".join(part.split()) for part in re.split(r"\n\s*\n", text)]
    return "\n\n".join(part for part in paragraphs if part)


def narration_segments(text: str, sentence_ms: int, clause_ms: int, paragraph_ms: int):
    """Retain spoken text, adding breaks only at unambiguous punctuation/paragraphs."""
    abbreviations = {'ts', 'ths', 'gs', 'pgs', 'tp', 'p', 'q', 'st', 'mr', 'mrs', 'dr', 'v.v', 'v.d'}
    pending_pause = 0
    for paragraph in text.split('\n\n'):
        start = 0
        for match in re.finditer(r'''([,;:.!?…]+["”’»)]*)(\s+)''', paragraph):
            punctuation = match.group(1).rstrip('"”’»)')
            following = paragraph[match.end():]
            if not following:
                continue
            if punctuation in {'.', ',', ':'} and following[0].isdigit():
                continue  # Numbers, dates, decimal separators, or numbered labels.
            if punctuation == '.':
                token = paragraph[:match.start()].rsplit(' ', 1)[-1]
                if token.casefold() in abbreviations or (len(token) == 1 and token.isalpha()):
                    continue
            pause = sentence_ms if any(char in punctuation for char in '.!?…') else clause_ms
            if pause == 0:
                continue
            yield paragraph[start:match.start(2)], pending_pause
            start = match.end()
            pending_pause = pause
        remainder = paragraph[start:]
        if remainder:
            yield remainder, pending_pause
        pending_pause = paragraph_ms


class SpeechBusy(RuntimeError):
    pass


class PiperSynthesizer:
    # Both voices share the same Azure CPU allocation.
    _generation_lock = Lock()

    def __init__(self, language: str = "vi") -> None:
        settings = get_settings(language)
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
            sherpa_onnx.OfflineTtsConfig(model=model, max_num_sentences=1, silence_scale=settings.silence_scale)
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
        self._speed_factor = settings.speed_factor
        self._silence_scale = settings.silence_scale
        self._paragraph_pause_ms = settings.paragraph_pause_ms
        self._sentence_pause_ms = settings.sentence_pause_ms
        self._clause_pause_ms = settings.clause_pause_ms

    def generate(self, text: str, speed: float) -> tuple[bytes, bool]:
        normalized_text = normalize_narration(text)
        # Prosody changes must not reuse the old, fast/compressed-pause WAV cache.
        prosody = f"{PROSODY_VERSION}:{self._speed_factor.hex()}:{self._silence_scale.hex()}:{self._paragraph_pause_ms}:{self._sentence_pause_ms}:{self._clause_pause_ms}"
        cache_key = hashlib.sha256(
            f"{self._voice}\0{self._model_identity}\0{prosody}\0{float(speed).hex()}\0{normalized_text}".encode("utf-8")
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

            samples = array('f')
            sample_rate = None
            generation = sherpa_onnx.GenerationConfig()
            generation.sid = 0
            generation.speed = speed * self._speed_factor
            # The Python (text, sid, speed) overload creates its own config and
            # ignores OfflineTtsConfig.silence_scale in sherpa-onnx 1.13.8.
            generation.silence_scale = self._silence_scale
            for segment, pause_ms in narration_segments(normalized_text, self._sentence_pause_ms,
                                                         self._clause_pause_ms, self._paragraph_pause_ms):
                result = self._tts.generate(text=segment, config=generation)
                if len(result.samples) == 0 or result.sample_rate <= 0:
                    raise RuntimeError("Piper generated an empty audio result")
                if sample_rate is not None:
                    if sample_rate != result.sample_rate:
                        raise RuntimeError("Piper returned inconsistent sample rates")
                    samples.extend(array('f', [0.0]) * round(sample_rate * pause_ms / 1000))
                sample_rate = result.sample_rate
                samples.extend(result.samples)
            if not samples or sample_rate is None:
                raise RuntimeError("Piper generated an empty audio result")
            wav_bytes = _to_pcm_wav(samples, sample_rate)
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


@lru_cache(maxsize=2)
def get_synthesizer(language: str = "vi") -> PiperSynthesizer:
    LOGGER.info("Loading Piper voice model")
    return PiperSynthesizer(language)
