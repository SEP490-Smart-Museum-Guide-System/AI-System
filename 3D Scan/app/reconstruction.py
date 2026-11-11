import logging
import json
import math
import os
import re
import subprocess
import struct
from pathlib import Path

import trimesh

from . import jobs
from .settings import COLMAP_COMMAND, COLMAP_CAMERA_MODEL, OPENMVS_BIN_DIR, OPENMVS_COMMANDS

logger = logging.getLogger(__name__)


class ReconstructionFailure(RuntimeError):
    """A controlled message that is safe to return to clients."""


def _tool(name: str) -> str:
    """Resolve OpenMVS executables from an optional binary directory or PATH."""
    directory = Path(OPENMVS_BIN_DIR) if OPENMVS_BIN_DIR else None
    candidate = directory / name if directory else None
    if candidate and candidate.is_file():
        return str(candidate)
    return OPENMVS_COMMANDS.get(name, name)


def openmvs_available() -> bool:
    """Check the complete CPU MVS pipeline, not only the COLMAP executable."""
    import shutil

    for name in OPENMVS_COMMANDS:
        command = _tool(name)
        if Path(command).is_file():
            continue
        if shutil.which(command) is None:
            return False
    return True


def _run(args: list[str], cwd: Path, label: str | None = None) -> None:
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                                timeout=6 * 60 * 60, check=False)
    except FileNotFoundError as exc:
        raise ReconstructionFailure(
            f"Thiếu công cụ dựng 3D '{args[0]}'. Cài COLMAP và OpenMVS CPU rồi cấu hình PATH/OPENMVS_BIN_DIR."
        ) from exc
    log_dir = cwd / "logs"
    log_dir.mkdir(exist_ok=True)
    log_name = re.sub(r"[^A-Za-z0-9_-]+", "_", label or Path(args[0]).name)
    (log_dir / f"{log_name}.log").write_text(
        f"COMMAND: {args!r}\nEXIT: {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        encoding="utf-8",
    )
    if result.returncode:
        step = label or Path(args[0]).name
        logger.error("3D command %s failed (%s): %s", step, result.returncode,
                     (result.stderr or result.stdout or "no output")[-3000:])
        raise ReconstructionFailure(f"Bước dựng 3D {step} thất bại (exit code {result.returncode}).")


def _validate_surface_glb(output: Path) -> None:
    """Read the generated GLB and reject point-cloud-only output."""
    if not output.is_file() or output.stat().st_size < 1024:
        raise ReconstructionFailure("GLB đầu ra rỗng hoặc không hợp lệ.")
    scene = trimesh.load(output, force="scene", process=False)
    geometries = list(scene.geometry.values())
    meshes = [item for item in geometries if isinstance(item, trimesh.Trimesh)]
    if not meshes or not any(len(mesh.vertices) > 0 and len(mesh.faces) > 0 for mesh in meshes):
        output.unlink(missing_ok=True)
        raise ReconstructionFailure("OpenMVS GLB không chứa bề mặt mesh; từ chối lưu point cloud như hiện vật 3D.")


def _embed_glb_textures(output: Path) -> None:
    """Embed sidecar bytes without changing OpenMVS UVs or unlit materials."""
    try:
        raw = output.read_bytes()
        magic, version, length = struct.unpack_from("<4sII", raw)
        if magic != b"glTF" or version != 2 or length != len(raw):
            raise ValueError("Invalid GLB header")
        chunks = {}; offset = 12
        while offset < len(raw):
            size, kind = struct.unpack_from("<II", raw, offset)
            chunks[kind] = raw[offset+8:offset+8+size]
            offset += size+8
        document = json.loads(chunks[0x4E4F534A])
        binary = bytearray(chunks.get(0x004E4942, b""))
        changed = False
        for item in document.get("images", []):
            uri = item.get("uri")
            if not uri:
                continue
            path = (output.parent / uri).resolve()
            if not path.is_relative_to(output.parent.resolve()):
                raise ValueError("Atlas must be inside output directory")
            data = path.read_bytes()
            mime = "image/png" if data.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg" if data.startswith(b"\xff\xd8") else None
            if mime is None:
                raise ValueError("Unsupported atlas image")
            binary.extend(b"\x00" * (-len(binary) % 4))
            views = document.setdefault("bufferViews", [])
            item["bufferView"] = len(views)
            item["mimeType"] = mime
            del item["uri"]
            views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(data)})
            binary.extend(data)
            changed = True
        if not changed:
            return
        binary.extend(b"\x00" * (-len(binary) % 4))
        document["buffers"][0]["byteLength"] = len(binary)
        encoded_json = json.dumps(document, separators=(",", ":")).encode("utf-8")
        encoded_json += b" " * (-len(encoded_json) % 4)
        body = (struct.pack("<II", len(encoded_json), 0x4E4F534A) + encoded_json
                + struct.pack("<II", len(binary), 0x004E4942) + binary)
        encoded = struct.pack("<4sII", b"glTF", 2, len(body)+12) + body
        temporary = output.with_name(f"{output.stem}.embedded.glb")
        temporary.write_bytes(encoded)
        temporary.replace(output)
    except Exception as exc:
        raise ReconstructionFailure("Không thể đóng gói texture vào GLB đầu ra.") from exc


