import asyncio
import json
import re
import secrets
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError

from . import jobs
from .reconstruction import process
from .settings import DATA_DIR, MAX_IMAGE_BYTES, MAX_IMAGES, MAX_TOTAL_BYTES, SERVICE_API_KEY

_job_slots = asyncio.Semaphore(1)
_recovery_tasks: set[asyncio.Task] = set()


@asynccontextmanager
async def lifespan(_: FastAPI):
    jobs.initialize()
    for job_id in jobs.queued_ids():
        task = asyncio.create_task(_run_job(job_id, DATA_DIR / "scan-jobs" / job_id))
        _recovery_tasks.add(task)
        task.add_done_callback(_recovery_tasks.discard)
    yield


app = FastAPI(title="SMGS 3D Scan Service", version="0.1.0", lifespan=lifespan)


def _authorize(provided_key: str | None) -> None:
    if not SERVICE_API_KEY:
        raise HTTPException(status_code=503, detail="SCAN_SERVICE_API_KEY chưa được cấu hình.")
    if not provided_key or not secrets.compare_digest(provided_key, SERVICE_API_KEY):
        raise HTTPException(status_code=401, detail="Service key không hợp lệ.")


async def _run_job(job_id: str, job_dir: Path) -> None:
    async with _job_slots:
        await asyncio.to_thread(process, job_id, job_dir)


@app.get("/health")
def health():
    return {"status": "ok", "service": "3d-scan"}


@app.post("/api/v1/scans", status_code=202)
async def create_scan(background_tasks: BackgroundTasks,
                      artifact_id: int = Form(..., gt=0),
                      capture_metadata: str = Form("{}"),
                      images: list[UploadFile] = File(...),
                      x_service_key: str | None = Header(default=None)):
    _authorize(x_service_key)
    if not 10 <= len(images) <= MAX_IMAGES:
        raise HTTPException(422, detail=f"Cần từ 10 đến {MAX_IMAGES} ảnh cho một scan.")
    try:
        metadata = json.loads(capture_metadata)
        if not isinstance(metadata, dict):
            raise ValueError
    except ValueError:
        raise HTTPException(422, detail="capture_metadata phải là JSON object hợp lệ.")

    job_id = str(uuid.uuid4())
    job_dir = DATA_DIR / "scan-jobs" / job_id
    input_dir = job_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=False)
    total_bytes = 0
    try:
        for index, upload in enumerate(images, start=1):
            filename = Path(upload.filename or "").name
            if not re.search(r"\.(jpe?g|png)$", filename, re.IGNORECASE):
                raise HTTPException(415, detail="Chỉ chấp nhận ảnh JPG/JPEG hoặc PNG.")
            destination = input_dir / f"image_{index:03d}{Path(filename).suffix.lower()}"
            size = 0
            with destination.open("wb") as output:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    total_bytes += len(chunk)
                    if size > MAX_IMAGE_BYTES or total_bytes > MAX_TOTAL_BYTES:
                        raise HTTPException(413, detail="Bộ ảnh vượt giới hạn dung lượng cho phép.")
                    output.write(chunk)
            try:
                with Image.open(destination) as image:
                    image.verify()
            except (UnidentifiedImageError, OSError):
                raise HTTPException(415, detail=f"Tệp ảnh số {index} không hợp lệ.")
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    finally:
        for upload in images:
            await upload.close()

    jobs.create(job_id, artifact_id, len(images), metadata)
    background_tasks.add_task(_run_job, job_id, job_dir)
    return {"scanJobId": job_id, "artifactId": artifact_id, "status": "QUEUED"}


@app.get("/api/v1/scans/{job_id}")
def get_scan(job_id: str, x_service_key: str | None = Header(default=None)):
    _authorize(x_service_key)
    record = jobs.get(job_id)
    if not record:
        raise HTTPException(404, detail="Không tìm thấy scan job.")
    return {
        "scanJobId": record["id"], "artifactId": record["artifact_id"],
        "status": record["status"], "progress": record["progress"],
        "imageCount": record["image_count"],
        "modelUrl": f"/api/v1/scans/{record['id']}/model" if record["model_path"] else None,
        "error": record["error"], "createdAt": record["created_at"],
    }


@app.get("/api/v1/scans/{job_id}/model")
def get_model(job_id: str, x_service_key: str | None = Header(default=None)):
    _authorize(x_service_key)
    record = jobs.get(job_id)
    if not record or not record["model_path"]:
        raise HTTPException(404, detail="Model chưa sẵn sàng.")
    path = Path(record["model_path"]).resolve()
    allowed_root = (DATA_DIR / "scan-jobs" / job_id / "output").resolve()
    if allowed_root not in path.parents or not path.is_file():
        raise HTTPException(404, detail="Không tìm thấy model.")
    return FileResponse(path, media_type="model/gltf-binary", filename="model.glb")


@app.post("/api/v1/scans/{job_id}/approve")
def approve_scan(job_id: str, x_service_key: str | None = Header(default=None)):
    _authorize(x_service_key)
    record = jobs.approve(job_id)
    if not record:
        raise HTTPException(404, detail="Không tìm thấy scan job.")
    if record["status"] != "COMPLETED":
        raise HTTPException(409, detail="Chỉ duyệt được scan đang ở trạng thái REVIEW_REQUIRED.")
    return {"scanJobId": job_id, "artifactId": record["artifact_id"],
            "status": "COMPLETED", "modelUrl": f"/api/v1/scans/{job_id}/model"}

