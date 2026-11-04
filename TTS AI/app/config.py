from functools import lru_cache
import os
from pathlib import Path


@lru_cache
def get_settings() -> "Settings":
    model_dir = Path(os.getenv("TTS_MODEL_DIR", "/models"))
    cache_dir = Path(os.getenv("TTS_CACHE_DIR", "/data/audio-cache"))
    voice = "vi_VN-vais1000-medium"
    voice_dir = model_dir / f"vits-piper-{voice}"

    return Settings(
        model_dir=model_dir,
        cache_dir=cache_dir,
        voice=voice,
        model_path=voice_dir / f"{voice}.onnx",
        tokens_path=voice_dir / "tokens.txt",
        espeak_data_dir=model_dir / "espeak-ng-data",
        max_text_chars=int(os.getenv("TTS_MAX_TEXT_CHARS", "12000")),
        num_threads=max(1, int(os.getenv("TTS_NUM_THREADS", "2"))),
        cache_max_bytes=int(os.getenv("TTS_CACHE_MAX_BYTES", str(512 * 1024 * 1024))),
        cache_max_files=int(os.getenv("TTS_CACHE_MAX_FILES", "1000")),
        queue_timeout=float(os.getenv("TTS_QUEUE_TIMEOUT_SECONDS", "2")),
        service_api_key=os.getenv("TTS_SERVICE_API_KEY", ""),
    )


class Settings:
    def __init__(
        self,
        *,
        model_dir: Path,
        cache_dir: Path,
        voice: str,
        model_path: Path,
        tokens_path: Path,
        espeak_data_dir: Path,
        max_text_chars: int,
        num_threads: int,
        cache_max_bytes: int = 512 * 1024 * 1024,
        cache_max_files: int = 1000,
        queue_timeout: float = 2,
        service_api_key: str = "",
    ) -> None:
        self.model_dir = model_dir
        self.cache_dir = cache_dir
        self.voice = voice
        self.model_path = model_path
        self.tokens_path = tokens_path
        self.espeak_data_dir = espeak_data_dir
        self.max_text_chars = max_text_chars
        self.num_threads = num_threads
        if not 0 <= queue_timeout <= 30 or not 1 <= max_text_chars <= 12000:
            raise ValueError("Cấu hình giới hạn TTS không hợp lệ.")
        self.cache_max_bytes = cache_max_bytes
        self.cache_max_files = cache_max_files
        self.queue_timeout = queue_timeout
        self.service_api_key = service_api_key
