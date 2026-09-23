\set ON_ERROR_STOP on

BEGIN;

DO $roles$
DECLARE
    required_role text;
BEGIN
    FOREACH required_role IN ARRAY ARRAY[
        'weather_owner',
        'weather_migrator',
        'weather_api',
        'weather_tiles',
        'weather_ingest',
        'weather_readonly',
        'weather_backup'
    ]
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = required_role
        ) THEN
            RAISE EXCEPTION
                'Required role % is missing; run the administrator role bootstrap first',
                required_role;
        END IF;
    END LOOP;

    IF NOT pg_has_role('weather_migrator', 'weather_owner', 'MEMBER') THEN
        RAISE EXCEPTION
            'weather_migrator must be a member of weather_owner; run the administrator role bootstrap first';
    END IF;
END
$roles$;

REVOKE ALL ON DATABASE weather_app FROM PUBLIC;
GRANT CONNECT ON DATABASE weather_app TO weather_migrator;
GRANT CONNECT ON DATABASE weather_app TO weather_api;
GRANT CONNECT ON DATABASE weather_app TO weather_tiles;
GRANT CONNECT ON DATABASE weather_app TO weather_ingest;
GRANT CONNECT ON DATABASE weather_app TO weather_readonly;
GRANT CONNECT ON DATABASE weather_app TO weather_backup;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;

ALTER SCHEMA app OWNER TO weather_owner;
ALTER TABLE app.schema_migration OWNER TO weather_owner;

CREATE SCHEMA catalogue AUTHORIZATION weather_owner;
CREATE SCHEMA ingestion AUTHORIZATION weather_owner;
CREATE SCHEMA display AUTHORIZATION weather_owner;
CREATE SCHEMA audit AUTHORIZATION weather_owner;

REVOKE ALL ON SCHEMA app, catalogue, ingestion, display, audit FROM PUBLIC;

GRANT USAGE ON SCHEMA catalogue, display TO weather_api;
GRANT USAGE ON SCHEMA catalogue, display TO weather_tiles;
GRANT USAGE ON SCHEMA catalogue, ingestion, audit TO weather_ingest;
GRANT USAGE ON SCHEMA app, catalogue, ingestion, display, audit TO weather_readonly;
GRANT USAGE ON SCHEMA app, catalogue, ingestion, display, audit TO weather_backup;

SET ROLE weather_owner;

ALTER DEFAULT PRIVILEGES IN SCHEMA app, catalogue, ingestion, display, audit
    REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA app, catalogue, ingestion, display, audit
    REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA app, catalogue, ingestion, display, audit
    REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

ALTER DEFAULT PRIVILEGES IN SCHEMA app, catalogue, ingestion, display, audit
    GRANT SELECT ON TABLES TO weather_readonly, weather_backup;
ALTER DEFAULT PRIVILEGES IN SCHEMA app, catalogue, ingestion, display, audit
    GRANT SELECT ON SEQUENCES TO weather_readonly, weather_backup;

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
