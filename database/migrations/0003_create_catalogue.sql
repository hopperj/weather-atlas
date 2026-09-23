\set ON_ERROR_STOP on

BEGIN;

SET ROLE weather_owner;

CREATE TABLE catalogue.provider (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL UNIQUE CHECK (code ~ '^[a-z][a-z0-9_]*$'),
    name text NOT NULL CHECK (btrim(name) <> ''),
    base_url text NOT NULL CHECK (base_url ~ '^https://'),
    documentation_url text NOT NULL CHECK (documentation_url ~ '^https://'),
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE catalogue.product (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider_id bigint NOT NULL REFERENCES catalogue.provider (id) ON DELETE RESTRICT,
    code text NOT NULL UNIQUE CHECK (code ~ '^[a-z][a-z0-9_]*$'),
    name text NOT NULL CHECK (btrim(name) <> ''),
    description text NOT NULL DEFAULT '',
    product_kind text NOT NULL
        CHECK (product_kind IN ('forecast', 'analysis', 'ensemble_analysis')),
    enabled boolean NOT NULL DEFAULT true,
    priority integer NOT NULL DEFAULT 100 CHECK (priority >= 0),
    schedule_config jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(schedule_config) = 'object'),
    retention_config jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(retention_config) = 'object'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT product_provider_code_uk UNIQUE (provider_id, code),
    CONSTRAINT product_id_provider_uk UNIQUE (id, provider_id)
);

CREATE INDEX product_enabled_priority_idx
    ON catalogue.product (enabled, priority, code);

CREATE TABLE catalogue.domain (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id bigint NOT NULL REFERENCES catalogue.product (id) ON DELETE RESTRICT,
    code text NOT NULL CHECK (code ~ '^[a-z][a-z0-9_]*$'),
    name text NOT NULL CHECK (btrim(name) <> ''),
    native_crs text NOT NULL CHECK (btrim(native_crs) <> ''),
    grid_resolution_x_m numeric CHECK (grid_resolution_x_m > 0),
    grid_resolution_y_m numeric CHECK (grid_resolution_y_m > 0),
    grid_width integer CHECK (grid_width > 0),
    grid_height integer CHECK (grid_height > 0),
    footprint geometry(MultiPolygon, 4326),
    source_grid_metadata jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(source_grid_metadata) = 'object'),
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT domain_product_code_uk UNIQUE (product_id, code),
    CONSTRAINT domain_product_id_uk UNIQUE (product_id, id),
    CONSTRAINT domain_grid_dimensions_ck CHECK (
        (grid_width IS NULL AND grid_height IS NULL)
        OR (grid_width IS NOT NULL AND grid_height IS NOT NULL)
    ),
    CONSTRAINT domain_grid_resolution_ck CHECK (
        (grid_resolution_x_m IS NULL AND grid_resolution_y_m IS NULL)
        OR (grid_resolution_x_m IS NOT NULL AND grid_resolution_y_m IS NOT NULL)
    )
);

CREATE INDEX domain_footprint_gix ON catalogue.domain USING gist (footprint);

CREATE TABLE catalogue.vertical_level (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL UNIQUE CHECK (code ~ '^[a-z0-9][a-z0-9_]*$'),
    name text NOT NULL CHECK (btrim(name) <> ''),
    level_type text NOT NULL CHECK (btrim(level_type) <> ''),
    level_value numeric,
    unit text,
    display_order integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT vertical_level_value_unit_ck CHECK (
        (level_value IS NULL AND unit IS NULL)
        OR (level_value IS NOT NULL AND unit IS NOT NULL AND btrim(unit) <> '')
    )
);

CREATE TABLE catalogue.variable (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL UNIQUE CHECK (code ~ '^[a-z][a-z0-9_]*$'),
    name text NOT NULL CHECK (btrim(name) <> ''),
    description text NOT NULL DEFAULT '',
    variable_class text NOT NULL
        CHECK (variable_class IN ('atmosphere', 'precipitation', 'air_quality')),
    canonical_unit text NOT NULL CHECK (btrim(canonical_unit) <> ''),
    value_kind text NOT NULL
        CHECK (value_kind IN ('continuous', 'categorical', 'index', 'vector_component')),
    is_vector_component boolean NOT NULL DEFAULT false,
    vector_group text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT variable_vector_ck CHECK (
        (is_vector_component AND value_kind = 'vector_component' AND vector_group IS NOT NULL)
        OR (NOT is_vector_component AND value_kind <> 'vector_component' AND vector_group IS NULL)
    )
);

