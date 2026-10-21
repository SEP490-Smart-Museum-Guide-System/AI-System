import logging
import subprocess
from pathlib import Path

import trimesh

from . import jobs
from .settings import COLMAP_COMMAND

logger = logging.getLogger(__name__)


def _run(args: list[str], cwd: Path) -> None:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=6 * 60 * 60)
    if result.returncode:
        logger.error("COLMAP command %s failed (%s): %s", args[1], result.returncode,
                     (result.stderr or result.stdout or "no output")[-3000:])
        raise RuntimeError(f"COLMAP {args[1]} thất bại (exit code {result.returncode}).")


def process(job_id: str, job_dir: Path) -> None:
    jobs.update(job_id, status="PROCESSING", progress=5)
    images_dir = job_dir / "input"
    workspace = job_dir / "colmap"
    workspace.mkdir(parents=True, exist_ok=True)

    try:
        _run([COLMAP_COMMAND, "automatic_reconstructor", "--workspace_path", str(workspace),
              "--image_path", str(images_dir)], job_dir)
        jobs.update(job_id, progress=80)

        mesh_candidates = list(workspace.glob("dense/**/meshed-poisson.ply"))
        if not mesh_candidates:
            mesh_candidates = list(workspace.glob("dense/**/meshed-delaunay.ply"))
        if not mesh_candidates:
            raise RuntimeError("COLMAP hoàn tất nhưng không tạo được mesh Poisson/Delaunay.")

        mesh_path = mesh_candidates[0]
        textured_prefix = job_dir / "output" / "textured"
        textured_prefix.parent.mkdir(parents=True, exist_ok=True)
        try:
            _run([COLMAP_COMMAND, "mesh_texturer", "--workspace_path", str(mesh_path.parent),
                  "--input_path", str(mesh_path), "--output_path", str(textured_prefix)], job_dir)
            textured_outputs = list(textured_prefix.parent.rglob("*.obj"))
            if textured_outputs:
                mesh_path = textured_outputs[0]
        except RuntimeError:
            # Some COLMAP builds omit texture-mapping dependencies; retain the geometric mesh.
            pass

        mesh = trimesh.load(mesh_path, force="mesh", process=False)
        if mesh.is_empty or len(mesh.vertices) == 0 or len(mesh.faces) == 0:
            raise RuntimeError("Mesh đầu ra rỗng hoặc không hợp lệ.")
        output = job_dir / "output"
        output.mkdir(exist_ok=True)
        model_path = output / "model.glb"
        mesh.export(model_path, file_type="glb")
        if not model_path.is_file() or model_path.stat().st_size < 1024:
            raise RuntimeError("Không tạo được GLB hợp lệ.")
        jobs.update(job_id, status="REVIEW_REQUIRED", progress=100,
                    model_path=str(model_path.resolve()))
    except FileNotFoundError as exc:
        logger.exception("COLMAP executable could not be started for job %s", job_id)
        jobs.update(job_id, status="FAILED", error="Không chạy được COLMAP. Kiểm tra cấu hình worker.")
    except subprocess.TimeoutExpired:
        jobs.update(job_id, status="FAILED", error="COLMAP vượt quá thời gian xử lý tối đa 6 giờ.")
    except Exception as exc:
        logger.exception("3D reconstruction failed for job %s", job_id)
        safe_message = str(exc) if isinstance(exc, RuntimeError) else "Không thể tạo GLB. Kiểm tra log worker."
        jobs.update(job_id, status="FAILED", error=safe_message[:300])

