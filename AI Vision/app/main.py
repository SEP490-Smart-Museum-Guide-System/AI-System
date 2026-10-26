from contextlib import asynccontextmanager
import logging

import numpy as np
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile

from app import settings
from app.store import ReferenceStore
from app.vision import InvalidImage, cosine_similarity, get_encoder

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)
store: ReferenceStore


@asynccontextmanager
async def lifespan(_: FastAPI):
    global store
    if not settings.SERVICE_API_KEY:
        raise RuntimeError("AI_SERVICE_API_KEY must be configured")
    store = ReferenceStore()
    store.initialize()
    get_encoder()  # Load model before accepting traffic; first boot downloads weights.
    yield


app = FastAPI(
    title="SMGS Artifact Vision Service",
    description="Matches artifact photos against reference images indexed by artifact ID.",
    version="0.2.0",
    lifespan=lifespan,
)


def require_service_key(x_service_key: str | None = Header(default=None)) -> None:
    if x_service_key is None or x_service_key != settings.SERVICE_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid service credentials")


async def read_image(upload: UploadFile) -> bytes:
    content = await upload.read(settings.MAX_IMAGE_BYTES + 1)
    if not content:
        raise HTTPException(status_code=422, detail="Image is empty")
    if len(content) > settings.MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds the upload size limit")
    return content


@app.get("/health")
def health() -> dict[str, object]:
    encoder = get_encoder()
    return {
        "status": "ok",
        "service": "artifact-vision",
        "model": encoder.model_id,
        "reference_images": store.count(encoder.model_id),
    }


@app.post("/api/v1/references", dependencies=[Depends(require_service_key)])
async def add_reference(
    artifact_id: int = Query(gt=0),
    image: UploadFile = File(...),
) -> dict[str, object]:
    encoder = get_encoder()
    if store.count_for_artifact(artifact_id, encoder.model_id) >= settings.MAX_REFERENCE_IMAGES_PER_ARTIFACT:
        raise HTTPException(status_code=409, detail="Reference image limit reached for artifact")
    content = await read_image(image)
    try:
        embedding = encoder.encode(content)
    except InvalidImage as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    reference_id = store.add(
        artifact_id=artifact_id,
        image_name=image.filename or "reference-image",
        embedding=embedding.tobytes(),
        dimensions=int(embedding.size),
        model_id=encoder.model_id,
    )
    return {"id": reference_id, "artifactId": artifact_id, "status": "indexed"}


@app.delete("/api/v1/references/{artifact_id}", dependencies=[Depends(require_service_key)])
def delete_references(artifact_id: int) -> dict[str, int]:
    return {"artifactId": artifact_id, "deleted": store.delete_artifact(artifact_id)}


@app.post("/api/v1/recognitions", dependencies=[Depends(require_service_key)])
async def recognize(
    image: UploadFile = File(...),
    top_k: int = Query(default=3, ge=1, le=10),
) -> dict[str, object]:
    content = await read_image(image)
    try:
        encoder = get_encoder()
        query_embedding = encoder.encode(content)
    except InvalidImage as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    references = store.list_embeddings(encoder.model_id)
    if not references:
        raise HTTPException(status_code=503, detail="No artifact reference images are indexed")

    best_by_artifact: dict[int, float] = {}
    for reference in references:
        if int(reference["dimensions"]) != query_embedding.size:
            LOGGER.warning("Ignoring reference %s with incompatible embedding size", reference["id"])
            continue
        vector = np.frombuffer(reference["embedding"], dtype=np.float32)
        score = cosine_similarity(query_embedding, vector)
        artifact_id = int(reference["artifact_id"])
        best_by_artifact[artifact_id] = max(score, best_by_artifact.get(artifact_id, -1.0))

    candidates = sorted(best_by_artifact.items(), key=lambda item: item[1], reverse=True)[:top_k]
    if not candidates:
        raise HTTPException(status_code=503, detail="No compatible references are indexed")

    margin = candidates[0][1] - candidates[1][1] if len(candidates) > 1 else 1.0
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
