from contextlib import asynccontextmanager
import logging
import secrets

import numpy as np
import psycopg
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from app import settings
from app.store import ReferenceLimitReached, ReferenceStore
from app.vision import EncoderUnavailable, InvalidImage, cosine_similarity, get_encoder

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)
store: ReferenceStore | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global store
    if not settings.SERVICE_API_KEY:
        raise RuntimeError("AI_SERVICE_API_KEY must be configured")
    store = ReferenceStore()
    store.initialize()
    get_encoder()  # Load model before accepting traffic; first boot downloads weights.
    app.state.model_ready = True
    try:
        yield
    finally:
        app.state.model_ready = False


app = FastAPI(
    title="SMGS Artifact Vision Service",
    description="Matches artifact photos against reference images indexed by artifact ID.",
    version="0.2.0",
    lifespan=lifespan,
)
app.state.model_ready = False


@app.exception_handler(psycopg.Error)
@app.exception_handler(EncoderUnavailable)
async def unavailable(_, exc: Exception):
    LOGGER.exception("Vision dependency unavailable", exc_info=exc)
    return JSONResponse(status_code=503, content={"detail": "Dịch vụ nhận diện hiện chưa sẵn sàng. Vui lòng thử lại."}, headers={"Retry-After": "3"})


def require_service_key(x_service_key: str | None = Header(default=None)) -> None:
    if not settings.SERVICE_API_KEY or not x_service_key or not secrets.compare_digest(x_service_key.encode(), settings.SERVICE_API_KEY.encode()):
        raise HTTPException(status_code=401, detail="Thông tin xác thực dịch vụ không hợp lệ.")


@app.middleware("http")
async def authenticate_before_upload(request, call_next):
    if request.url.path.startswith('/api/'):
        try:
            require_service_key(request.headers.get('x-service-key'))
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={'detail': exc.detail})
    return await call_next(request)


def read_image(upload: UploadFile) -> bytes:
    content = upload.file.read(settings.MAX_IMAGE_BYTES + 1)
    if not content:
        raise HTTPException(status_code=422, detail="Ảnh không được để trống.")
    if len(content) > settings.MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Ảnh vượt giới hạn dung lượng cho phép.")
    return content


@app.get("/health")
@app.get("/ready")
def health() -> dict[str, object]:
    if not app.state.model_ready:
        raise HTTPException(status_code=503, detail="Bộ nhận diện đang khởi động.")
    encoder = get_encoder()
    return {
        "status": "ok",
        "service": "artifact-vision",
        "model": encoder.model_id,
        "model_ready": True,
        "reference_images": store.count(encoder.model_id),
    }


@app.get("/live")
async def live():
    return {"status": "ok", "service": "artifact-vision"}


@app.post("/api/v1/references", dependencies=[Depends(require_service_key)])
def add_reference(
    artifact_id: int = Query(gt=0),
    image: UploadFile = File(...),
) -> dict[str, object]:
    encoder = get_encoder()
    if store.count_for_artifact(artifact_id, encoder.model_id) >= settings.MAX_REFERENCE_IMAGES_PER_ARTIFACT:
        raise HTTPException(status_code=409, detail="Hiện vật đã đạt giới hạn ảnh tham chiếu.")
    content = read_image(image)
    try:
        embedding = encoder.encode(content)
    except InvalidImage as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    try:
        reference_id = store.add(
            artifact_id=artifact_id, image_name=image.filename or "reference-image",
            embedding=embedding.tobytes(), dimensions=int(embedding.size), model_id=encoder.model_id,
            limit=settings.MAX_REFERENCE_IMAGES_PER_ARTIFACT,
        )
    except ReferenceLimitReached as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    return {"id": reference_id, "artifactId": artifact_id, "status": "indexed"}


@app.delete("/api/v1/references/{artifact_id}", dependencies=[Depends(require_service_key)])
def delete_references(artifact_id: int) -> dict[str, int]:
    return {"artifactId": artifact_id, "deleted": store.delete_artifact(artifact_id)}


@app.post("/api/v1/recognitions", dependencies=[Depends(require_service_key)])
def recognize(
    image: UploadFile = File(...),
    top_k: int = Query(default=3, ge=1, le=10),
) -> dict[str, object]:
    content = read_image(image)
    try:
        encoder = get_encoder()
        query_embedding = encoder.encode(content)
    except InvalidImage as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    references = store.list_embeddings(encoder.model_id)
    if not references:
        raise HTTPException(status_code=503, detail="Chưa có ảnh tham chiếu hiện vật để nhận diện.")

    best_by_artifact: dict[int, float] = {}
    for reference in references:
        if int(reference["dimensions"]) != query_embedding.size:
            LOGGER.warning("Ignoring reference %s with incompatible embedding size", reference["id"])
            continue
        try:
            vector = np.frombuffer(reference["embedding"], dtype=np.float32)
            score = cosine_similarity(query_embedding, vector)
        except (ValueError, TypeError):
            LOGGER.warning("Ignoring invalid embedding reference %s", reference["id"])
            continue
        artifact_id = int(reference["artifact_id"])
        best_by_artifact[artifact_id] = max(score, best_by_artifact.get(artifact_id, -1.0))

    ranked = sorted(best_by_artifact.items(), key=lambda item: (-item[1], item[0]))
    if not ranked:
        raise HTTPException(status_code=503, detail="Chưa có ảnh tham chiếu phù hợp với bộ nhận diện hiện tại.")

    # top_k only limits the response; it must never suppress the runner-up used for ambiguity.
    margin = ranked[0][1] - ranked[1][1] if len(ranked) > 1 else 1.0
    candidates = ranked[:top_k]
    matched = candidates[0][1] >= settings.MIN_SIMILARITY and margin >= settings.MIN_MARGIN
    return {
        "matched": matched,
        "artifactId": candidates[0][0] if matched else None,
        "similarity": round(candidates[0][1], 4),
        "margin": round(margin, 4),
        "requiresConfirmation": not matched,
        "candidates": [
            {"artifactId": artifact_id, "similarity": round(score, 4)}
            for artifact_id, score in candidates
        ],
        "model": encoder.model_id,
    }
