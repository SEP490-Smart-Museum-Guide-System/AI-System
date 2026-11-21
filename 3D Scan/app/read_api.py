"""Read-only job status API; can roll out without replacing a busy worker."""
from fastapi import FastAPI
import psycopg

from . import jobs
from .main import (authenticate_before_upload, database_unavailable,
                   get_scan, list_artifact_scans)

app = FastAPI(title='SMGS Scan Status', docs_url=None, redoc_url=None, openapi_url=None)
app.middleware('http')(authenticate_before_upload)
app.add_exception_handler(psycopg.Error, database_unavailable)
app.add_api_route('/api/v1/scans/{job_id}', get_scan, methods=['GET'])
app.add_api_route('/api/v1/artifacts/{artifact_id}/scans', list_artifact_scans, methods=['GET'])


@app.get('/ready')
def ready():
    jobs.ping()
    return {'status': 'ok', 'read_only': True}