CREATE TABLE catalogue.product_field (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id bigint NOT NULL REFERENCES catalogue.product (id) ON DELETE RESTRICT,
    variable_id bigint NOT NULL REFERENCES catalogue.variable (id) ON DELETE RESTRICT,
    vertical_level_id bigint NOT NULL REFERENCES catalogue.vertical_level (id) ON DELETE RESTRICT,
    source_parameter text NOT NULL CHECK (btrim(source_parameter) <> ''),
    source_level_type text NOT NULL CHECK (btrim(source_level_type) <> ''),
    source_level_value numeric,
    source_unit text NOT NULL CHECK (btrim(source_unit) <> ''),
    conversion_key text NOT NULL CHECK (conversion_key ~ '^[a-z][a-z0-9_]*$'),
    displayable boolean NOT NULL DEFAULT true,
    download_enabled boolean NOT NULL DEFAULT false,
    processing_enabled boolean NOT NULL DEFAULT false,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT product_field_source_uk UNIQUE NULLS NOT DISTINCT (
        product_id, source_parameter, source_level_type, source_level_value
    ),
    CONSTRAINT product_field_id_product_level_uk UNIQUE (id, product_id, vertical_level_id),
    CONSTRAINT product_field_id_variable_uk UNIQUE (id, variable_id),
    CONSTRAINT product_field_processing_ck CHECK (NOT processing_enabled OR download_enabled)
);

CREATE UNIQUE INDEX product_field_display_identity_uk
    ON catalogue.product_field (product_id, variable_id, vertical_level_id)
    WHERE displayable;

CREATE TABLE catalogue.product_run (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id bigint NOT NULL REFERENCES catalogue.product (id) ON DELETE RESTRICT,
    domain_id bigint NOT NULL,
    run_time timestamptz NOT NULL,
    source_status text NOT NULL DEFAULT 'discovered'
        CHECK (source_status IN (
            'discovered', 'downloading', 'partially_available', 'complete', 'failed', 'expired'
        )),
    processing_status text NOT NULL DEFAULT 'discovered'
        CHECK (processing_status IN (
            'discovered', 'processing', 'partially_available', 'complete',
            'complete_with_warnings', 'failed', 'expired'
        )),
    is_visible boolean NOT NULL DEFAULT false,
    expected_asset_count integer NOT NULL DEFAULT 0 CHECK (expected_asset_count >= 0),
    discovered_asset_count integer NOT NULL DEFAULT 0 CHECK (discovered_asset_count >= 0),
    downloaded_asset_count integer NOT NULL DEFAULT 0 CHECK (downloaded_asset_count >= 0),
    processed_asset_count integer NOT NULL DEFAULT 0 CHECK (processed_asset_count >= 0),
    failed_asset_count integer NOT NULL DEFAULT 0 CHECK (failed_asset_count >= 0),
    source_manifest jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(source_manifest) = 'object'),
    first_discovered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT product_run_domain_fk FOREIGN KEY (product_id, domain_id)
        REFERENCES catalogue.domain (product_id, id) ON DELETE RESTRICT,
    CONSTRAINT product_run_identity_uk UNIQUE (product_id, domain_id, run_time),
    CONSTRAINT product_run_id_product_uk UNIQUE (id, product_id),
    CONSTRAINT product_run_completion_ck CHECK (
        completed_at IS NULL
        OR processing_status IN ('complete', 'complete_with_warnings', 'failed', 'expired')
    )
);

CREATE INDEX product_run_visible_time_idx
    ON catalogue.product_run (product_id, run_time DESC)
    WHERE is_visible;

