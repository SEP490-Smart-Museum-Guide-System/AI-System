"""Offline LR3D-CULT2 camera audit; inferred calibration is NOT original metadata.

The reference OBJ is used only to validate/infer calibration, never as reconstructed
geometry. Output is an explicitly labeled benchmark prior, not a mobile scan API.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
import trimesh
from trimesh.transformations import quaternion_from_matrix


def rotation(position, target):
    forward = target-position
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, [0., 1., 0.])
    right /= np.linalg.norm(right)
    down = np.cross(forward, right)
    return np.array([right, down, forward])


def run(source, output):
    output.mkdir(parents=True, exist_ok=True)
    metadata = json.loads((source/'metadata.json').read_text())
    center = np.array([metadata['object_center_world'][axis] for axis in ('x','y','z')])
    frames = {(int(f['camera'].split('CAM')[-1]), f['frame']): f
              for f in metadata['frames']}
    paths = sorted((source/'images').glob('*.png'))
    mesh = trimesh.load(source/'metal_cups_1.obj', force='mesh', process=False)
    vertices = np.asarray(mesh.vertices)
    samples = []
    for path in paths:
        orbit = int(path.name.split('CAM')[1][0])
        frame = int(path.stem.split('.')[-1])
        if frame not in (1, 12, 23, 34, 46, 57, 68, 79, 90):
            continue
        a = np.array(Image.open(path).convert('RGB')).astype(float)
        fg = np.max(np.abs(a-a[0, 0]), axis=2) > 18
        y, x = np.where(fg)
        samples.append((path, orbit, frame, fg, np.array([x.min(), x.max(), y.min(), y.max()])))
    trials = []
    fitting = [s for s in samples if s[2] in (1, 23, 46, 68, 90)]
    for offset in (-1, 0):
        projected = []
        for path, orbit, frame, fg, box in fitting:
            f = frames[orbit, frame+offset]
            position = np.array(list(f['position_world'].values()))
            R = rotation(position, center)
            xyz = (vertices-position) @ R.T
            uv = xyz[:, :2]/xyz[:, 2:]
            projected.append((uv[:, 0].min(), uv[:, 0].max(), uv[:, 1].min(), uv[:, 1].max()))
        projected = np.array(projected)
        observed = np.array([s[-1] for s in fitting])
        fx, cx = np.linalg.lstsq(np.column_stack([projected[:, :2].reshape(-1), np.ones(2*len(fitting))]), observed[:, :2].reshape(-1), rcond=None)[0]
        fy, cy = np.linalg.lstsq(np.column_stack([projected[:, 2:].reshape(-1), np.ones(2*len(fitting))]), observed[:, 2:].reshape(-1), rcond=None)[0]
        error = np.sqrt(np.mean((projected*np.array([fx, fx, fy, fy])+np.array([cx,cx,cy,cy])-observed)**2))
        trials.append(dict(frame_offset=offset, fx=float(fx), fy=float(fy), cx=float(cx), cy=float(cy), bbox_rmse_px=float(error)))
    best = min(trials, key=lambda t: t['bbox_rmse_px'])
    ious = []
    for path, orbit, frame, fg, box in samples:
        position = np.array(list(frames[orbit, frame+best['frame_offset']]['position_world'].values()))
        xyz = (vertices-position) @ rotation(position, center).T
        uv = xyz[:, :2]/xyz[:, 2:]*[best['fx'],best['fy']]+[best['cx'],best['cy']]
        mask = Image.new('1', (fg.shape[1],fg.shape[0]))
        draw = ImageDraw.Draw(mask)
        for face in mesh.faces:
            draw.polygon([tuple(v) for v in uv[face]], fill=1)
        rendered = np.array(mask, dtype=bool)
        iou = float(np.logical_and(fg,rendered).sum()/np.logical_or(fg,rendered).sum())
        ious.append(dict(image=path.name,silhouette_iou=iou,held_out=frame not in (1,23,46,68,90)))
        Image.fromarray(np.uint8(np.stack([fg*255, rendered*255, np.zeros_like(fg)],axis=-1))).save(output/(path.stem+'-silhouette.png'))
    report = dict(original_metadata_fields=list(metadata), original_has_rotation=False,
                  original_has_intrinsics=False, metadata_frames=len(frames), image_count=len(paths),
                  reference_only_for_calibration=True, assumptions=['camera looks at object_center_world','Y-up, zero roll','perspective camera'],
                  trials=trials, selected=best, silhouettes=ious)
    (output/'camera-audit.json').write_text(json.dumps(report,indent=2))
    # Do not silently export an unverified camera reconstruction.
    if best['bbox_rmse_px'] > 3 or min(x['silhouette_iou'] for x in ious) < .9:
        print(json.dumps(report,indent=2))
        raise SystemExit('Inferred cameras do not pass the reference silhouette check; no model exported')
    model = output/'known-cameras'; model.mkdir(exist_ok=True)
    width,height = Image.open(paths[0]).size
    (model/'cameras.txt').write_text(f"1 PINHOLE {width} {height} {best['fx']} {best['fy']} {best['cx']} {best['cy']}\n")
    rows=[]; poses={}
    for i,path in enumerate(paths,1):
        orbit=int(path.name.split('CAM')[1][0]); frame=int(path.stem.split('.')[-1])
        C=np.array(list(frames[orbit,frame+best['frame_offset']]['position_world'].values()))
        R=rotation(C,center); t=-R@C
        matrix=np.eye(4); matrix[:3,:3]=R; q=quaternion_from_matrix(matrix)
        rows.append(f"{i} {' '.join(map(str,q))} {' '.join(map(str,t))} 1 {path.name}\n\n")
        poses[path.name]=dict(imageId=i,qvec=q.tolist(),tvec=t.tolist(),width=width,height=height,**{k:best[k] for k in ('fx','fy','cx','cy')})
    (model/'images.txt').write_text(''.join(rows)); (model/'points3D.txt').write_text('')
    (output/'camera-poses.json').write_text(json.dumps(poses))
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('source',type=Path); parser.add_argument('output',type=Path)
    args=parser.parse_args(); run(args.source,args.output)
