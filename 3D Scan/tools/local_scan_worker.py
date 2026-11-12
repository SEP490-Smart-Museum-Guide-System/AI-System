"""Container-side local runner. Reuses the API pipeline without creating DB jobs."""
import argparse
import json
import logging
from pathlib import Path
import shutil
import sqlite3
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import reconstruction as pipeline
from app.validation import validate_image
from tools.audit_dataset_cameras import run as audit_cameras, image_key


def write_status(root, **changes):
    path = root / 'status.json'
    state = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    state.update(changes)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)
    print(f"[{state.get('status')}] {state.get('progress', 0)}% {state.get('error', '')}", flush=True)


def prepare_priors(root, report):
    """Match source-image features and triangulate with fixed, audited camera priors."""
    audit = root / 'camera-audit'
    database = root / 'features.db'
    images = root / 'input'
    K = report['selected']
    pipeline._run(['colmap', 'feature_extractor', '--database_path', str(database),
                   '--image_path', str(images), '--ImageReader.single_camera', '1',
                   '--ImageReader.camera_model', 'PINHOLE', '--ImageReader.camera_params',
                   ','.join(str(K[k]) for k in ('fx', 'fy', 'cx', 'cy')),
                   '--SiftExtraction.use_gpu', '0', '--SiftExtraction.num_threads', '4'],
                  root, 'COLMAP CPU features')
    with sqlite3.connect(database) as connection:
        records = connection.execute('SELECT name, image_id, camera_id FROM images').fetchall()
    ids = {name: (image_id, camera_id) for name, image_id, camera_id in records}
    priors = audit / 'known-cameras'
    lines = (priors / 'images.txt').read_text().splitlines()
    aligned = []
    for line in lines:
        if not line.strip():
            continue
        fields = line.split()
        fields[0], fields[8] = map(str, ids[fields[9]])
        aligned.append(' '.join(fields) + '\n\n')
    (priors / 'images.txt').write_text(''.join(aligned))
    camera_ids = {row[2] for row in records}
    if len(camera_ids) != 1:
        raise ValueError('Expected one camera calibration in feature database')
    fields = (priors / 'cameras.txt').read_text().split()
    fields[0] = str(next(iter(camera_ids)))
    (priors / 'cameras.txt').write_text(' '.join(fields) + '\n')
    # Include close views within and across the two LR3D camera rings.
    names = sorted(ids)
    frames = {name: image_key(Path(name))[1] for name in names}
    pairs = []
    for index, first in enumerate(names):
        for second in names[index + 1:]:
            difference = abs(frames[first] - frames[second])
            if min(difference, 90 - difference) <= 5:
                pairs.append(f'{first} {second}\n')
    pair_file = root / 'pairs.txt'
    pair_file.write_text(''.join(pairs))
    pipeline._run(['colmap', 'matches_importer', '--database_path', str(database),
                   '--match_list_path', str(pair_file), '--match_type', 'pairs',
                   '--SiftMatching.use_gpu', '0', '--SiftMatching.num_threads', '4'],
                  root, 'COLMAP CPU neighboring matches')
    sparse = root / 'fixed-sparse'
    sparse.mkdir()
    pipeline._run(['colmap', 'point_triangulator', '--database_path', str(database),
                   '--image_path', str(images), '--input_path', str(priors),
                   '--output_path', str(sparse), '--refine_intrinsics', '0',
                   '--Mapper.fix_existing_images', '1'], root, 'COLMAP fixed camera triangulation')
    with (sparse / 'points3D.bin').open('rb') as file:
        count = struct.unpack('<Q', file.read(8))[0]
    if count == 0:
        raise ValueError('No triangulated feature tracks; cannot reconstruct from these cameras')
    return sparse


def run(source, root, prepare_only=False):
    config = json.loads((root / 'config.json').read_text(encoding='utf-8'))
    mode = config['mode']
    write_status(root, status='PROCESSING', progress=0, mode=mode,
                 warning=('Benchmark: camera calibration uses the reference OBJ; output geometry '
                          'and atlas are reconstructed from images.' if mode == 'benchmark' else
                          'Cameras are estimated from photos. Missing or occluded surfaces may remain.'))
    try:
        images = root / 'input'
        images.mkdir()
        for index, relative in enumerate(config['images'], 1):
            path = (source / relative).resolve()
            if not path.is_relative_to(source.resolve()):
                raise ValueError('Image path escapes source folder')
            validate_image(path)
            name = path.name if mode == 'benchmark' else f'image_{index:05d}{path.suffix.lower()}'
            shutil.copyfile(path, images / name)
        sparse = None
        if mode == 'benchmark':
            report = audit_cameras(source, root / 'camera-audit')
            if not prepare_only:
                sparse = prepare_priors(root, report)
        if prepare_only:
            write_status(root, status='CHECKED', progress=0,
                         note='Input validation/calibration only. No model generated.')
            return 0
        def update_local(_id, **changes):
            if changes.get('status') == 'REVIEW_REQUIRED':
                changes.update(status='FINALIZING', progress=95)
            write_status(root, **changes)
        pipeline.process(root.name, root,
                         on_update=update_local,
                         sparse_model=sparse, dense_method='patchmatch', resolution_level=0)
        state = json.loads((root / 'status.json').read_text(encoding='utf-8'))
        if state['status'] != 'FINALIZING':
            return 1
        # Surface existence alone is not proof of an image-textured output.
        raw = (root / 'output' / 'model.glb').read_bytes()
        json_size = struct.unpack_from('<I', raw, 12)[0]
        document = json.loads(raw[20:20 + json_size])
        if not document.get('images') or not any(
            m.get('pbrMetallicRoughness', {}).get('baseColorTexture') is not None
            for m in document.get('materials', [])
        ):
            raise ValueError('Output has no image texture. Model is not accepted as textured reconstruction.')
        provenance = dict(mode=mode, image_count=len(config['images']),
                          reference_used_for_calibration=mode == 'benchmark',
                          reference_geometry_copied=False, synthetic_fill=False,
                          quality='Needs visual review; completeness is not guaranteed.')
        (root / 'provenance.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
        write_status(root, status='REVIEW_REQUIRED', progress=100)
        return 0
    except BaseException as error:
        if isinstance(error, KeyboardInterrupt):
            raise
        logging.exception('Local scan failed')
        write_status(root, status='FAILED', model_path='', error=str(error)[:800])
        return 1


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    sys.exit(run(args.source, args.output, args.prepare_only))
