import logging
import json
import math
import os
import re
import subprocess
import struct
import time
from pathlib import Path

import trimesh

from . import jobs
from .orientation import normalize_capture_orientation
from .performance import ordered_pairs, settings as performance_settings
from .settings import COLMAP_COMMAND, COLMAP_CAMERA_MODEL, OPENMVS_BIN_DIR, OPENMVS_COMMANDS

logger = logging.getLogger(__name__)
COMMAND_TIMEOUT_SECONDS = 6 * 60 * 60
COMMAND_HEARTBEAT_SECONDS = 20


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
    step = label or Path(args[0]).name
    log_dir = cwd / "logs"
    log_dir.mkdir(exist_ok=True)
    log_name = re.sub(r"[^A-Za-z0-9_-]+", "_", step)
    log_path = log_dir / f"{log_name}.log"
    logger.info("Starting: %s; log=%s", step, log_path)
    # Native commands can run for minutes. Stream directly to disk so logs are
    # visible before completion and large output does not accumulate in RAM.
    with log_path.open('w', encoding='utf-8') as output:
        output.write(f"COMMAND: {args!r}\nSTATUS: RUNNING\nOUTPUT:\n")
        output.flush()
        try:
            child = subprocess.Popen(args, cwd=cwd, stdout=output, stderr=subprocess.STDOUT)
        except FileNotFoundError as exc:
            output.write('STATUS: TOOL_MISSING\n')
            raise ReconstructionFailure(
                f"Thiếu công cụ dựng 3D '{args[0]}'. Cài COLMAP và OpenMVS CPU rồi cấu hình PATH/OPENMVS_BIN_DIR."
            ) from exc
        started = time.monotonic()
        try:
            while True:
                remaining = COMMAND_TIMEOUT_SECONDS - (time.monotonic() - started)
                if remaining <= 0:
                    child.kill()
                    child.wait()
                    output.write('\nSTATUS: TIMEOUT\n')
                    raise ReconstructionFailure(f"Bước dựng 3D {step} vượt giới hạn thời gian.")
                try:
                    child.wait(timeout=min(COMMAND_HEARTBEAT_SECONDS, remaining))
                    break
                except subprocess.TimeoutExpired:
                    logger.info("Still running: %s; elapsed=%ds; logBytes=%d", step,
                                time.monotonic() - started, log_path.stat().st_size)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
        output.write(f'\nEXIT: {child.returncode}\nELAPSED_SECONDS: {time.monotonic() - started:.3f}\n')
    if child.returncode:
        with log_path.open('rb') as output:
            output.seek(max(0, log_path.stat().st_size - 3000))
            tail = output.read().decode('utf-8', errors='replace')
        logger.error("3D command %s failed (%s): %s", step, child.returncode, tail)
        raise ReconstructionFailure(f"Bước dựng 3D {step} thất bại (exit code {child.returncode}).")
    logger.info("Completed: %s; elapsed=%ds", step, time.monotonic() - started)


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


