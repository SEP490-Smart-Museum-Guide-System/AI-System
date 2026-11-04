"""Bounded WAV cache with atomic, independent writers."""
import io
import logging
from pathlib import Path
import re
import tempfile
import wave

LOGGER = logging.getLogger(__name__)


class AudioCache:
    def __init__(self, directory: Path, max_bytes: int, max_files: int):
        if max_bytes <= 0 or max_files <= 0:
            raise ValueError("Giới hạn cache phải lớn hơn 0.")
        self.directory, self.max_bytes, self.max_files = directory, max_bytes, max_files
        directory.mkdir(parents=True, exist_ok=True)
        self._trim()

    def _path(self, key: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{64}", key):
            raise ValueError("Cache key không hợp lệ.")
        return self.directory / f"{key}.wav"

    def get(self, key: str) -> bytes | None:
        path = self._path(key)
        try:
            audio = path.read_bytes()
            with wave.open(io.BytesIO(audio), "rb") as wav:
                if wav.getnframes() <= 0 or len(wav.readframes(wav.getnframes())) != wav.getnframes() * wav.getnchannels() * wav.getsampwidth():
                    raise ValueError("Audio cache bị thiếu dữ liệu.")
        except FileNotFoundError:
            return None
        except (OSError, EOFError, wave.Error, ValueError):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return None
        try:
            path.touch()
        except OSError:
            pass
        return audio

    def put(self, key: str, audio: bytes) -> None:
        if len(audio) > self.max_bytes:
            return  # Synthesis still succeeds; a single large file cannot exceed the cache budget.
        path = self._path(key)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.directory, prefix=f"{key}.", suffix=".part", delete=False) as file:
                temporary = Path(file.name)
                file.write(audio)
            temporary.replace(path)
            self._trim()
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _trim(self) -> None:
        entries = []
        for path in self.directory.glob("*.wav"):
            if not re.fullmatch(r"[a-f0-9]{64}", path.stem):
                continue
            try:
                info = path.stat()
                entries.append((info.st_mtime_ns, path, info.st_size))
            except FileNotFoundError:
                pass
        total, count = sum(item[2] for item in entries), len(entries)
        for _, path, size in sorted(entries):
            if total <= self.max_bytes and count <= self.max_files:
                break
            try:
                path.unlink(missing_ok=True)
                total -= size
                count -= 1
            except OSError:
                LOGGER.warning("Chưa dọn được tệp cache cũ", exc_info=True)
