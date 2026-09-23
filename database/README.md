# Application database

`weather_app` is managed with reviewed, immutable SQL files. Runtime services do
not create or migrate tables, and no ORM or query builder is used.

## Bootstrap versus migrations

PostgreSQL role and extension creation are privileged bootstrap operations. The
normal migration account, `weather_migrator`, intentionally has neither
`CREATEROLE` nor superuser privileges.

On a new `weatherapp_data/postgres` bind-mounted store,
`docker/postgres/init-databases.sh` performs this order:

1. create `weather_migrator` and the `weather_app` database;
2. install PostGIS and `pgcrypto` as the PostgreSQL administrator;
3. create the non-login owner and least-privilege service roles;
4. grant `weather_migrator` membership in `weather_owner`.

For an existing or externally managed PostgreSQL cluster, an administrator must
perform the equivalent setup before application migrations:

1. create `weather_migrator` and `weather_app` owned by that role;
2. while connected to `weather_app`, apply
   `database/bootstrap/create_extensions.sql`;
3. while still connected as an administrator, apply
   `database/bootstrap/create_application_roles.sql`, supplying distinct role
   password variables through the operator's secret-management process.

The role bootstrap accepts these optional `psql` variables:

```text
migrator_password
api_password
tiles_password
ingest_password
readonly_password
backup_password
```

An omitted password leaves that login unusable for password authentication. Do
not put production passwords into migrations, the repository, or shell history.

## Migrations

Numbered files under `database/migrations/` are applied in lexical order. Every
file is transactional and records its filename and SHA-256 in
`app.schema_migration`.

Use:

```bash
make db-create
make db-verify
```

Or apply one reviewed file explicitly:

```bash
./scripts/apply_migration.sh database/migrations/0003_create_catalogue.sql
```

Applied migrations are immutable. The migration runner rejects a reused filename
with a changed checksum and treats an identical migration as a successful no-op
when applying the directory.

## Schemas and roles

The non-login `weather_owner` role owns every application object.

| Schema | Purpose |
|---|---|
| `app` | Migration/application metadata |
| `catalogue` | Products, grids, variables, times, runs, and processed assets |
| `ingestion` | Remote objects, attempts, and quality checks |
| `display` | Palettes, styles, and persistent layer specifications |
| `audit` | Administrative and ingestion audit events |

| Role | Intended access |
|---|---|
| `weather_migrator` | Set role to `weather_owner` and apply reviewed migrations |
| `weather_api` | Read public catalogue/display data; create layer specifications |
| `weather_tiles` | Read only catalogue/display data required for rendering |
| `weather_ingest` | Read static catalogue and write runs, times, assets, and ingest state |
| `weather_readonly` | Read all application schemas for troubleshooting |
| `weather_backup` | Read all application schemas for logical backup |

`PUBLIC` has no application-schema access and cannot create objects in the
`public` schema. Default privileges are defined for objects created by
`weather_owner`; migrations also grant table-specific write access explicitly.

## SQL files in Python

Runtime SQL lives in `database/queries/**/*.sql`. `weather_common.db.SqlFileLoader`
rejects absolute paths, traversal, missing files, and non-SQL suffixes.
`weather_common.db.Database` provides an async psycopg pool with explicit
transaction scopes. Values must always use psycopg parameter binding.

The database stores only metadata for raw and processed data. Raw GRIB objects
are represented by `ingestion.source_object`; map-ready COGs and derived outputs
are represented by `catalogue.asset`. Raster bytes remain on the configured data
filesystem.

## Configured weather catalogue

Migration `0008_catalogue_configured_weather_fields.sql` is the reviewed SQL
projection of the current model and variable YAML files. It registers:

| Product | Domain | Configured fields | Enabled for download/process/display |
|---|---|---:|---:|
| HRDPS | `continental` | 10 | 10 |
| RAQDPS | `north_america` | 5 | 5 |
| RDPS | `north_america` | 10 | 10 |
| GDPS | `global` | 12 | 12 |

Every product-field row retains its source producer, parameter, source level,
source and canonical units, named conversion, output type, nodata value,
resampling method, style code, and availability window. The migration does not
turn on a field that the YAML keeps disabled. Enabling another field therefore
requires a reviewed configuration change and a new SQL migration after its
source semantics and processing path have been verified. Migrations 0017 and
0018 activate all currently configured deterministic forecast fields.

Each configured field has a field-specific `default` style. Pollutant palettes
are neutral visualization defaults and deliberately do not claim to implement
health or regulatory thresholds.

Migration `0026_add_seven_day_gdps_overlays.sql` extends GDPS with direct
10-metre wind speed and 3-hour precipitation accumulation, gives the GDPS
1-hour and 3-hour precipitation fields unambiguous display names, and registers
field-specific wind and precipitation styles. The configured availability
windows follow the live ECCC publication inventory: wind speed through forecast
hour 240, 1-hour precipitation through hour 144, and 3-hour precipitation
through hour 168.

Domain footprints remain null until an authoritative WGS84 bound is read from a
processed COG. Grid names, nominal resolutions, and current documented raster
dimensions are recorded for validation; the application must use an asset's
bounds when resolving a rendered layer.

## Precipitation-analysis catalogue and time constraints

Migration `0009_register_precipitation_analyses.sql` registers independent HRDPA
and RDPA domains plus preliminary/final 6-hour and 24-hour precipitation fields.
All eight source mappings are downloadable for inventory purposes, but none is
processing- or display-enabled until a real payload proves message/band, unit,
nodata, timing, grid, and pixel semantics. Each row records the explicit
activation gate and intended source band in metadata.

Preliminary and final files use the same parameter, level type, and level value.
The migration therefore promotes `source_producer` to a required relational
column and includes it in `product_field_source_uk`; source identity no longer
depends on JSON metadata and the two revisions cannot collide.

`catalogue.enforce_product_time_semantics()` protects the shared product-time
table:

- forecast rows require a non-null `forecast_hour`;
- analysis rows require `forecast_hour` to be null;
- analysis rows cannot use `time_kind = 'instant'`;
- the existing interval check requires non-instant `valid_time` to equal
  `interval_end` and requires both interval bounds.

Application migrations remain the only place schema constraints are changed;
runtime ingestion binds values through the reviewed
`ingestion/upsert_product_time.sql` statement.

## Backup role

`weather_backup` is read-only. It has schema usage and `SELECT` on application
tables and sequences, including `app.schema_migration`, so `pg_dump` can lock
and read every application object. Default privileges retain that access for
future objects created by `weather_owner`; the role receives no data-mutation,
object-creation, or role-management privilege.
