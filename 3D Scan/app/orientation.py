"""Orient legacy OpenMVS GLBs from the capture's camera-up consensus.

COLMAP stores world-to-camera Hamilton quaternions; camera +Y points down.
Only a JSON parent transform is added. Geometry, UV and image bytes stay intact.
"""
import hashlib
import json
from pathlib import Path
import struct

import numpy as np
from trimesh.transformations import quaternion_matrix

MARKER = 'smgsCaptureOrientation'


def camera_up(images: Path) -> tuple[np.ndarray, float, int]:
    size = images.stat().st_size
    def read(stream, fmt):
        length = struct.calcsize(fmt)
        value = stream.read(length)
        if len(value) != length:
            raise ValueError('Truncated COLMAP camera file')
        return struct.unpack(fmt, value)
    ups = []
    with images.open('rb') as stream:
        count, = read(stream, '<Q')
        if not 5 <= count <= 10000:
            raise ValueError('Insufficient or invalid camera count')
        for _ in range(count):
            values = read(stream, '<idddddddi')
            quaternion = np.asarray(values[1:5], dtype=float)
            if not np.isfinite(quaternion).all() or np.linalg.norm(quaternion) < 1e-8:
                raise ValueError('Invalid camera rotation')
            ups.append(-quaternion_matrix(quaternion)[1, :3])
            for _ in range(4096):
                char = stream.read(1)
                if char == b'\0': break
                if not char: raise ValueError('Truncated camera name')
            else:
                raise ValueError('Camera name too long')
            points, = read(stream, '<Q')
            if stream.tell() + points * 24 > size:
                raise ValueError('Truncated image observations')
            stream.seek(points * 24, 1)
    mean = np.mean(ups, axis=0)
    coherence = float(np.linalg.norm(mean))
    if coherence < .6:
        raise ValueError('Camera up directions disagree; manual orientation required')
    return mean / coherence, coherence, len(ups)


def align_up_quaternion(up: np.ndarray) -> np.ndarray:
    up = np.asarray(up, dtype=float)
    up = up / np.linalg.norm(up)
    target = np.array([0., 1., 0.])
    dot = float(np.clip(up @ target, -1, 1))
    if dot < -1 + 1e-10:
        axis = np.cross(up, [1., 0., 0.])
        if np.linalg.norm(axis) < 1e-6: axis = np.cross(up, [0., 0., 1.])
        return np.r_[axis / np.linalg.norm(axis), 0.]
    quaternion = np.r_[np.cross(up, target), 1 + dot]
    return quaternion / np.linalg.norm(quaternion)  # glTF order: x,y,z,w


def normalize_capture_orientation(model: Path, images: Path) -> dict:
    raw = model.read_bytes()
    if len(raw) < 20 or struct.unpack_from('<4sII', raw) != (b'glTF', 2, len(raw)):
        raise ValueError('Invalid GLB header')
    length, kind = struct.unpack_from('<II', raw, 12)
    if kind != 0x4e4f534a or length % 4 or 20 + length > len(raw):
        raise ValueError('Invalid GLB JSON chunk')
    document = json.loads(raw[20:20+length])
    asset = document.setdefault('asset', {})
    if not isinstance(asset, dict):
        raise ValueError('Invalid GLB asset')
    extras = asset.setdefault('extras', {})
    if not isinstance(extras, dict):
        raise ValueError('Unsupported asset extras')
    if MARKER in extras:
        return {**extras[MARKER], 'alreadyApplied': True}
    if asset.get('generator') != 'OpenMVS':
        raise ValueError('Unknown exporter coordinate frame')
    nodes, scenes = document.get('nodes', []), document.get('scenes', [])
    if not scenes or not nodes:
        raise ValueError('GLB has no scene')
    for scene in scenes:
        for index in scene.get('nodes', []):
            if not isinstance(index, int) or not 0 <= index < len(nodes):
                raise ValueError('Invalid scene root')
            root = nodes[index]
            if any(key in root for key in ('matrix', 'rotation', 'translation', 'scale')):
                raise ValueError('Exporter already transforms scene roots; manual orientation required')
    up, coherence, count = camera_up(images)
    quaternion = align_up_quaternion(up)
    rotation = quaternion_matrix(np.r_[quaternion[3], quaternion[:3]])[:3, :3]
    if not np.allclose(rotation @ up, [0, 1, 0], atol=1e-7) or np.linalg.det(rotation) < .999999:
        raise ValueError('Invalid upright rotation')
    report = dict(version=1, applied=True, method='camera-up-consensus', cameras=count,
                  coherence=coherence, sourceUp=up.tolist(), rotation=quaternion.tolist(),
                  angleDegrees=float(np.degrees(np.arccos(np.clip(up[1], -1, 1)))),
                  originalSHA256=hashlib.sha256(raw).hexdigest(),
                  binarySHA256=hashlib.sha256(raw[20+length:]).hexdigest())
    for scene in scenes:
        index = len(nodes)
        nodes.append({'name': 'SMGS capture upright', 'rotation': quaternion.tolist(),
                      'children': list(scene.get('nodes', []))})
        scene['nodes'] = [index]
    extras[MARKER] = report
    encoded = json.dumps(document, ensure_ascii=False, separators=(',', ':')).encode('utf8')
    encoded += b' ' * (-len(encoded) % 4)
    # Preserve every non-JSON chunk byte-for-byte, including embedded textures.
    body = struct.pack('<II', len(encoded), kind) + encoded + raw[20+length:]
    updated = struct.pack('<4sII', b'glTF', 2, len(body)+12) + body
    temporary = model.with_name(model.name + '.upright.tmp')
    temporary.write_bytes(updated)
    temporary.replace(model)
    return {**report, 'outputSHA256': hashlib.sha256(updated).hexdigest()}
