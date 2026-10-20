from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from app.config import get_settings
from app.model_assets import ensure_model_assets
from app.schemas import SpeechRequest
from app.synthesizer import get_synthesizer

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_model_assets()
    get_synthesizer()
    yield


app = FastAPI(
    title="SMGS Vietnamese TTS Service",
    description=(
        "Creates speech from museum narration text that has already been "
        "reviewed and published by museum staff. This service does not author content."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    model_ready = settings.model_path.is_file() and settings.tokens_path.is_file()
    return {
        "status": "ok" if model_ready else "starting",
        "service": "tts-service",
        "voice": settings.voice,
    }


@app.post(
    "/api/v1/speech",
    response_class=Response,
    responses={200: {"content": {"audio/wav": {}}}},
)
def create_speech(request: SpeechRequest) -> Response:
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Text must not be blank")

    settings = get_settings()
    if len(text) > settings.max_text_chars:
        raise HTTPException(
            status_code=413,
            detail=f"Text exceeds the {settings.max_text_chars} character limit",
        )

    try:
        audio, cache_hit = get_synthesizer().generate(text, request.speed)
    except Exception as exc:
        LOGGER.exception("Speech generation failed")
        raise HTTPException(status_code=503, detail="Speech generation is unavailable") from exc

    return Response(
        content=audio,
        media_type="audio/wav",
        headers={
            "Cache-Control": "private, max-age=86400",
            "X-TTS-Cache": "HIT" if cache_hit else "MISS",
            "X-TTS-Voice": settings.voice,
        },
    )
