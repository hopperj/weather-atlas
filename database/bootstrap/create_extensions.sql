\set ON_ERROR_STOP on

-- Run this file while connected to weather_app as a PostgreSQL administrator.
-- PostGIS installation is privileged; weather_migrator intentionally cannot
-- install extensions itself. Migration 0001 verifies/records this setup with
-- CREATE EXTENSION IF NOT EXISTS after the administrator bootstrap has run.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
