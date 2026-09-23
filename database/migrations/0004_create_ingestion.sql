\set ON_ERROR_STOP on

BEGIN;

SET ROLE weather_owner;

CREATE TABLE ingestion.source_object (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider_id bigint NOT NULL,
    product_id bigint NOT NULL,
    product_run_id bigint,
    canonical_key text NOT NULL CHECK (btrim(canonical_key) <> ''),
    observed_url text NOT NULL CHECK (observed_url ~ '^https://'),
    observed_aliases jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(observed_aliases) = 'array'),
    response_headers jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(response_headers) = 'object'),
    reported_size_bytes bigint CHECK (reported_size_bytes >= 0),
    actual_size_bytes bigint CHECK (actual_size_bytes >= 0),
    local_raw_path text CHECK (
        local_raw_path IS NULL
        OR (btrim(local_raw_path) <> '' AND local_raw_path !~ '(^/|(^|/)\.\.(/|$))')
    ),
    sha256 text CHECK (sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'),
    status text NOT NULL DEFAULT 'discovered'
        CHECK (status IN (
            'discovered', 'downloading', 'downloaded', 'validated', 'quarantined',
            'failed', 'pending_deletion', 'deleted'
        )),
    download_attempts integer NOT NULL DEFAULT 0 CHECK (download_attempts >= 0),
    last_error_class text,
    last_error_message text,
    last_error_detail jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(last_error_detail) = 'object'),
    first_observed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    last_observed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    downloaded_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT source_object_product_provider_fk FOREIGN KEY (product_id, provider_id)
        REFERENCES catalogue.product (id, provider_id) ON DELETE RESTRICT,
    CONSTRAINT source_object_run_product_fk FOREIGN KEY (product_run_id, product_id)
        REFERENCES catalogue.product_run (id, product_id) ON DELETE RESTRICT,
    CONSTRAINT source_object_canonical_uk UNIQUE (provider_id, canonical_key),
    CONSTRAINT source_object_downloaded_metadata_ck CHECK (
        status NOT IN ('downloaded', 'validated')
        OR (
            local_raw_path IS NOT NULL
            AND actual_size_bytes IS NOT NULL
            AND sha256 IS NOT NULL
            AND downloaded_at IS NOT NULL
        )
    ),
    CONSTRAINT source_object_observed_time_ck CHECK (last_observed_at >= first_observed_at)
);

CREATE INDEX source_object_product_status_idx
    ON ingestion.source_object (product_id, status, last_observed_at DESC);
CREATE INDEX source_object_run_idx
    ON ingestion.source_object (product_run_id)
    WHERE product_run_id IS NOT NULL;

CREATE TABLE ingestion.processing_attempt (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_object_id bigint REFERENCES ingestion.source_object (id) ON DELETE RESTRICT,
    asset_id bigint REFERENCES catalogue.asset (id) ON DELETE RESTRICT,
    attempt_type text NOT NULL
        CHECK (attempt_type IN ('download', 'validate', 'extract', 'transform', 'derive', 'publish')),
    attempt_number integer NOT NULL CHECK (attempt_number > 0),
    status text NOT NULL
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    started_at timestamptz,
    completed_at timestamptz,
    worker_hostname text,
    input_paths jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(input_paths) = 'array'),
    output_paths jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(output_paths) = 'array'),
    command_line text,
    tool_versions jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(tool_versions) = 'object'),
    metrics jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metrics) = 'object'),
    error_class text,
    error_message text,
    error_detail jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(error_detail) = 'object'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT processing_attempt_subject_ck CHECK (
        source_object_id IS NOT NULL OR asset_id IS NOT NULL
    ),
    CONSTRAINT processing_attempt_identity_uk UNIQUE NULLS NOT DISTINCT (
        source_object_id, asset_id, attempt_type, attempt_number
    ),
    CONSTRAINT processing_attempt_timing_ck CHECK (
        (status = 'queued' AND started_at IS NULL AND completed_at IS NULL)
        OR (status = 'running' AND started_at IS NOT NULL AND completed_at IS NULL)
        OR (
            status IN ('succeeded', 'failed', 'cancelled')
            AND started_at IS NOT NULL
            AND completed_at IS NOT NULL
            AND completed_at >= started_at
        )
    ),
    CONSTRAINT processing_attempt_error_ck CHECK (
        status <> 'failed' OR error_message IS NOT NULL
    )
);

CREATE INDEX processing_attempt_source_idx
    ON ingestion.processing_attempt (source_object_id, created_at DESC)
    WHERE source_object_id IS NOT NULL;
CREATE INDEX processing_attempt_asset_idx
    ON ingestion.processing_attempt (asset_id, created_at DESC)
    WHERE asset_id IS NOT NULL;

CREATE TABLE ingestion.data_quality_result (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_object_id bigint REFERENCES ingestion.source_object (id) ON DELETE CASCADE,
    asset_id bigint REFERENCES catalogue.asset (id) ON DELETE CASCADE,
    check_name text NOT NULL CHECK (check_name ~ '^[a-z][a-z0-9_]*$'),
    status text NOT NULL CHECK (status IN ('passed', 'warning', 'failed', 'skipped')),
    measured_value jsonb,
    expected_value jsonb,
    details jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(details) = 'object'),
    checked_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT data_quality_subject_ck CHECK (
        num_nonnulls(source_object_id, asset_id) = 1
    )
);

CREATE INDEX data_quality_source_idx
    ON ingestion.data_quality_result (source_object_id, check_name, checked_at DESC)
    WHERE source_object_id IS NOT NULL;
CREATE INDEX data_quality_asset_idx
    ON ingestion.data_quality_result (asset_id, check_name, checked_at DESC)
    WHERE asset_id IS NOT NULL;

CREATE TABLE audit.event (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type text NOT NULL CHECK (event_type ~ '^[a-z][a-z0-9_.]*$'),
    actor text NOT NULL DEFAULT current_user,
    object_type text NOT NULL CHECK (btrim(object_type) <> ''),
    object_key text NOT NULL CHECK (btrim(object_key) <> ''),
    details jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(details) = 'object'),
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX audit_event_object_idx
    ON audit.event (object_type, object_key, occurred_at DESC);

GRANT SELECT, INSERT, UPDATE ON ingestion.source_object,
    ingestion.processing_attempt, ingestion.data_quality_result
    TO weather_ingest;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ingestion TO weather_ingest;
GRANT INSERT ON audit.event TO weather_ingest;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA audit TO weather_ingest;

GRANT SELECT ON ingestion.source_object, ingestion.processing_attempt,
    ingestion.data_quality_result, audit.event
    TO weather_readonly, weather_backup;

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
