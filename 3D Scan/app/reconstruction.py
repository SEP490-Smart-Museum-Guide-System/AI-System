import logging
import subprocess
from pathlib import Path

import trimesh

from . import jobs
from .settings import COLMAP_COMMAND

logger = logging.getLogger(__name__)


class ReconstructionFailure(RuntimeError):
    """A controlled message that is safe to return to clients."""


def _run(args: list[str], cwd: Path) -> None:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=6 * 60 * 60)
    if result.returncode:
        logger.error("COLMAP command %s failed (%s): %s", args[1], result.returncode,
                     (result.stderr or result.stdout or "no output")[-3000:])
        raise ReconstructionFailure(f"COLMAP {args[1]} thất bại (exit code {result.returncode}).")


def _export_sparse_glb(points_path: Path, output_path: Path) -> None:
    """Package COLMAP's sparse colored points as a GLB when CPU MVS made no surface mesh."""
    cloud = trimesh.load(points_path, process=False)
    if not isinstance(cloud, trimesh.points.PointCloud) or len(cloud.vertices) < 20:
        raise ReconstructionFailure("COLMAP không tạo đủ điểm sparse để xuất GLB xem trước.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cloud.export(output_path, file_type="glb")
    if not output_path.is_file() or output_path.stat().st_size < 1024:
        raise ReconstructionFailure("Không tạo được GLB point cloud hợp lệ.")


def process(job_id: str, job_dir: Path) -> None:
    images_dir = job_dir / "input"
    workspace = job_dir / "colmap"

    try:
        workspace.mkdir(parents=True, exist_ok=True)
        _run([COLMAP_COMMAND, "automatic_reconstructor", "--workspace_path", str(workspace),
              "--image_path", str(images_dir), "--use_gpu", "0", "--num_threads", "4"], job_dir)
        jobs.update(job_id, progress=80)

        mesh_candidates = list(workspace.glob("dense/**/meshed-poisson.ply"))
        if not mesh_candidates:
            mesh_candidates = list(workspace.glob("dense/**/meshed-delaunay.ply"))
        output = job_dir / "output"
        output.mkdir(exist_ok=True)
        model_path = output / "model.glb"
        if not mesh_candidates:
            sparse_candidates = list(workspace.glob("sparse/**/points3D.ply"))
            if not sparse_candidates:
                sparse_models = [path.parent for path in workspace.glob("sparse/**/points3D.bin")]
                if not sparse_models:
                    sparse_models = [path.parent for path in workspace.glob("sparse/**/points3D.txt")]
                if sparse_models:
                    sparse_ply = output / "sparse-points.ply"
                    _run([COLMAP_COMMAND, "model_converter", "--input_path", str(sparse_models[0]),
                          "--output_path", str(sparse_ply), "--output_type", "PLY"], job_dir)
                    if sparse_ply.is_file():
                        sparse_candidates.append(sparse_ply)
            if not sparse_candidates:
                raise ReconstructionFailure("COLMAP không tạo được dense mesh hoặc sparse point cloud.")
            _export_sparse_glb(sparse_candidates[0], model_path)
            jobs.update(job_id, status="REVIEW_REQUIRED", progress=100,
                        model_path=str(model_path.resolve()), model_type="sparse_point_cloud")
            return

        mesh_path = mesh_candidates[0]
        textured_prefix = job_dir / "output" / "textured"
        textured_prefix.parent.mkdir(parents=True, exist_ok=True)
        try:
            _run([COLMAP_COMMAND, "mesh_texturer", "--workspace_path", str(mesh_path.parent),
                  "--input_path", str(mesh_path), "--output_path", str(textured_prefix)], job_dir)
            textured_outputs = list(textured_prefix.parent.rglob("*.obj"))
            if textured_outputs:
                mesh_path = textured_outputs[0]
        except ReconstructionFailure:
            # Some COLMAP builds omit texture-mapping dependencies; retain the geometric mesh.
            pass

        mesh = trimesh.load(mesh_path, force="mesh", process=False)
        if mesh.is_empty or len(mesh.vertices) == 0 or len(mesh.faces) == 0:
            raise ReconstructionFailure("Mesh đầu ra rỗng hoặc không hợp lệ.")
        mesh.export(model_path, file_type="glb")
        if not model_path.is_file() or model_path.stat().st_size < 1024:
            raise ReconstructionFailure("Không tạo được GLB hợp lệ.")
        jobs.update(job_id, status="REVIEW_REQUIRED", progress=100,
                    model_path=str(model_path.resolve()), model_type="mesh")
    except FileNotFoundError as exc:
        logger.exception("COLMAP executable could not be started for job %s", job_id)
        jobs.update(job_id, status="FAILED", error="Không chạy được COLMAP. Kiểm tra cấu hình worker.")
    except subprocess.TimeoutExpired:
        jobs.update(job_id, status="FAILED", error="COLMAP vượt quá thời gian xử lý tối đa 6 giờ.")
    except Exception as exc:
        logger.exception("3D reconstruction failed for job %s", job_id)
        safe_message = str(exc) if isinstance(exc, ReconstructionFailure) else "Không thể tạo GLB. Kiểm tra log worker."
        jobs.update(job_id, status="FAILED", error=safe_message[:300])

