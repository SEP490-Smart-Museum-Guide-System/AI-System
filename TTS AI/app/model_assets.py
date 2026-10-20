"""Download the selected Piper voice and shared eSpeak data on first start."""

import logging
import os
from pathlib import Path
import tarfile
from urllib.request import urlretrieve

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
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if target != destination_resolved and destination_resolved not in target.parents:
                raise RuntimeError(f"Unsafe path in model archive: {member.name}")
        archive.extractall(destination)


def _download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    LOGGER.info("Downloading %s", url)
    urlretrieve(url, temporary)
    temporary.replace(target)


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
