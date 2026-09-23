\set ON_ERROR_STOP on

BEGIN;

-- The migrator owns weather_app and therefore creates the schema on behalf of
-- the non-login object-owner role, matching migration 0002.
CREATE SCHEMA simulation AUTHORIZATION weather_owner;

SET ROLE weather_owner;
REVOKE ALL ON SCHEMA simulation FROM PUBLIC;
GRANT USAGE ON SCHEMA simulation TO weather_api, weather_ingest;
GRANT USAGE ON SCHEMA simulation TO weather_readonly, weather_backup;

CREATE TABLE simulation.model_build (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_name text NOT NULL CHECK (model_name IN ('CFFEPS', 'FLEXPART')),
    model_version text NOT NULL CHECK (btrim(model_version) <> ''),
    source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    patch_set_sha256 text NOT NULL CHECK (patch_set_sha256 ~ '^[0-9a-f]{64}$'),
    executable_sha256 text NOT NULL CHECK (executable_sha256 ~ '^[0-9a-f]{64}$'),
    container_digest text CHECK (container_digest IS NULL OR btrim(container_digest) <> ''),
    toolchain jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(toolchain) = 'object'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    enabled boolean NOT NULL DEFAULT false,
    UNIQUE (model_name, model_version, source_sha256, patch_set_sha256, executable_sha256)
);

CREATE TABLE simulation.scenario (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 100),
    description text NOT NULL DEFAULT '' CHECK (char_length(description) <= 2000),
    owner_label text NOT NULL DEFAULT 'local' CHECK (btrim(owner_label) <> ''),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    archived_at timestamptz
);

CREATE TABLE simulation.scenario_revision (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scenario_id uuid NOT NULL REFERENCES simulation.scenario (id) ON DELETE RESTRICT,
    revision_number integer NOT NULL CHECK (revision_number > 0),
    canonical_config jsonb NOT NULL CHECK (jsonb_typeof(canonical_config) = 'object'),
    config_sha256 text NOT NULL CHECK (config_sha256 ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (scenario_id, revision_number),
    UNIQUE (scenario_id, config_sha256),
    UNIQUE (scenario_id, id)
);

CREATE TABLE simulation.run (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scenario_revision_id uuid NOT NULL REFERENCES simulation.scenario_revision (id) ON DELETE RESTRICT,
    run_kind text NOT NULL CHECK (run_kind IN ('interactive', 'operational', 'validation')),
    status text NOT NULL DEFAULT 'queued' CHECK (status IN (
        'queued', 'resolving_inputs', 'emissions_running', 'transport_running',
        'processing_outputs', 'publishing', 'complete', 'complete_with_warnings',
        'cancellation_requested', 'cancelled', 'failed'
    )),
    requested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    queued_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    started_at timestamptz,
    completed_at timestamptz,
    requested_by text NOT NULL DEFAULT 'local' CHECK (btrim(requested_by) <> ''),
    gfs_cycle_time timestamptz,
    cffeps_build_id bigint REFERENCES simulation.model_build (id) ON DELETE RESTRICT,
    flexpart_build_id bigint REFERENCES simulation.model_build (id) ON DELETE RESTRICT,
    random_seed_policy jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(random_seed_policy) = 'object'),
    input_manifest_path text CHECK (
        input_manifest_path IS NULL OR (
            btrim(input_manifest_path) <> '' AND input_manifest_path !~ '(^/|(^|/)\.\.(/|$))'
        )
    ),
    output_manifest_path text CHECK (
        output_manifest_path IS NULL OR (
            btrim(output_manifest_path) <> '' AND output_manifest_path !~ '(^/|(^|/)\.\.(/|$))'
        )
    ),
    product_run_id bigint REFERENCES catalogue.product_run (id) ON DELETE RESTRICT,
    metrics jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metrics) = 'object'),
    warnings jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(warnings) = 'array'),
    error_class text,
    error_message text,
    run_key text NOT NULL UNIQUE CHECK (run_key ~ '^[0-9a-f]{64}$'),
    cancellation_requested_at timestamptz,
    CONSTRAINT simulation_run_completion_ck CHECK (
        (status IN ('complete', 'complete_with_warnings', 'cancelled', 'failed'))
        = (completed_at IS NOT NULL)
    ),
    CONSTRAINT simulation_run_failure_ck CHECK (status <> 'failed' OR error_message IS NOT NULL)
);

CREATE INDEX simulation_run_queue_idx
    ON simulation.run (requested_at, id) WHERE status = 'queued';
CREATE INDEX simulation_run_revision_idx
    ON simulation.run (scenario_revision_id, requested_at DESC);

CREATE TABLE simulation.run_input (
    run_id uuid NOT NULL REFERENCES simulation.run (id) ON DELETE CASCADE,
    input_kind text NOT NULL CHECK (input_kind ~ '^[a-z][a-z0-9_]*$'),
    relative_path text NOT NULL CHECK (
        btrim(relative_path) <> '' AND relative_path !~ '(^/|(^|/)\.\.(/|$))'
    ),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    size_bytes bigint NOT NULL CHECK (size_bytes > 0),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    PRIMARY KEY (run_id, input_kind, relative_path)
);

CREATE TABLE simulation.run_artifact (
    run_id uuid NOT NULL REFERENCES simulation.run (id) ON DELETE CASCADE,
    artifact_kind text NOT NULL CHECK (artifact_kind ~ '^[a-z][a-z0-9_]*$'),
    relative_path text NOT NULL CHECK (
        btrim(relative_path) <> '' AND relative_path !~ '(^/|(^|/)\.\.(/|$))'
    ),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    size_bytes bigint NOT NULL CHECK (size_bytes > 0),
    mime_type text NOT NULL CHECK (btrim(mime_type) <> ''),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    status text NOT NULL DEFAULT 'available'
        CHECK (status IN ('processing', 'available', 'quarantined', 'deleted')),
    PRIMARY KEY (run_id, artifact_kind, relative_path)
);

GRANT SELECT ON simulation.model_build, simulation.scenario,
    simulation.scenario_revision, simulation.run, simulation.run_input,
    simulation.run_artifact TO weather_api, weather_ingest, weather_readonly, weather_backup;
GRANT INSERT ON simulation.scenario, simulation.scenario_revision, simulation.run
    TO weather_api;
GRANT UPDATE (name, description, archived_at, updated_at) ON simulation.scenario
    TO weather_api;
GRANT UPDATE (status, cancellation_requested_at) ON simulation.run TO weather_api;
GRANT INSERT, UPDATE ON simulation.model_build, simulation.run,
    simulation.run_input, simulation.run_artifact TO weather_ingest;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA simulation TO weather_ingest;

ALTER DEFAULT PRIVILEGES IN SCHEMA simulation REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA simulation REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA simulation GRANT SELECT ON TABLES TO weather_readonly, weather_backup;
ALTER DEFAULT PRIVILEGES IN SCHEMA simulation GRANT SELECT ON SEQUENCES TO weather_readonly, weather_backup;

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