def _ply_vertex_count(path: Path) -> int:
    """Read the vertex count from an ASCII or binary PLY header."""
    if not path.is_file() or path.stat().st_size < 32:
        return 0
    try:
        with path.open("rb") as source:
            for _ in range(128):
                line = source.readline(256)
                if not line:
                    return 0
                if line.startswith(b"element vertex "):
                    return max(0, int(line.split()[2]))
                if line.strip() == b"end_header":
                    return 0
    except (OSError, ValueError, IndexError):
        return 0
    return 0


def _registered_image_count(model_dir: Path) -> int:
    """Read COLMAP's registered-image count for one sparse submodel."""
    try:
        result = subprocess.run([COLMAP_COMMAND, "model_analyzer", "--path", str(model_dir)],
                                capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return 0
    match = re.search(r"Registered images:\s*(\d+)", result.stdout + result.stderr)
    return int(match.group(1)) if result.returncode == 0 and match else 0


def _validate_camera_calibration(model_dir: Path) -> None:
    """Reject a radial fit that folds the image before sending it to OpenMVS."""
    diagnostic = model_dir / "calibration-audit"
    diagnostic.mkdir(exist_ok=True)
    _run([COLMAP_COMMAND, "model_converter", "--input_path", str(model_dir),
          "--output_path", str(diagnostic), "--output_type", "TXT"], model_dir,
         "COLMAP calibration export")
    for line in (diagnostic / "cameras.txt").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        fields = line.split()
        if fields[1] != "SIMPLE_RADIAL":
            continue
        width, height = map(float, fields[2:4])
        focal, cx, cy, radial = map(float, fields[4:8])
        if not all(math.isfinite(v) for v in (focal, cx, cy, radial)) or focal <= 0:
            raise ReconstructionFailure("COLMAP tạo camera calibration không hợp lệ.")
        radius_squared = max(((x-cx)/focal)**2 + ((y-cy)/focal)**2
                             for x in (0, width) for y in (0, height))
        # r_distorted = r * (1 + k*r^2); a nonpositive derivative folds rays.
        if radial < 0 and 1 + 3 * radial * radius_squared <= 0:
            raise ReconstructionFailure(
                f"Camera COLMAP bị méo không hợp lệ (k={radial:.3f}); "
                "phép chiếu bị gập trong vùng ảnh. Không tiếp tục dựng mesh từ camera này."
            )


def process(job_id: str, job_dir: Path) -> None:
    images_dir = job_dir / "input"
    workspace = job_dir / "colmap"
    mvs_dir = job_dir / "openmvs"
    output_dir = job_dir / "output"

    try:
        if not openmvs_available():
            raise ReconstructionFailure(
                "Worker thiếu OpenMVS CPU (InterfaceCOLMAP, DensifyPointCloud, ReconstructMesh, "
                "RefineMesh, TextureMesh). Chưa thể tạo model surface GLB."
            )
        workspace.mkdir(parents=True, exist_ok=True)
        mvs_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        # COLMAP performs only CPU SfM here. Its CUDA-only PatchMatch dense stage is disabled.
        _run([COLMAP_COMMAND, "automatic_reconstructor", "--workspace_path", str(workspace),
              "--image_path", str(images_dir), "--use_gpu", "0", "--num_threads", "4",
              "--dense", "0", "--single_camera", "1", "--camera_model", COLMAP_CAMERA_MODEL], job_dir, "COLMAP SfM")
        jobs.update(job_id, progress=35)

        models = [path.parent for path in workspace.glob("sparse/*/images.bin")]
        if not models:
            raise ReconstructionFailure("COLMAP không tạo được sparse camera model.")
        model_counts = [(model, _registered_image_count(model)) for model in models]
        sparse_model, registered_images = max(model_counts, key=lambda item: item[1])
        input_image_count = sum(1 for path in images_dir.iterdir() if path.is_file())
        required_registered = max(5, math.ceil(input_image_count * 0.8))
        logger.info("COLMAP sparse models for job %s: %s; selected %s with %s/%s registered images",
                    job_id, len(model_counts), sparse_model.name, registered_images, input_image_count)
        if registered_images < required_registered:
            raise ReconstructionFailure(
                f"COLMAP chỉ đăng ký {registered_images}/{input_image_count} ảnh trong mô hình tốt nhất; "
                f"cần ít nhất {required_registered} ảnh chồng lấp để dựng 3D đáng tin cậy. "
                "Hãy chụp bổ sung các góc có nhiều chi tiết chung giữa ảnh liền kề."
            )
        _validate_camera_calibration(sparse_model)
        undistorted = workspace / "undistorted"
        _run([COLMAP_COMMAND, "image_undistorter", "--image_path", str(images_dir),
              "--input_path", str(sparse_model), "--output_path", str(undistorted),
              "--output_type", "COLMAP", "--max_image_size", "2000", "--blank_pixels", "1"], job_dir,
             "COLMAP image undistortion")
        jobs.update(job_id, progress=45)

        scene = mvs_dir / "scene.mvs"
        _run([_tool("InterfaceCOLMAP"), "-i", str(undistorted), "-o", str(scene),
              "--image-folder", str(undistorted / "images")], mvs_dir, "OpenMVS COLMAP import")
        _run([_tool("DensifyPointCloud"), str(scene), "--fusion-mode", "-2",
              "--tower-mode", "0", "--max-threads", "4"], mvs_dir, "OpenMVS CPU SGM densification")
        jobs.update(job_id, progress=70)

        dense_scene = mvs_dir / "scene_dense.mvs"
        dense_cloud = mvs_dir / "scene_dense.ply"
        dense_points = _ply_vertex_count(dense_cloud)
        reconstruction_dir = mvs_dir
        if dense_points == 0:
            # SGM can finish successfully while rejecting every depth during fusion.
            # Run CPU PatchMatch in a clean scene directory so its depth-map cache
            # cannot reuse files produced by the SGM attempt.
            logger.warning("OpenMVS SGM produced no dense points for job %s; retrying CPU PatchMatch", job_id)
            reconstruction_dir = mvs_dir / "patchmatch"
            reconstruction_dir.mkdir(parents=True, exist_ok=True)
            patchmatch_scene = reconstruction_dir / "scene.mvs"
            _run([_tool("InterfaceCOLMAP"), "-i", str(undistorted), "-o", str(patchmatch_scene),
                  "--image-folder", str(undistorted / "images")], reconstruction_dir,
                 "OpenMVS COLMAP re-import for CPU PatchMatch")
            _run([_tool("DensifyPointCloud"), str(patchmatch_scene), "--fusion-mode", "0",
                  "--resolution-level", "1", "--tower-mode", "0", "--max-threads", "4"], reconstruction_dir,
                 "OpenMVS CPU PatchMatch fallback")
            dense_scene = reconstruction_dir / "scene_dense.mvs"
            dense_cloud = reconstruction_dir / "scene_dense.ply"
            dense_points = _ply_vertex_count(dense_cloud)
        if dense_points == 0:
            raise ReconstructionFailure(
                "OpenMVS không tạo được dense point cloud (SGM và CPU PatchMatch đều không giữ được điểm). "
                "Không xuất GLB từ sparse points vì sẽ tạo bề mặt giả hoặc thủng."
            )
        logger.info("OpenMVS dense point cloud contains %s points for job %s", dense_points, job_id)

        _run([_tool("ReconstructMesh"), str(dense_scene), "-p", str(dense_cloud),
              "--close-holes", "0", "--max-threads", "4"], reconstruction_dir, "OpenMVS mesh reconstruction")
        mesh = reconstruction_dir / "scene_dense_mesh.ply"
        _run([_tool("RefineMesh"), str(dense_scene), "-m", str(mesh),
              "--close-holes", "0", "--decimate", "1", "--max-threads", "4"], reconstruction_dir, "OpenMVS mesh refinement")
        refined_mesh = reconstruction_dir / "scene_dense_refine.ply"
        _run([_tool("TextureMesh"), str(dense_scene), "-m", str(refined_mesh),
              "-o", str(output_dir / "model.glb"), "--export-type", "glb",
              "--resolution-level", "0", "--min-resolution", "640", "--max-texture-size", "4096",
              "--virtual-face-images", "3", "--cost-smoothness-ratio", "0.5",
              "--global-seam-leveling", "0", "--local-seam-leveling", "0",
              "--max-threads", "4"], reconstruction_dir, "OpenMVS texture mapping")
        jobs.update(job_id, progress=90)

        model_path = output_dir / "model.glb"
        _embed_glb_textures(model_path)
        _validate_surface_glb(model_path)
        jobs.update(job_id, status="REVIEW_REQUIRED", progress=100,
                    model_path=str(model_path.resolve()), model_type="mesh")
    except subprocess.TimeoutExpired:
        jobs.update(job_id, status="FAILED", model_path="", model_type="", error="Pipeline dựng 3D vượt quá thời gian xử lý tối đa 6 giờ.")
    except Exception as exc:
        logger.exception("3D reconstruction failed for job %s", job_id)
        safe_message = str(exc) if isinstance(exc, ReconstructionFailure) else "Không thể tạo mesh GLB. Kiểm tra log worker."
        jobs.update(job_id, status="FAILED", model_path="", model_type="", error=safe_message[:300])
