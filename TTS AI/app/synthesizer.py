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


def _roman_value(value: str) -> int | None:
    numeral = value.upper()
    if not re.fullmatch(r"M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})", numeral):
        return None
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    for index, char in enumerate(numeral):
        current = values[char]
        total += -current if index + 1 < len(numeral) and current < values[numeral[index + 1]] else current
    return total


def _vietnamese_integer(value: int) -> str:
    digits = ("không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín")
    if value < 10:
        return digits[value]
    if value < 20:
        remainder = value - 10
        return "mười" if remainder == 0 else "mười " + ("lăm" if remainder == 5 else digits[remainder])
    tens, remainder = divmod(value, 10)
    result = digits[tens] + " mươi"
    if remainder:
        result += " " + ({1: "mốt", 4: "tư", 5: "lăm"}.get(remainder, digits[remainder]))
    return result


def normalize_narration(text: str, language: str = "vi") -> str:
    """Normalize layout and expand common measurement units for the selected voice."""
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [" ".join(part.split()) for part in re.split(r"\n\s*\n", text)]
    text = "\n\n".join(part for part in paragraphs if part)

    vi_units = {
        "km": "ki-lô-mét", "mm": "mi-li-mét", "cm": "xăng-ti-mét", "m": "mét",
        "mg": "mi-li-gam", "kg": "ki-lô-gam", "g": "gam",
        "ml": "mi-li-lít", "l": "lít",
        "mm²": "mi-li-mét vuông", "cm²": "xăng-ti-mét vuông", "m²": "mét vuông",
        "mm³": "mi-li-mét khối", "cm³": "xăng-ti-mét khối", "m³": "mét khối",
    }
    en_units = {
        "km": "kilometer", "mm": "millimeter", "cm": "centimeter", "m": "meter",
        "mg": "milligram", "kg": "kilogram", "g": "gram",
        "ml": "milliliter", "l": "liter",
        "mm²": "square millimeter", "cm²": "square centimeter", "m²": "square meter",
        "mm³": "cubic millimeter", "cm³": "cubic centimeter", "m³": "cubic meter",
    }
    is_vietnamese = language.split("-")[0].lower() == "vi"
    units = vi_units if is_vietnamese else en_units
    unit_pattern = "|".join(re.escape(unit) for unit in sorted(units, key=len, reverse=True))

    def expand_measurement(match: re.Match[str]) -> str:
        number, unit = match.group("number"), match.group("unit").lower()
        spoken_unit = units[unit]
        if not is_vietnamese:
            try:
                if float(number.replace(",", ".")) != 1:
                    spoken_unit += "s"
            except ValueError:
                spoken_unit += "s"
        return f"{number} {spoken_unit}"

    text = re.sub(
        rf"(?P<number>\d+(?:[.,]\d+)?)\s*(?P<unit>{unit_pattern})(?![A-Za-zÀ-ỹ])",
        expand_measurement,
        text,
        flags=re.IGNORECASE,
    )
    # Expand longer standalone abbreviations too; single-letter m/g/l are
    # expanded only when attached to a number to avoid changing ordinary prose.
    safe_units = {key: value for key, value in units.items() if len(key) > 1}
    safe_pattern = "|".join(re.escape(unit) for unit in sorted(safe_units, key=len, reverse=True))
    text = re.sub(
        rf"(?<!\w)(?P<unit>{safe_pattern})(?!\w)",
        lambda match: safe_units[match.group("unit").lower()],
        text,
        flags=re.IGNORECASE,
    )
    separator = "nhân" if is_vietnamese else "by"
    text = re.sub(r"(?<=\d)\s*[x×]\s*(?=\d)", f" {separator} ", text, flags=re.IGNORECASE)

    if is_vietnamese:
        def expand_century(match: re.Match[str]) -> str:
            first = _roman_value(match.group("first"))
            second = _roman_value(match.group("second")) if match.group("second") else None
            if first is None or first > 99 or (match.group("second") and (second is None or second > 99)):
                return match.group(0)
            phrase = f"{match.group('prefix')} {_vietnamese_integer(first)}"
            if second is not None:
                phrase += f" đến {_vietnamese_integer(second)}"
            return phrase

        text = re.sub(
            r"(?P<prefix>thế\s*kỷ|thế\s*kỉ)\s+(?:thứ\s+)?(?P<first>[IVXLCDM]+)(?:\s*[-–—]\s*(?P<second>[IVXLCDM]+))?\b",
            expand_century,
            text,
            flags=re.IGNORECASE,
        )

    return text


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
        self._language = language
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
        normalized_text = normalize_narration(text, self._language)
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
