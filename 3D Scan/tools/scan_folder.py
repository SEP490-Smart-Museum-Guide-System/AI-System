"""One-command local folder -> existing CPU pipeline -> GLB. Host needs Python + Docker."""
import argparse
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname
from urllib.request import urlopen
import uuid

ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = {'.jpg', '.jpeg', '.png'}
VIEWER_ASSETS = {
    'viewer.js': ('dist/model-viewer.min.js', '283b0672384614b4847636c306fc93fe4b1fcadc76d668b4e47f0ca76bcf033b'),
    'model-viewer-LICENSE': ('LICENSE', 'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30'),
}


def setup_runtime(image, rebuild=False):
    if not shutil.which('docker'):
        raise ValueError('Install Docker Desktop (Linux containers) or Docker Engine first.')
    if subprocess.run(['docker', 'info'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        raise ValueError('Docker is not running. Start Docker and retry.')
    exists = subprocess.run(['docker', 'image', 'inspect', image], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if rebuild or not exists:
        print('Building CPU image; first setup needs Internet. No .env/database required.', flush=True)
        subprocess.run(['docker', 'build', '--platform', 'linux/amd64', '-t', image, str(ROOT)], check=True)
    cache = ROOT / 'state' / 'viewer-assets'
    cache.mkdir(parents=True, exist_ok=True)
    for name, (remote, expected) in VIEWER_ASSETS.items():
        destination = cache / name
        if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() == expected:
            continue
        print(f'Downloading pinned model-viewer 4.3.1: {name}', flush=True)
        with urlopen('https://cdn.jsdelivr.net/npm/@google/model-viewer@4.3.1/' + remote, timeout=90) as response:
            data = response.read(4 * 1024 * 1024)
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f'Checksum mismatch: {name}. Asset was not installed.')
        temporary = destination.with_suffix('.tmp')
        temporary.write_bytes(data)
        temporary.replace(destination)
    print('CPU image and standalone viewer ready.', flush=True)
    return cache


def folder_path(value):
    value = value.strip().strip('"')
    if value.lower().startswith('file:'):
        parsed = urlparse(value)
        if parsed.netloc not in {'', 'localhost'}:
            raise ValueError('Use a local folder path, not a remote file host')
        value = url2pathname(unquote(parsed.path))
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f'Folder does not exist: {path}')
    return path


def inspect_folder(source, requested='auto'):
    # Pointing at images/ also recognizes its parent LR3D dataset.
    if source.name.lower() == 'images' and (source.parent / 'metadata.json').is_file():
        source = source.parent
    image_root = source / 'images' if (source / 'images').is_dir() else source
    paths = sorted(p for p in image_root.rglob('*') if p.is_file() and p.suffix.lower() in EXTENSIONS)
    if any(not p.resolve().is_relative_to(source) for p in paths):
        raise ValueError('Image symlinks must remain inside the selected folder')
    if not 5 <= len(paths) <= 1000:
        raise ValueError(f'Found {len(paths)} images; local runner accepts 5..1000 images of ONE object')
    objects = list(source.glob('*.obj'))
    metadata_path = source / 'metadata.json'
    metadata = json.loads(metadata_path.read_text(encoding='utf-8')) if metadata_path.exists() else {}
    benchmark = (len(objects) == 1 and 'object_center_world' in metadata and 'frames' in metadata
                 and image_root != source
                 and all(p.parent == image_root and re.search(r'CAM\d+.*\.\d+\.png$', p.name) for p in paths))
    mode = ('benchmark' if benchmark else 'photos') if requested == 'auto' else requested
    if mode == 'benchmark' and not benchmark:
        raise ValueError('Benchmark mode requires LR3D metadata, one OBJ and images/*.png with camera/frame names')
    total = sum(path.stat().st_size for path in paths)
    return source, dict(mode=mode, images=[p.relative_to(source).as_posix() for p in paths],
                        total_bytes=total, input_folder=str(source), image_count=len(paths))


class PreviewHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', nargs='?', help='Folder of one object; quoted Windows paths supported')
    parser.add_argument('--mode', choices=['auto', 'photos', 'benchmark'], default='auto')
    parser.add_argument('--check', action='store_true', help='List input/mode only; do not start Docker or reconstruction')
    parser.add_argument('--prepare-only', action='store_true', help='Validate images and benchmark calibration; no reconstruction')
    parser.add_argument('--no-serve', action='store_true', help='Exit after worker, without local preview server')
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--image', default='smgs-ai-scan', help='Existing local CPU Docker image')
    parser.add_argument('--setup', action='store_true', help='Prepare Docker image and viewer only; no dataset required')
    parser.add_argument('--rebuild', action='store_true', help='Rebuild CPU image after pulling updates')
    args = parser.parse_args()
    if args.setup:
        setup_runtime(args.image, args.rebuild)
        return 0
    source, config = inspect_folder(folder_path(args.folder or input('Folder anh: ')), args.mode)
    print(f"Folder: {source}\nImages: {config['image_count']} ({config['total_bytes'] / 1048576:.1f} MiB)\nMode: {config['mode']}", flush=True)
    if config['mode'] == 'benchmark':
        print('BENCHMARK: reference OBJ is used for camera calibration only, NOT as output geometry.', flush=True)
    if args.check:
        return 0
    viewer_assets = setup_runtime(args.image, args.rebuild)
    job = datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8]
    output = ROOT / 'state' / 'local-scans' / job
    output.mkdir(parents=True)
    (output / 'config.json').write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'status.json').write_text(json.dumps({'status': 'QUEUED', 'progress': 0}), encoding='utf-8')
    shutil.copyfile(ROOT / 'tools' / 'local_scan_viewer.html', output / 'index.html')
    for asset in VIEWER_ASSETS:
        shutil.copyfile(viewer_assets / asset, output / asset)
    server = None
    if not args.no_serve:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), partial(PreviewHandler, directory=str(output)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print(f'VIEW: http://127.0.0.1:{args.port}/\nKeep this terminal open to view results.', flush=True)
    print(f'OUTPUT: {output}\nLOG: {output / "worker.log"}', flush=True)
    container = 'smgs-local-' + job
    mounts = [(source, '/source', True), (ROOT, '/service', True), (output, '/job', False)]
    command = ['docker', 'run', '--rm', '--platform', 'linux/amd64', '--name', container, '--network', 'none', '--cpus', '4',
               '-e', 'QT_QPA_PLATFORM=offscreen', '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'PYTHONUNBUFFERED=1']
    if sys.platform.startswith('linux'):
        command += ['--user', f'{os.getuid()}:{os.getgid()}']
    for host, target, readonly in mounts:
        if ',' in str(host):
            raise ValueError('Docker mount paths containing commas are not supported')
        command += ['--mount', f'type=bind,source={host},target={target}' + (',readonly' if readonly else '')]
    command += [args.image, 'python', '/service/tools/local_scan_worker.py', '--source', '/source', '--output', '/job']
    if args.prepare_only:
        command.append('--prepare-only')
    try:
        with (output / 'worker.log').open('w', encoding='utf-8') as log:
            worker = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, encoding='utf-8', errors='replace')
            for line in worker.stdout:
                print(line, end='', flush=True)
                log.write(line)
                log.flush()
            code = worker.wait()
        state = json.loads((output / 'status.json').read_text(encoding='utf-8'))
        if code or state['status'] not in {'REVIEW_REQUIRED', 'CHECKED'}:
            state.update(status='FAILED', error=state.get('error') or 'Worker stopped. See worker.log.')
            (output / 'status.json').write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
            print('FAILED: ' + state['error'], flush=True)
            code = 1
        elif state['status'] == 'REVIEW_REQUIRED':
            print(f'GLB: {output / "output" / "model.glb"}\nReview shape and texture before publication.', flush=True)
        if server:
            print('Preview stays open. Press Ctrl+C to close the preview server.', flush=True)
            threading.Event().wait()
        return code
    except KeyboardInterrupt:
        subprocess.run(['docker', 'stop', container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        state = json.loads((output / 'status.json').read_text(encoding='utf-8'))
        if state['status'] in {'QUEUED', 'PROCESSING', 'FINALIZING'}:
            state.update(status='CANCELLED', error='Stopped by user; no completed model claimed.')
            (output / 'status.json').write_text(json.dumps(state), encoding='utf-8')
        return 130
    finally:
        if server:
            server.shutdown()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
