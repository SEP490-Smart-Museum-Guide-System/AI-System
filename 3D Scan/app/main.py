import asyncio
import json
import logging
import re
import secrets
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
import psycopg

from . import jobs
from .reconstruction import openmvs_available, process
from .settings import COLMAP_COMMAND, DATA_DIR, MIN_IMAGES, MAX_IMAGE_BYTES, MAX_IMAGES, MAX_METADATA_BYTES, MAX_TOTAL_BYTES, SERVICE_API_KEY
from .validation import validate_image

_job_slots = asyncio.Semaphore(1)
_recovery_tasks: set[asyncio.Task] = set()
LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not SERVICE_API_KEY:
        raise RuntimeError("SCAN_SERVICE_API_KEY must be configured")
    await asyncio.to_thread(jobs.initialize)
    app.state.worker_ready = True
    for job_id in await asyncio.to_thread(jobs.queued_ids):
        task = asyncio.create_task(_run_job(job_id, DATA_DIR / "scan-jobs" / job_id))
        _recovery_tasks.add(task)
        task.add_done_callback(_recovery_tasks.discard)
    try:
        yield
    finally:
        app.state.worker_ready = False


app = FastAPI(title="SMGS 3D Scan Service", version="0.1.0", lifespan=lifespan)
app.state.worker_ready = False


@app.exception_handler(psycopg.Error)
async def database_unavailable(_, exc: Exception):
    LOGGER.exception("Scan database unavailable", exc_info=exc)
    return JSONResponse(status_code=503, content={"detail": "Kho dữ liệu scan hiện chưa sẵn sàng. Vui lòng thử lại."}, headers={"Retry-After": "3"})


def _authorize(provided_key: str | None) -> None:
    if not SERVICE_API_KEY:
        raise HTTPException(status_code=503, detail="SCAN_SERVICE_API_KEY chưa được cấu hình.")
    if not provided_key or not secrets.compare_digest(provided_key.encode(), SERVICE_API_KEY.encode()):
        raise HTTPException(status_code=401, detail="Service key không hợp lệ.")


@app.middleware("http")
async def authenticate_before_upload(request, call_next):
    if request.url.path.startswith('/api/'):
        try:
            _authorize(request.headers.get('x-service-key'))
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={'detail': exc.detail})
    return await call_next(request)


async def _run_job(job_id: str, job_dir: Path) -> None:
    async with _job_slots:
        try:
            if await asyncio.to_thread(jobs.claim, job_id):
                await asyncio.to_thread(process, job_id, job_dir)
        except Exception:
            LOGGER.exception("Scan worker failed for job %s", job_id)


@app.get("/health")
@app.get("/ready")
def health():
    available = shutil.which(COLMAP_COMMAND) is not None
    mvs_available = openmvs_available()
    database_ready = False
    if app.state.worker_ready:
        try:
            jobs.ping()
            database_ready = True
        except psycopg.Error:
            LOGGER.warning("Scan readiness database check failed", exc_info=True)
    ready = bool(SERVICE_API_KEY) and available and mvs_available and database_ready and app.state.worker_ready
    return JSONResponse(status_code=200 if ready else 503, content={
        "status": "ok" if ready else "unavailable", "service": "3d-scan",
        "colmap_available": available, "openmvs_cpu_available": mvs_available,
        "worker_ready": app.state.worker_ready,
        "database_ready": database_ready,
    })


@app.get("/live")
async def live():
    return {"status": "ok", "service": "3d-scan"}


