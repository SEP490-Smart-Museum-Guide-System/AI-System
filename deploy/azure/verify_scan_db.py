"""Run through Scan Compose environment; no secrets or permanent test job output."""
import argparse
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

from psycopg import sql
from psycopg.types.json import Jsonb

from app import jobs
from app.settings import DB_SCHEMA


def verify(write_probe=False):
    if os.environ.get('PGSSLMODE') != 'verify-full':
        raise RuntimeError('Production preflight requires PGSSLMODE=verify-full')
    ca = os.environ.get('PGSSLROOTCERT', '')
    if not ca or not Path(ca).is_file():
        raise RuntimeError('Configured PostgreSQL CA bundle is missing from container')
    if DB_SCHEMA != 'ai_3d_scan':
        raise RuntimeError('Unexpected Scan schema')
    with jobs._connect() as db:
        identity = db.execute('SELECT current_user AS role, current_database() AS database').fetchone()
        tls = db.execute('SELECT ssl, version, cipher FROM pg_stat_ssl WHERE pid=pg_backend_pid()').fetchone()
        role = db.execute('SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()
        owner = db.execute(
            'SELECT pg_get_userbyid(c.relowner) AS owner FROM pg_class c '
            'JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relname=%s',
            (DB_SCHEMA, 'scan_jobs'),
        ).fetchone()
        columns = db.execute(
            'SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s',
            (DB_SCHEMA, 'scan_jobs'),
        ).fetchall()
        required = {'id', 'artifact_id', 'status', 'progress', 'image_count', 'model_path',
                    'model_type', 'error', 'created_at', 'updated_at', 'capture_metadata'}
        checks = {
            'expectedRole': identity['role'] == 'smgs_scan',
            'expectedDatabase': identity['database'] == 'smgs_demo',
            'tlsEncrypted': bool(tls and tls['ssl']),
            'nonAdministrativeRole': not any(role.values()),
            'ownsScanTableForStartupDdl': bool(owner and owner['owner'] == identity['role']),
            'expectedColumnsPresent': required <= {row['column_name'] for row in columns},
        }
        report = {'scope': 'Azure container to existing BE PostgreSQL', 'sslMode': 'verify-full',
                  'role': identity['role'], 'database': identity['database'], 'tls': dict(tls) if tls else None,
                  'schema': DB_SCHEMA, 'permanentTestJobCreated': False, 'checks': checks}
    if not all(checks.values()):
        return report
    if write_probe:
        job_id = uuid4()
        table = sql.SQL('{}.{}').format(sql.Identifier(DB_SCHEMA), sql.Identifier('scan_jobs'))
        with jobs._connect() as db:
            db.execute(sql.SQL(
                "INSERT INTO {} (id,artifact_id,status,progress,image_count,created_at,updated_at,capture_metadata) "
                "VALUES (%s,0,'QUEUED',0,5,now(),now(),%s)"
            ).format(table), (job_id, Jsonb({'connectionSmokeTest': True})))
            db.execute(sql.SQL("UPDATE {} SET status='FAILED',progress=15 WHERE id=%s").format(table), (job_id,))
            row = db.execute(sql.SQL('SELECT status,progress FROM {} WHERE id=%s').format(table), (job_id,)).fetchone()
            checks['jobInsertReadUpdate'] = row['status'] == 'FAILED' and row['progress'] == 15
            db.rollback()
            row = db.execute(sql.SQL('SELECT id FROM {} WHERE id=%s').format(table), (job_id,)).fetchone()
            checks['testJobRolledBack'] = row is None
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-probe', action='store_true')
    args = parser.parse_args()
    try:
        report = verify(args.write_probe)
        print(json.dumps(report))
        if not all(report['checks'].values()):
            raise SystemExit(1)
    except Exception as exc:
        message = str(exc)
        password = os.environ.get('AI_SYSTEM_DB_PASSWORD', '')
        if password:
            message = message.replace(password, '<redacted>')
        print(json.dumps({'passed': False, 'errorType': type(exc).__name__,
                          'sqlState': getattr(exc, 'sqlstate', None), 'detail': message[:1000]}))
        sys.exit(1)
