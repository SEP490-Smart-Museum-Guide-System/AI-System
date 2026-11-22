import json
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np
from trimesh.transformations import quaternion_matrix
from app.orientation import align_up_quaternion, camera_up, normalize_capture_orientation


class OrientationTests(unittest.TestCase):
    def cameras(self, path, quaternions):
        data = struct.pack('<Q', len(quaternions))
        for i, q in enumerate(quaternions):
            data += struct.pack('<idddddddi', i+1, *q, 0., 0., 0., 1) + f'{i}.jpg'.encode() + b'\0' + struct.pack('<Q', 0)
        path.write_bytes(data)

    def test_proper_rotation_maps_up_without_mirroring(self):
        for up in ([0, 1, 0], [0, -1, 0], [0.2, -.9, .3]):
            up = np.array(up); up = up/np.linalg.norm(up)
            q = align_up_quaternion(up)
            matrix = quaternion_matrix(np.r_[q[3], q[:3]])[:3, :3]
            np.testing.assert_allclose(matrix @ up, [0, 1, 0], atol=1e-7)
            self.assertAlmostEqual(np.linalg.det(matrix), 1)

    def test_glb_keeps_binary_textures_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); cameras = root/'images.bin'; model = root/'model.glb'
            self.cameras(cameras, [[1., 0, 0, 0]]*5)
            document = {'asset': {'generator': 'OpenMVS', 'version': '2.0'}, 'nodes': [{'mesh': 0}], 'scenes': [{'nodes': [0]}]}
            body = json.dumps(document).encode(); body += b' ' * (-len(body)%4)
            binary = struct.pack('<II', 16, 0x004e4942) + bytes(range(16))
            chunks = struct.pack('<II', len(body), 0x4e4f534a) + body + binary
            model.write_bytes(struct.pack('<4sII', b'glTF', 2, 12+len(chunks)) + chunks)
            report = normalize_capture_orientation(model, cameras)
            raw = model.read_bytes(); length, = struct.unpack_from('<I', raw, 12)
            self.assertEqual(raw[20+length:], binary)
            self.assertEqual(report['angleDegrees'], 180)
            self.assertTrue(normalize_capture_orientation(model, cameras)['alreadyApplied'])
            self.assertEqual(model.read_bytes(), raw)

    def test_bad_or_disagreeing_cameras_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'images.bin'
            self.cameras(path, [[1., 0, 0, 0]]*3 + [[0., 1, 0, 0]]*3)
            with self.assertRaisesRegex(ValueError, 'disagree'): camera_up(path)
            path.write_bytes(path.read_bytes()[:-1])
            with self.assertRaisesRegex(ValueError, 'Truncated'): camera_up(path)


if __name__ == '__main__': unittest.main()
