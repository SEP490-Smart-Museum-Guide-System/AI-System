"""Download the selected Piper voice and shared eSpeak data on first start."""

import logging
import os
from pathlib import Path
import tarfile
import tempfile
from urllib.request import urlopen

from app.config import get_settings

LOGGER = logging.getLogger(__name__)
VOICE_ARCHIVE_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"
    "vits-piper-vi_VN-vais1000-medium.tar.bz2"
)
ESPEAK_ARCHIVE_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"
    "espeak-ng-data.tar.bz2"
)


def _safe_extract(archive_path: Path, destination: Path) -> None:
    destination_resolved = destination.resolve()
    with tarfile.open(archive_path, "r:bz2") as archive:
        members, total_size = [], 0
        for member in archive:
            total_size += member.size
            if len(members) >= 10000 or total_size > 2 * 1024 ** 3:
                raise RuntimeError("Model archive exceeds extraction limits")
            if not member.isfile() and not member.isdir():
                raise RuntimeError("Model archive must only contain regular files and directories")
            target = (destination / member.name).resolve()
            if target != destination_resolved and destination_resolved not in target.parents:
                raise RuntimeError(f"Unsafe path in model archive: {member.name}")
            members.append(member)
        archive.extractall(destination, members=members, filter="data")


def _download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.info("Downloading %s", url)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".part", delete=False) as file:
            temporary = Path(file.name)
            with urlopen(url, timeout=60) as response:
                size = 0
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > 1024 ** 3:
                        raise RuntimeError("Model download exceeds 1 GiB")
                    file.write(chunk)
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def ensure_model_assets() -> None:
    settings = get_settings()
    settings.model_dir.mkdir(parents=True, exist_ok=True)

    if not settings.model_path.is_file() or not settings.tokens_path.is_file():
        archive_path = settings.model_dir / "piper-vietnamese.tar.bz2"
        _download(VOICE_ARCHIVE_URL, archive_path)
        _safe_extract(archive_path, settings.model_dir)
        archive_path.unlink(missing_ok=True)

    if not (settings.espeak_data_dir / "phontab").exists():
        archive_path = settings.model_dir / "espeak-ng-data.tar.bz2"
        _download(ESPEAK_ARCHIVE_URL, archive_path)
        _safe_extract(archive_path, settings.model_dir)
        archive_path.unlink(missing_ok=True)

    missing = [
        path
        for path in (
            settings.model_path,
            settings.tokens_path,
            settings.espeak_data_dir / "phontab",
        )
        if not path.exists()
    ]
    if missing:
        raise RuntimeError(
            "Piper model download completed, but required files are missing: "
            + ", ".join(map(str, missing))
        )


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    ensure_model_assets()