def _ordered_sfm(images_dir: Path, workspace: Path, job_dir: Path, audit: dict) -> list[Path]:
    """Bound matching work for explicitly ordered photos; reuse features on fallback."""
    database = workspace / 'database.db'
    names = sorted(p.name for p in images_dir.iterdir() if p.is_file())
    pairs = ordered_pairs(names)
    pair_file = workspace / 'ordered-pairs.txt'
    pair_file.write_text(''.join(f'{a} {b}\n' for a, b in pairs), encoding='utf8')
    audit.update(matching='ordered', candidate_pairs=len(pairs),
                 exhaustive_pairs=len(names) * (len(names)-1) // 2, exhaustive_fallback=False)
    _run([COLMAP_COMMAND, 'feature_extractor', '--database_path', str(database),
          '--image_path', str(images_dir), '--ImageReader.single_camera', '1',
          '--ImageReader.camera_model', COLMAP_CAMERA_MODEL,
          '--SiftExtraction.use_gpu', '0', '--SiftExtraction.num_threads', '4'], job_dir, 'COLMAP CPU features')

    def map_into(name):
        output = workspace / name
        output.mkdir()
        _run([COLMAP_COMMAND, 'mapper', '--database_path', str(database),
              '--image_path', str(images_dir), '--output_path', str(output),
              '--Mapper.num_threads', '4'], job_dir, f'COLMAP {name} camera mapping')
        return [p.parent for p in output.glob('*/images.bin')]

    try:
        _run([COLMAP_COMMAND, 'matches_importer', '--database_path', str(database),
              '--match_list_path', str(pair_file), '--match_type', 'pairs',
              '--SiftMatching.use_gpu', '0', '--SiftMatching.num_threads', '4'], job_dir, 'COLMAP ordered matches')
        models = map_into('ordered-sparse')
        if max((_registered_image_count(p) for p in models), default=0) >= max(5, math.ceil(.8 * len(names))):
            return models
        audit['fallback_reason'] = 'insufficient_registered_images'
    except ReconstructionFailure:
        audit['fallback_reason'] = 'ordered_matching_or_mapping_failed'
    # Never accept a poorly connected reconstruction simply to finish faster.
    # Exhaustive matching keeps the already extracted features and valid matches.
    audit['exhaustive_fallback'] = True
    logger.warning('Ordered matching insufficient; retrying exhaustive matching')
    _run([COLMAP_COMMAND, 'exhaustive_matcher', '--database_path', str(database),
          '--SiftMatching.use_gpu', '0', '--SiftMatching.num_threads', '4'], job_dir, 'COLMAP exhaustive fallback matches')
    return map_into('fallback-sparse')


def process(job_id: str, job_dir: Path, *, on_update=None, sparse_model=None,
            dense_method="sgm", resolution_level=1, quality=None, capture_order='unordered') -> None:
    # Local CLI supplies a JSON status writer; the API continues using PostgreSQL.
    update = on_update if on_update is not None else jobs.update
    images_dir = job_dir / "input"
    workspace = job_dir / "colmap"
    mvs_dir = job_dir / "openmvs"
    output_dir = job_dir / "output"
    audit = {}

    try:
        options = performance_settings(quality if quality is not None else 'detailed', capture_order)
        # Preserve direct callers' legacy resolution setting unless a preset was requested.
        if quality is not None:
            resolution_level = options['resolution_level']
        audit.update(options, resolution_level=resolution_level)
        if not openmvs_available():
            raise ReconstructionFailure(
                "Worker thiếu OpenMVS CPU (InterfaceCOLMAP, DensifyPointCloud, ReconstructMesh, "
                "RefineMesh, TextureMesh). Chưa thể tạo model surface GLB."
            )
        workspace.mkdir(parents=True, exist_ok=True)
        mvs_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        # COLMAP performs only CPU SfM here. Its CUDA-only PatchMatch dense stage is disabled.
        if sparse_model is None:
            update(job_id, progress=10)
            if capture_order == 'ordered':
                models = _ordered_sfm(images_dir, workspace, job_dir, audit)
            else:
                audit['matching'] = 'automatic'
                _run([COLMAP_COMMAND, "automatic_reconstructor", "--workspace_path", str(workspace),
                      "--image_path", str(images_dir), "--use_gpu", "0", "--num_threads", "4",
                      "--dense", "0", "--single_camera", "1", "--camera_model", COLMAP_CAMERA_MODEL], job_dir, "COLMAP SfM")
                models = [path.parent for path in workspace.glob("sparse/*/images.bin")]
        else:
            audit['matching'] = 'audited_camera_priors'
            models = [Path(sparse_model)]
        update(job_id, progress=35)
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
        update(job_id, progress=45)

        scene = mvs_dir / "scene.mvs"
        _run([_tool("InterfaceCOLMAP"), "-i", str(undistorted), "-o", str(scene),
              "--image-folder", str(undistorted / "images")], mvs_dir, "OpenMVS COLMAP import")
        if dense_method not in {"sgm", "patchmatch"} or resolution_level not in {0, 1, 2}:
            raise ReconstructionFailure("Invalid local dense reconstruction options")
        dense_args = (["--resolution-level", str(resolution_level),
                       "--min-resolution", str(options['min_resolution'])] if dense_method == "patchmatch" else [])
        _run([_tool("DensifyPointCloud"), str(scene), "--fusion-mode", "0" if dense_method == "patchmatch" else "-2",
              *dense_args, "--tower-mode", "0", "--max-threads", "4"], mvs_dir,
             "OpenMVS CPU PatchMatch densification" if dense_method == "patchmatch" else "OpenMVS CPU SGM densification")
        update(job_id, progress=70)

        dense_scene = mvs_dir / "scene_dense.mvs"
        dense_cloud = mvs_dir / "scene_dense.ply"
        dense_points = _ply_vertex_count(dense_cloud)
        reconstruction_dir = mvs_dir
        if dense_points == 0 and dense_method == "sgm":
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
                  "--resolution-level", str(resolution_level), "--min-resolution", str(options['min_resolution']),
                  "--tower-mode", "0", "--max-threads", "4"], reconstruction_dir,
                 "OpenMVS CPU PatchMatch fallback")
            dense_scene = reconstruction_dir / "scene_dense.mvs"
            dense_cloud = reconstruction_dir / "scene_dense.ply"
            dense_points = _ply_vertex_count(dense_cloud)
        if dense_points == 0:
            raise ReconstructionFailure(
                "OpenMVS không tạo được dense point cloud với các phương án đã chạy. "
                "Không xuất GLB từ sparse points vì sẽ tạo bề mặt giả hoặc thủng."
            )
        logger.info("OpenMVS dense point cloud contains %s points for job %s", dense_points, job_id)

        _run([_tool("ReconstructMesh"), str(dense_scene), "-p", str(dense_cloud),
              "--close-holes", "0", "--max-threads", "4"], reconstruction_dir, "OpenMVS mesh reconstruction")
        mesh = reconstruction_dir / "scene_dense_mesh.ply"
        refined_mesh = mesh
        if options['refine']:
            _run([_tool("RefineMesh"), str(dense_scene), "-m", str(mesh),
                  "--close-holes", "0", "--decimate", "1", "--max-threads", "4"], reconstruction_dir, "OpenMVS mesh refinement")
            refined_mesh = reconstruction_dir / "scene_dense_refine.ply"
        _run([_tool("TextureMesh"), str(dense_scene), "-m", str(refined_mesh),
              "-o", str(output_dir / "model.glb"), "--export-type", "glb",
              "--resolution-level", "0", "--min-resolution", "640", "--max-texture-size", str(options['texture_size']),
              "--virtual-face-images", "3", "--cost-smoothness-ratio", "0.5",
              "--global-seam-leveling", "0", "--local-seam-leveling", "0",
              "--max-threads", "4"], reconstruction_dir, "OpenMVS texture mapping")
        update(job_id, progress=90)

        model_path = output_dir / "model.glb"
        _embed_glb_textures(model_path)
        try:
            orientation = normalize_capture_orientation(model_path, undistorted / 'sparse' / 'images.bin')
        except (ValueError, OSError) as error:
            orientation = {'applied': False, 'reason': str(error), 'requiresReview': True}
            logger.warning('Could not establish upright orientation for job %s: %s', job_id, error)
        (job_dir / 'orientation.json').write_text(json.dumps(orientation, indent=2), encoding='utf8')
        _validate_surface_glb(model_path)
        update(job_id, status="REVIEW_REQUIRED", progress=100,
                    model_path=str(model_path.resolve()), model_type="mesh")
    except subprocess.TimeoutExpired:
        update(job_id, status="FAILED", model_path="", model_type="", error="Một bước dựng 3D vượt thời gian tối đa 6 giờ.")
    except Exception as exc:
        logger.exception("3D reconstruction failed for job %s", job_id)
        safe_message = str(exc) if isinstance(exc, ReconstructionFailure) else "Không thể tạo mesh GLB. Kiểm tra log worker."
        update(job_id, status="FAILED", model_path="", model_type="", error=safe_message[:300])
    finally:
        if audit:
            (job_dir / 'performance.json').write_text(json.dumps(audit, indent=2), encoding='utf8')
