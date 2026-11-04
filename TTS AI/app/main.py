from contextlib import asynccontextmanager
import logging
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, Response

from app.config import get_settings
from app.model_assets import ensure_model_assets
from app.schemas import SpeechRequest
from app.synthesizer import SpeechBusy, get_synthesizer

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_model_assets()
    get_synthesizer()
    app.state.model_ready = True
    try:
        yield
    finally:
        app.state.model_ready = False


app = FastAPI(
    title="SMGS Vietnamese TTS Service",
    description=(
        "Creates speech from museum narration text that has already been "
        "reviewed and published by museum staff. This service does not author content."
    ),
    version="0.1.0",
    lifespan=lifespan,
)
app.state.model_ready = False


def require_service_key(x_service_key: str | None = Header(default=None)) -> None:
    expected = get_settings().service_api_key
    # Optional for the existing local FE proxy; enable at the server-side gateway in deployment.
    if expected and (not x_service_key or not secrets.compare_digest(expected.encode(), x_service_key.encode())):
        raise HTTPException(401, detail="Thông tin xác thực dịch vụ không hợp lệ.")


@app.middleware("http")
async def authenticate_before_body(request, call_next):
    if request.url.path.startswith('/api/'):
        try:
            require_service_key(request.headers.get('x-service-key'))
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={'detail': exc.detail})
    return await call_next(request)


@app.get("/health")
@app.get("/ready")
def health() -> dict[str, object]:
    settings = get_settings()
    model_ready = app.state.model_ready
    if not model_ready:
        raise HTTPException(503, detail="Bộ đọc tiếng Việt đang khởi động.")
    return {
        "status": "ok" if model_ready else "starting",
        "service": "tts-service",
        "voice": settings.voice,
        "model_ready": model_ready,
        "language": "vi-VN",
    }


@app.get("/live")
async def live():
    return {"status": "ok", "service": "tts-service"}


@app.post(
    "/api/v1/speech",
    response_class=Response,
    responses={200: {"content": {"audio/wav": {}}}},
    dependencies=[Depends(require_service_key)],
)
def create_speech(request: SpeechRequest) -> Response:
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Nội dung thuyết minh không được để trống.")

    settings = get_settings()
    if len(text) > settings.max_text_chars:
        raise HTTPException(
            status_code=413,
            detail=f"Nội dung vượt giới hạn {settings.max_text_chars} ký tự.",
        )

    try:
        audio, cache_hit = get_synthesizer().generate(text, request.speed)
    except SpeechBusy as exc:
        raise HTTPException(503, detail=str(exc), headers={"Retry-After": "3"}) from exc
    except Exception as exc:
        LOGGER.exception("Speech generation failed")
        raise HTTPException(status_code=503, detail="Chưa tạo được giọng đọc. Vui lòng thử lại.", headers={"Retry-After": "3"}) from exc

    return Response(
        content=audio,
        media_type="audio/wav",
        headers={
            "Cache-Control": "private, max-age=86400",
            "X-TTS-Cache": "HIT" if cache_hit else "MISS",
            "X-TTS-Voice": settings.voice,
        },
    )
