"""Run inside the Scan image; checks native CPU binaries without a DB/job claim."""
import json
import shutil
import subprocess

from app.reconstruction import openmvs_available


report = {'scope': 'Scan image native runtime only; DB/API/reconstruction not tested',
          'cpuOnly': True, 'tools': []}
for name in ('colmap', 'InterfaceCOLMAP', 'DensifyPointCloud', 'ReconstructMesh', 'RefineMesh', 'TextureMesh'):
    path = shutil.which(name)
    row = {'name': name, 'available': bool(path), 'sharedLibrariesResolved': False, 'helpRuns': False}
    if path:
        linked = subprocess.run(['ldd', path], text=True, capture_output=True, timeout=15)
        row['sharedLibrariesResolved'] = linked.returncode == 0 and 'not found' not in linked.stdout + linked.stderr
        help_result = subprocess.run([path, 'help' if name == 'colmap' else '--help'], text=True,
                                     capture_output=True, timeout=20)
        text = help_result.stdout + help_result.stderr
        row['helpRuns'] = help_result.returncode in (0, 1) and ('options' in text.lower() or 'usage' in text.lower())
        row['helpExitCode'] = help_result.returncode
    report['tools'].append(row)
report['openMvsAvailable'] = openmvs_available()
report['passed'] = report['openMvsAvailable'] and all(
    row['available'] and row['sharedLibrariesResolved'] and row['helpRuns'] for row in report['tools'])
print(json.dumps(report))
if not report['passed']:
    raise SystemExit(1)