CREATE TABLE catalogue.product_time (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_run_id bigint NOT NULL REFERENCES catalogue.product_run (id) ON DELETE CASCADE,
    valid_time timestamptz NOT NULL,
    forecast_hour integer CHECK (forecast_hour >= 0),
    interval_start timestamptz,
    interval_end timestamptz,
    time_kind text NOT NULL DEFAULT 'instant'
        CHECK (time_kind IN ('instant', 'accumulation', 'average', 'maximum')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT product_time_identity_uk UNIQUE NULLS NOT DISTINCT (
        product_run_id, valid_time, forecast_hour, interval_start, interval_end, time_kind
    ),
    CONSTRAINT product_time_id_run_uk UNIQUE (id, product_run_id),
    CONSTRAINT product_time_interval_ck CHECK (
        (time_kind = 'instant' AND interval_start IS NULL AND interval_end IS NULL)
        OR (
            time_kind <> 'instant'
            AND interval_start IS NOT NULL
            AND interval_end IS NOT NULL
            AND interval_start <= interval_end
            AND valid_time = interval_end
        )
    )
);

CREATE INDEX product_time_run_valid_idx
    ON catalogue.product_time (product_run_id, valid_time);

CREATE TABLE catalogue.asset (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id bigint NOT NULL REFERENCES catalogue.product (id) ON DELETE RESTRICT,
    product_run_id bigint NOT NULL,
    product_time_id bigint NOT NULL,
    product_field_id bigint NOT NULL,
    vertical_level_id bigint NOT NULL REFERENCES catalogue.vertical_level (id) ON DELETE RESTRICT,
    asset_role text NOT NULL
        CHECK (asset_role IN ('processed_cog', 'derived_cog', 'thumbnail', 'vector')),
    storage_backend text NOT NULL DEFAULT 'local' CHECK (storage_backend = 'local'),
    relative_path text NOT NULL CHECK (
        btrim(relative_path) <> ''
        AND relative_path !~ '(^/|(^|/)\.\.(/|$))'
    ),
    mime_type text NOT NULL CHECK (btrim(mime_type) <> ''),
    file_size_bytes bigint NOT NULL CHECK (file_size_bytes > 0),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    projection text NOT NULL CHECK (btrim(projection) <> ''),
    bounds geometry(Polygon, 4326) NOT NULL,
    width integer NOT NULL CHECK (width > 0),
    height integer NOT NULL CHECK (height > 0),
    band_count integer NOT NULL DEFAULT 1 CHECK (band_count > 0),
    nodata_value double precision,
    minimum_value double precision,
    maximum_value double precision,
    statistics jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(statistics) = 'object'),
    provenance jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(provenance) = 'object'),
    status text NOT NULL DEFAULT 'available'
        CHECK (status IN ('processing', 'available', 'pending_deletion', 'deleted', 'failed')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT asset_run_product_fk FOREIGN KEY (product_run_id, product_id)
        REFERENCES catalogue.product_run (id, product_id) ON DELETE CASCADE,
    CONSTRAINT asset_time_run_fk FOREIGN KEY (product_time_id, product_run_id)
        REFERENCES catalogue.product_time (id, product_run_id) ON DELETE CASCADE,
    CONSTRAINT asset_field_product_level_fk
        FOREIGN KEY (product_field_id, product_id, vertical_level_id)
        REFERENCES catalogue.product_field (id, product_id, vertical_level_id) ON DELETE RESTRICT,
    CONSTRAINT asset_semantic_identity_uk UNIQUE (
        product_run_id, product_time_id, product_field_id, vertical_level_id, asset_role
    ),
    CONSTRAINT asset_relative_path_uk UNIQUE (storage_backend, relative_path),
    CONSTRAINT asset_value_range_ck CHECK (
        minimum_value IS NULL OR maximum_value IS NULL OR minimum_value <= maximum_value
    )
);

CREATE INDEX asset_available_lookup_idx
    ON catalogue.asset (product_id, product_run_id, product_time_id, product_field_id)
    WHERE status = 'available';
CREATE INDEX asset_bounds_gix ON catalogue.asset USING gist (bounds);

GRANT SELECT ON catalogue.provider, catalogue.product, catalogue.domain,
    catalogue.vertical_level, catalogue.variable, catalogue.product_field,
    catalogue.product_run, catalogue.product_time, catalogue.asset
    TO weather_api, weather_readonly, weather_backup;

GRANT SELECT ON catalogue.product, catalogue.domain, catalogue.vertical_level,
    catalogue.variable, catalogue.product_field, catalogue.product_run,
    catalogue.product_time, catalogue.asset
    TO weather_tiles;

GRANT SELECT ON catalogue.provider, catalogue.product, catalogue.domain,
    catalogue.vertical_level, catalogue.variable, catalogue.product_field,
    catalogue.product_run, catalogue.product_time, catalogue.asset
    TO weather_ingest;
GRANT INSERT, UPDATE ON catalogue.product_run, catalogue.product_time, catalogue.asset
    TO weather_ingest;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA catalogue TO weather_ingest;

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
