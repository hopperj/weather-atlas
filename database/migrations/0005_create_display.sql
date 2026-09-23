\set ON_ERROR_STOP on

BEGIN;

SET ROLE weather_owner;

CREATE TABLE display.palette (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL CHECK (code ~ '^[a-z][a-z0-9_]*$'),
    name text NOT NULL CHECK (btrim(name) <> ''),
    description text NOT NULL DEFAULT '',
    revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
    definition jsonb NOT NULL CHECK (jsonb_typeof(definition) = 'object'),
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT palette_code_revision_uk UNIQUE (code, revision)
);

CREATE TABLE display.variable_style (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    variable_id bigint NOT NULL REFERENCES catalogue.variable (id) ON DELETE RESTRICT,
    product_field_id bigint,
    palette_id bigint NOT NULL REFERENCES display.palette (id) ON DELETE RESTRICT,
    code text NOT NULL DEFAULT 'default' CHECK (code ~ '^[a-z][a-z0-9_]*$'),
    name text NOT NULL CHECK (btrim(name) <> ''),
    revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
    default_min double precision NOT NULL,
    default_max double precision NOT NULL,
    scale_type text NOT NULL DEFAULT 'linear'
        CHECK (scale_type IN ('linear', 'logarithmic', 'categorical', 'threshold', 'diverging')),
    clamp_values boolean NOT NULL DEFAULT true,
    opacity double precision NOT NULL DEFAULT 0.8 CHECK (opacity >= 0 AND opacity <= 1),
    resampling_method text NOT NULL DEFAULT 'bilinear'
        CHECK (resampling_method IN ('nearest', 'bilinear', 'average')),
    legend_precision integer NOT NULL DEFAULT 1 CHECK (legend_precision >= 0 AND legend_precision <= 10),
    nodata_transparent boolean NOT NULL DEFAULT true,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT variable_style_field_variable_fk FOREIGN KEY (product_field_id, variable_id)
        REFERENCES catalogue.product_field (id, variable_id) ON DELETE RESTRICT,
    CONSTRAINT variable_style_identity_uk UNIQUE NULLS NOT DISTINCT (
        variable_id, product_field_id, code, revision
    ),
    CONSTRAINT variable_style_range_ck CHECK (default_min < default_max),
    CONSTRAINT variable_style_log_ck CHECK (scale_type <> 'logarithmic' OR default_min > 0)
);

CREATE INDEX variable_style_enabled_idx
    ON display.variable_style (variable_id, code, revision DESC)
    WHERE enabled;

CREATE TABLE display.layer_specification (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    public_token uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    specification_hash text NOT NULL UNIQUE CHECK (specification_hash ~ '^[0-9a-f]{64}$'),
    asset_id bigint NOT NULL REFERENCES catalogue.asset (id) ON DELETE RESTRICT,
    variable_style_id bigint NOT NULL REFERENCES display.variable_style (id) ON DELETE RESTRICT,
    display_min double precision NOT NULL,
    display_max double precision NOT NULL,
    resampling_method text NOT NULL
        CHECK (resampling_method IN ('nearest', 'bilinear', 'average')),
    output_format text NOT NULL DEFAULT 'webp' CHECK (output_format IN ('webp', 'png')),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked', 'expired')),
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT layer_specification_range_ck CHECK (display_min < display_max),
    CONSTRAINT layer_specification_expiry_ck CHECK (
        expires_at IS NULL OR expires_at > created_at
    )
);

CREATE INDEX layer_specification_active_token_idx
    ON display.layer_specification (public_token)
    WHERE status = 'active';

GRANT SELECT ON display.palette, display.variable_style, display.layer_specification
    TO weather_api, weather_tiles, weather_readonly, weather_backup;
GRANT INSERT, UPDATE ON display.layer_specification TO weather_api;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA display TO weather_api;

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
