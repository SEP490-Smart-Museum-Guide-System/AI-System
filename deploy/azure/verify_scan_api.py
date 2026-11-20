"""Public HTTPS/auth/DB-read checks; does not upload images or create scan jobs."""
import argparse
import json
from pathlib import Path
import urllib.error
import urllib.request
from uuid import uuid4


def run(config_path):
    values = dict(line.split('=', 1) for line in config_path.read_text(encoding='utf-8-sig').splitlines()
                  if line and not line.startswith('#') and '=' in line)
    origin = values['AiScan__BaseUrl'].rstrip('/')

    def call(path, data=None, authorized=True):
        headers = {'Content-Type': 'application/json'}
        if authorized:
            headers['X-Service-Key'] = values['AiScan__ServiceKey']
        request = urllib.request.Request(origin + path, data=data, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as response:
            return response.code, response.read()

    ready_status, data = call('/ready', authorized=False)
    ready = json.loads(data) if ready_status == 200 else {}
    missing = str(uuid4())
    list_status, listed = call('/api/v1/artifacts/0/scans')
    checks = {
        'ready200': ready_status == 200,
        'databaseReady': ready.get('database_ready') is True,
        'workerReady': ready.get('worker_ready') is True,
        'colmapAvailable': ready.get('colmap_available') is True,
        'openMvsAvailable': ready.get('openmvs_cpu_available') is True,
        'missingKeyRejectedBeforeUploadParsing': call('/api/v1/scans', b'not multipart', False)[0] == 401,
        'authenticatedInvalidUploadRejected': call('/api/v1/scans', b'not multipart')[0] == 422,
        'authenticatedArtifactList200': list_status == 200 and isinstance(json.loads(listed), list),
        'missingJob404': call('/api/v1/scans/' + missing)[0] == 404,
        'modelDownloadRequiresKey': call('/api/v1/scans/' + missing + '/model', authorized=False)[0] == 401,
    }
    return {'origin': origin, 'publicTlsCertificateVerified': True, 'scope': 'Public API readiness/auth/DB read',
            'beIntegrationTested': False, 'fullPhotogrammetryJobTested': False, 'scanJobCreated': False,
            'ready': ready, 'checks': checks}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.config)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(report))
    if not all(report['checks'].values()):
        raise SystemExit(1)