@app.post("/api/v1/scans", status_code=202)
def create_scan(background_tasks: BackgroundTasks,
                      artifact_id: int = Form(..., gt=0),
                      capture_metadata: str = Form("{}"),
                      images: list[UploadFile] = File(...),
                      x_service_key: str | None = Header(default=None)):
    _authorize(x_service_key)
    if shutil.which(COLMAP_COMMAND) is None:
        raise HTTPException(503, detail="Worker chưa có COLMAP. Vui lòng kiểm tra cấu hình dịch vụ.")
    if not openmvs_available():
        raise HTTPException(503, detail="Worker chưa có OpenMVS CPU. Chưa thể tạo surface mesh GLB.")
    if not MIN_IMAGES <= len(images) <= MAX_IMAGES:
        raise HTTPException(422, detail=f"Cần ít nhất {MIN_IMAGES} ảnh của cùng một hiện vật (tối đa {MAX_IMAGES} ảnh).")
    if len(capture_metadata.encode('utf-8')) > MAX_METADATA_BYTES:
        raise HTTPException(413, detail="Thông tin bộ ảnh vượt giới hạn dung lượng cho phép.")
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
                while chunk := upload.file.read(1024 * 1024):
                    size += len(chunk)
                    total_bytes += len(chunk)
                    if size > MAX_IMAGE_BYTES or total_bytes > MAX_TOTAL_BYTES:
                        raise HTTPException(413, detail="Bộ ảnh vượt giới hạn dung lượng cho phép.")
                    output.write(chunk)
            try:
                validate_image(destination)
            except ValueError as exc:
                raise HTTPException(415, detail=f"Tệp ảnh số {index} không hợp lệ: {exc}") from exc
        # Persist before scheduling. A DB failure must not leave an orphaned upload directory.
        jobs.create(job_id, artifact_id, len(images), metadata)
    except Exception:
        root = (DATA_DIR / "scan-jobs").resolve()
        if job_dir.resolve().parent != root or job_dir.name != job_id:
            raise RuntimeError("Refusing cleanup outside the generated scan directory")
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    finally:
        for upload in images:
            upload.file.close()

    background_tasks.add_task(_run_job, job_id, job_dir)
    return {"scanJobId": job_id, "artifactId": artifact_id, "status": "QUEUED"}


@app.get("/api/v1/scans/{job_id}")
def get_scan(job_id: uuid.UUID, x_service_key: str | None = Header(default=None)):
    _authorize(x_service_key)
    job_id = str(job_id)
    record = jobs.get(job_id)
    if not record:
        raise HTTPException(404, detail="Không tìm thấy scan job.")
    return {
        "scanJobId": record["id"], "artifactId": record["artifact_id"],
        "status": record["status"], "progress": record["progress"],
        "imageCount": record["image_count"],
        "modelUrl": f"/api/v1/scans/{record['id']}/model" if record["model_path"] else None,
        "modelType": record.get("model_type"),
        "modelWarning": ("Bản xem trước là đám mây điểm thưa, chưa phải bề mặt mesh kín."
                         if record.get("model_type") == "sparse_point_cloud" else None),
        "error": record["error"], "createdAt": record["created_at"],
    }


@app.get("/api/v1/scans/{job_id}/model")
def get_model(job_id: uuid.UUID, x_service_key: str | None = Header(default=None)):
    _authorize(x_service_key)
    job_id = str(job_id)
    record = jobs.get(job_id)
    if not record or not record["model_path"]:
        raise HTTPException(404, detail="Model chưa sẵn sàng.")
    path = Path(record["model_path"]).resolve()
    allowed_root = (DATA_DIR / "scan-jobs" / job_id / "output").resolve()
    scan_root = (DATA_DIR / "scan-jobs").resolve()
    if scan_root not in allowed_root.parents or allowed_root not in path.parents or not path.is_file() or path.suffix.lower() != '.glb':
        raise HTTPException(404, detail="Không tìm thấy model.")
    return FileResponse(path, media_type="model/gltf-binary", filename="model.glb")


@app.post("/api/v1/scans/{job_id}/approve")
def approve_scan(job_id: uuid.UUID, x_service_key: str | None = Header(default=None)):
    _authorize(x_service_key)
    job_id = str(job_id)
    record = jobs.approve(job_id)
    if not record:
        raise HTTPException(404, detail="Không tìm thấy scan job.")
    if record["status"] != "COMPLETED":
        raise HTTPException(409, detail="Chỉ duyệt được scan đang ở trạng thái REVIEW_REQUIRED.")
    return {"scanJobId": job_id, "artifactId": record["artifact_id"],
            "status": "COMPLETED", "modelUrl": f"/api/v1/scans/{job_id}/model",
            "modelType": record.get("model_type")}

