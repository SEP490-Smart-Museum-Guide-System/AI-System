-- Run as PostgreSQL administrator, connected to the EXISTING smgs_demo.
-- No passwords, BE table grants, or network changes in this file.
\set ON_ERROR_STOP on
BEGIN;
DO $setup$
DECLARE vision_role record;
BEGIN
    IF current_database() <> 'smgs_demo' THEN
        RAISE EXCEPTION 'Connect to existing smgs_demo first';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'smgs_vision') THEN
        CREATE ROLE smgs_vision LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 5;
    END IF;
    SELECT * INTO STRICT vision_role FROM pg_roles WHERE rolname = 'smgs_vision';
    IF vision_role.rolsuper OR vision_role.rolcreatedb OR vision_role.rolcreaterole
       OR vision_role.rolreplication OR vision_role.rolbypassrls OR vision_role.rolinherit
       OR NOT vision_role.rolcanlogin THEN
        RAISE EXCEPTION 'Existing smgs_vision role has unexpected privileges; review manually';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_auth_members WHERE member = vision_role.oid) THEN
        RAISE EXCEPTION 'Existing smgs_vision has role memberships; review manually';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'ai_vision' AND nspowner <> vision_role.oid) THEN
        RAISE EXCEPTION 'Existing ai_vision has another owner; review Vision-only ownership manually';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
               WHERE n.nspname='ai_vision' AND c.relname IN ('artifact_reference_embeddings', 'artifact_reference_embeddings_id_seq')
                 AND c.relowner <> vision_role.oid) THEN
        RAISE EXCEPTION 'Existing Vision table/sequence has another owner; review manually';
    END IF;
END;
$setup$;
GRANT CONNECT ON DATABASE smgs_demo TO smgs_vision;
CREATE SCHEMA IF NOT EXISTS ai_vision AUTHORIZATION smgs_vision;
REVOKE ALL ON SCHEMA ai_vision FROM PUBLIC;
SET LOCAL ROLE smgs_vision;
CREATE TABLE IF NOT EXISTS ai_vision.artifact_reference_embeddings (
    id BIGSERIAL PRIMARY KEY,
    artifact_id INTEGER NOT NULL,
    image_name VARCHAR(255) NOT NULL,
    embedding BYTEA NOT NULL,
    dimensions INTEGER NOT NULL,
    model_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_ai_vision_embeddings_artifact_id ON ai_vision.artifact_reference_embeddings (artifact_id);
CREATE INDEX IF NOT EXISTS ix_ai_vision_embeddings_model_id ON ai_vision.artifact_reference_embeddings (model_id);
REVOKE ALL ON TABLE ai_vision.artifact_reference_embeddings FROM PUBLIC;
REVOKE ALL ON SEQUENCE ai_vision.artifact_reference_embeddings_id_seq FROM PUBLIC;
RESET ROLE;
COMMIT;
-- Set the password privately in administrator psql: \password smgs_vision
-- For the existing TLS allowlist, permit smgs_vision from 172.198.161.72/32 only.
-- No pgvector extension is needed: the current service stores BYTEA embeddings.
