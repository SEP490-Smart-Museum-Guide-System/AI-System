-- Run with psql as the PostgreSQL administrator, connected to EXISTING smgs_demo.
-- psql -X -v ON_ERROR_STOP=1 -U postgres -d smgs_demo -f scan_database.sql
-- No passwords, PostgreSQL network changes, BE-table grants, or database creation.
\set ON_ERROR_STOP on

BEGIN;

DO $setup$
DECLARE
    scan_role record;
BEGIN
    IF current_database() <> 'smgs_demo' THEN
        RAISE EXCEPTION 'Connect to existing smgs_demo before running this script';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'smgs_scan') THEN
        CREATE ROLE smgs_scan LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 10;
    END IF;
    SELECT * INTO STRICT scan_role FROM pg_roles WHERE rolname = 'smgs_scan';
    IF scan_role.rolsuper OR scan_role.rolcreatedb OR scan_role.rolcreaterole
       OR scan_role.rolreplication OR scan_role.rolbypassrls OR scan_role.rolinherit
       OR NOT scan_role.rolcanlogin THEN
        RAISE EXCEPTION 'Existing smgs_scan role has unexpected attributes; review manually';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_auth_members WHERE member = scan_role.oid) THEN
        RAISE EXCEPTION 'Existing smgs_scan has role memberships; review manually';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_namespace
        WHERE nspname = 'ai_3d_scan' AND nspowner <> scan_role.oid
    ) THEN
        RAISE EXCEPTION 'Existing ai_3d_scan has another owner; review before transferring Scan-only ownership';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'ai_3d_scan' AND c.relname = 'scan_jobs'
          AND c.relowner <> scan_role.oid
    ) THEN
        RAISE EXCEPTION 'Existing scan_jobs has another owner; review manually';
    END IF;
END;
$setup$;

GRANT CONNECT ON DATABASE smgs_demo TO smgs_scan;
CREATE SCHEMA IF NOT EXISTS ai_3d_scan AUTHORIZATION smgs_scan;
REVOKE ALL ON SCHEMA ai_3d_scan FROM PUBLIC;

-- Current Scan startup performs CREATE TABLE / ALTER TABLE / CREATE INDEX.
-- Scope ownership to Scan's schema/table, without CREATE on the whole database.
SET LOCAL ROLE smgs_scan;

CREATE TABLE IF NOT EXISTS ai_3d_scan.scan_jobs (
    id UUID PRIMARY KEY,
    artifact_id INTEGER NOT NULL,
    status VARCHAR(32) NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    image_count INTEGER NOT NULL,
    model_path TEXT,
    model_type VARCHAR(24),
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    capture_metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

ALTER TABLE ai_3d_scan.scan_jobs ADD COLUMN IF NOT EXISTS model_type VARCHAR(24);
CREATE INDEX IF NOT EXISTS ix_scan_jobs_status_created
    ON ai_3d_scan.scan_jobs (status, created_at);
REVOKE ALL ON TABLE ai_3d_scan.scan_jobs FROM PUBLIC;

RESET ROLE;
COMMIT;

-- Set a new SCRAM password separately in an interactive administrator psql session:
-- SET password_encryption = 'scram-sha-256';
-- \password smgs_scan
-- Store that password privately in Azure's .env.azure, never in this script/chat.
