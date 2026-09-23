# Operations guide

This guide covers the initial single-server deployment. It supplements the
[implementation plan](implementation-plan.md); it does not replace host security,
off-site backup, monitoring, or restore procedures appropriate to the operator's
environment.

All commands below run from the repository root. Application database migrations
remain explicit operator actions. Starting or restarting Compose directly never
applies them; the repository's `run.sh` wrapper deliberately invokes the same
reviewed, checksum-verifying migration scripts before starting the application
containers.

## Zero-argument installation and startup

For a complete first installation:

```bash
./install.sh
./run.sh
```

`install.sh` checks Docker and Compose, generates non-placeholder secrets for a
fresh deployment, sets `.env` to owner-only permissions, prepares every storage
directory, checks disk capacity, pulls runtime images, and builds the custom
images. It does not start containers or apply migrations.

`run.sh` is also sufficient by itself. It performs the lightweight installation
checks, starts PostgreSQL and Redis first, applies and verifies every numbered
SQL migration, and then starts the complete application and observability
profile. It waits for container health and verifies both application APIs'
readiness before returning. Neither script accepts arguments.

Published ports are configured in `.env`. If a host port is already occupied,
change the corresponding `APP_PORT`, `HTTPS_PORT`, `AIRFLOW_PORT`,
`POSTGRES_HOST_PORT`, `PROMETHEUS_PORT`, or `GRAFANA_PORT` value before
starting; no container-internal URL changes are required. The successful
`run.sh` summary always prints the effective browser endpoints.

Existing secrets are never automatically rotated after the PostgreSQL data
directory is present. Database, Airflow Fernet, and service-secret rotation
requires a separate reviewed procedure so persisted credentials remain usable.

## Local-network access

The web gateway explicitly binds to `APP_BIND_ADDRESS=0.0.0.0` by default,
publishing redirect-only HTTP on `APP_PORT` and application HTTPS on `HTTPS_PORT`.
Set `CADDY_SITE_ADDRESS` to a single public DNS hostname, without a scheme, port
or extra HTTP site. The current installation uses `weatheratlas.ioresearch.ca`,
`APP_PORT=18080` and `HTTPS_PORT=8443`. Start Docker Desktop, then run `./run.sh`
from this repository
to build and start the app, database, cache, tile services, Airflow, the ECCC
subscriber, and monitoring services with health checks.

On both LAN and external devices, open
`https://weatheratlas.ioresearch.ca/forecast`. Old localhost/LAN HTTP links redirect
to this HTTPS hostname; they no longer serve forecast, map, API or tile data.
Keep NAT loopback working for LAN devices, or configure an equivalent local HTTPS
route. Simply pointing the hostname at a LAN address is not sufficient when the
host listens on 8443 rather than 443. Do not disable certificate verification or
the host firewall. See [HTTPS routing and renewal](https.md).

Only the web gateway is LAN-accessible. PostgreSQL, Airflow's administrative
UI, Grafana and Prometheus remain bound to loopback; Redis, backend APIs and
the tile services have no separate public ports. Map, forecast and API requests
share the gateway origin, so the frontend needs no hard-coded LAN address.
Internal Docker service links and loopback-only administrative interfaces retain
their existing transport; they are not public app endpoints. Recreate only the
gateway with `docker compose up -d --no-deps reverse-proxy` for HTTPS configuration
changes, preserving all collection jobs and application services.

## Persistent storage layout

Compose bind-mounts every mutable service store below
`WEATHERAPP_DATA_DIR`, which defaults to `./weatherapp_data` relative to the
repository root:

```text
weatherapp_data/
├── airflow/logs/
├── backups/postgres/
├── caddy/config/
├── caddy/data/
├── grafana/
├── postgres/
├── prometheus/
├── redis/
├── tile-cache/
└── weather/
    ├── cache/
    ├── derived/
    ├── processed/
    ├── quarantine/
    ├── raw/
    ├── staging/
    └── temporary/
```

The one-shot `storage-init` Compose service creates missing directories and
sets the service ownership required by Airflow, Nginx, Prometheus, and Grafana.
PostgreSQL, Redis, and Caddy complete their own internal initialization. It runs
before PostgreSQL and Redis on every `compose up`; it does not erase contents.

Set both paths before the first start when storage belongs on another
filesystem:

```dotenv
WEATHERAPP_DATA_DIR=/srv/weather-platform/weatherapp_data
WEATHER_DATA_DIR=/srv/weather-platform/weatherapp_data/weather
WEATHER_BACKUP_DIR=/srv/weather-platform/weatherapp_data/backups/postgres
```

On macOS, configure external or NAS-backed storage with its absolute
`/Volumes/<mount>/...` path rather than relying on a repository-relative
symlink. Docker Desktop can report the Mac system disk's free-space value for
bind mounts below `/Volumes` even though the files are written to the external
filesystem. `install.sh` remains the authoritative host-side capacity check;
the per-download guard is a smaller last-resort reserve for the container
runtime view.

`install.sh` rejects a `WEATHER_DATA_DIR` outside `WEATHERAPP_DATA_DIR`.
Changing the root later points Compose at a separate deployment and does not
move the old files.

Releases that predate this layout used Docker named volumes and a repository
`data/` directory. Those stores are intentionally neither deleted nor
automatically copied. For an established installation, stop writers, create and
verify database backups, copy each filesystem store to its matching subdirectory,
and verify ownership and restore readiness before starting the new layout.

## Safety model

The operations scripts are deliberately conservative:

- `check_disk_capacity.sh` is read-only and exits nonzero before a planned job
  would cross either capacity floor.
- `report_storage_maintenance.sh` has no deletion mode. Retention candidates are
  a report, not authorization to remove files or database records.
- All three Airflow maintenance DAGs are manual and bounded. Retention and
  temporary cleanup remain dry runs unless the DAG-run JSON contains the literal
  boolean `"execute": true`.
- `backup_postgres.sh` creates new files with owner-only permissions, validates
  them with `pg_restore --list`, and refuses to overwrite a matching name. It
  never prunes old backups.
- The systemd example stops containers without removing containers or
  bind-mounted host data.

The Airflow retention DAG implements the database-first state transition from
the implementation plan: preflight the exact registered path and checksum, mark
one row pending deletion, remove or confirm absence of that file, verify absence,
then mark it deleted. A failure after the first transition deliberately leaves
the row pending so the same bounded workflow can reconcile it on a later run.

## Storage capacity admission

Place `WEATHERAPP_DATA_DIR` on the intended data filesystem. The capacity check
measures the filesystem containing `WEATHER_DATA_DIR` (the
`weatherapp_data/weather` subtree by default) before enabling a product,
backfill, or unusually large model run:

```bash
./scripts/check_disk_capacity.sh
```

The defaults require at least 20 GiB and 10 percent free after the proposed job.
Pass a measured download plus transformation estimate with `--required-gib`:

```bash
./scripts/check_disk_capacity.sh \
  --required-gib 45 \
  --minimum-free-gib 30 \
  --minimum-free-percent 12
```

Exit status `0` means admit, `1` means capacity blocked, and `2` means the path or
arguments are invalid. An Airflow task should treat any nonzero status as a hard
stop before downloading. Defaults may be set locally without changing the
script:

```dotenv
WEATHER_MIN_FREE_GIB=30
WEATHER_MIN_FREE_PERCENT=12
```

Capacity planning must include simultaneous raw input, staging output, final COG,
and temporary GDAL files. Do not use only the final compressed object size.

## PostgreSQL backups

The backup script dumps both databases by default:

- `weather_app` through the read-only `weather_backup` role
- `weather_airflow` through its database-owner role

Required values already used by the development bootstrap are
`WEATHER_BACKUP_PASSWORD` and `AIRFLOW_DB_PASSWORD`. Production may instead set
`WEATHER_BACKUP_USER`, `AIRFLOW_BACKUP_USER`, and `AIRFLOW_BACKUP_PASSWORD` to
separately managed backup credentials.

Create a backup set:

```bash
./scripts/backup_postgres.sh
```

Back up only one database when troubleshooting:

```bash
./scripts/backup_postgres.sh --database app
./scripts/backup_postgres.sh --database airflow
```

Each dump uses PostgreSQL's custom format and has a sibling `.sha256` file. Files
are staged in the destination and published only after `pg_restore --list` can
read them. The script uses `umask 077`; keep the destination owned by the service
operator and inaccessible to untrusted users.

Example independent checks:

```bash
backup_dir=${WEATHER_BACKUP_DIR:-./weatherapp_data/backups/postgres}
(cd "$backup_dir" && \
  sha256sum --check weather_app_20260716T220000Z.dump.sha256)
docker compose exec -T postgres pg_restore --list \
  < "$backup_dir/weather_app_20260716T220000Z.dump" > /dev/null
```

On macOS, use `shasum -a 256 -c` instead of `sha256sum --check`.

The local backup directory is not a disaster-recovery target. Copy completed
backup sets to physically separate storage with Restic, Borg, or the operator's
equivalent. Back up reviewed migrations and configuration too, while handling
`.env` and other secrets separately. Never place plaintext production secrets in
the same broadly readable archive as application source.

### Restore drill

At least monthly:

1. Provision a disposable PostgreSQL/PostGIS instance with the same major
   version.
2. Create the required cluster roles and extensions using the external-cluster
   bootstrap procedure in [database/README.md](../database/README.md).
3. Verify the dump checksum and restore it with `pg_restore` into an empty
   database on that disposable instance.
4. Connect directly to the disposable target with `psql -X` and verify that
   `postgis` and `pgcrypto` are installed, `app.schema_migration` contains the
   expected filenames and checksums, and every application schema is present.
5. Confirm catalogue row counts and sample asset paths against the disposable
   target, then exercise at least one read through a service role.
6. Record the target identity, dump names, checksums, duration, result, and
   operator.
7. Destroy only the explicitly identified disposable instance after review.

`scripts/verify_database.sh` deliberately targets the repository's running
Compose `postgres` service and is not an alternate-target restore verifier. Do
not use it as evidence for a disposable restore, and do not test restoration by
overwriting either live database.

## Integrity and retention reporting

Run the filesystem report:

```bash
./scripts/report_storage_maintenance.sh
```

It reports counts and bytes for `raw`, `staging`, `temporary`, `quarantine`,
`processed`, `derived`, and `cache`. It reports age-based candidates for every
class except the size-managed cache, plus zero-byte files, incomplete
`.part`/`.tmp` files in published areas, and broken symlinks. Missing directories
are reported as empty because a newly installed system may not have created every
class yet.

List individual candidates and anomalies:

```bash
./scripts/report_storage_maintenance.sh --verbose
```

Compare catalogue paths and recorded sizes to disk using the read-only database
role:

```bash
./scripts/report_storage_maintenance.sh \
  --check-catalogue \
  --fail-on-integrity
```

Full checksum verification is I/O intensive and should run outside peak ingest
and tile-serving periods:

```bash
./scripts/report_storage_maintenance.sh \
  --verify-checksums \
  --fail-on-integrity
```

`--fail-on-integrity` is suitable for a monitoring job: it exits `1` when an
issue is found. Retention candidates alone do not make the command fail. Override
candidate ages only after measuring actual daily growth:

```bash
./scripts/report_storage_maintenance.sh \
  --raw-days 30 \
  --staging-days 2 \
  --temporary-days 1 \
  --quarantine-days 14 \
  --processed-days 180 \
  --derived-days 180
```

The tile cache remains size-based and is intentionally not included in age-based
candidate totals.

## Airflow maintenance DAGs

The protected Airflow environment exposes three manual DAGs. They have no
schedule, permit only one active run, reject unknown options, and cap `limit` at
1000 objects per run.

### Catalogue-backed retention

All configured ECCC products have `retain_forever: true`. Normal
data-collection DAGs never delete a prior cycle, and the age-based query excludes
their raw sources and processed assets. The manual DAG remains a bounded,
dry-run-first recovery mechanism for interrupted deletions and for any future
product that explicitly opts into age-based retention.

Preview up to 100 candidates without changing files or rows:

```bash
docker compose exec -T airflow-scheduler \
  airflow dags trigger weather_asset_retention \
  --conf '{"limit":100}'
```

The database query uses `retain_forever`, `raw_days`, and `processed_days` from
each product's reviewed `retention_config`. Pending deletions are selected first
so an interrupted legacy deletion remains recoverable. The total bound is shared
by processed assets and raw source objects.

After reviewing the dry-run XCom result and confirming backups/capacity policy,
execute the same bounded batch:

```bash
docker compose exec -T airflow-scheduler \
  airflow dags trigger weather_asset_retention \
  --conf '{"execute":true,"limit":100}'
```

Execution refuses absolute/traversing paths, unexpected storage classes,
symlinks in any path component, non-regular files, size mismatches, and checksum
mismatches. It never removes directories. Database rows are retained with
`deleted` status and audit events for both state transitions.

### Read-only integrity audit

Compare a bounded set of active catalogue paths and recorded sizes to disk:

```bash
docker compose exec -T airflow-scheduler \
  airflow dags trigger weather_integrity_audit \
  --conf '{"limit":500,"fail_on_issue":true}'
```

Add `"verify_checksums":true` outside peak processing periods. The result states
when the registered set exceeded the bound and the audit was truncated. This DAG
does not update catalogue status or repair files.

### Temporary-file cleanup

Preview old partial files:

```bash
docker compose exec -T airflow-scheduler \
  airflow dags trigger weather_cleanup_temporary_files \
  --conf '{"minimum_age_hours":48,"limit":100}'
```

After review, add `"execute":true`. Cleanup is restricted to regular `*.part`
and `*.tmp` files below `staging/` and `temporary/`; it does not follow symlinks
or touch similarly named files below raw or published storage classes.

## systemd startup example

The example unit is
[weather-platform.service.example](systemd/weather-platform.service.example).
It assumes:

- repository: `/srv/weather-platform/app`
- `.env`: `/srv/weather-platform/app/.env`
- service account: `weather`
- Docker CLI: `/usr/bin/docker`

Docker daemon access is effectively root-equivalent. Restrict membership in the
Docker group and do not reuse the `weather` account for interactive users.

Install after reviewing every path and account:

```bash
sudo install -m 0644 \
  docs/systemd/weather-platform.service.example \
  /etc/systemd/system/weather-platform.service
sudo systemctl daemon-reload
```

Before the first systemd start, initialize PostgreSQL, apply every migration, and
verify the database from the repository root:

```bash
docker compose up -d --wait postgres redis
make db-create
make db-verify
sudo systemctl enable --now weather-platform.service
sudo systemctl status weather-platform.service
```

The unit uses `docker compose up -d --wait` and then checks both application
readiness endpoints from inside their containers. Startup fails if `.env` is
missing, a container does not become healthy, or PostgreSQL/Redis/data-root
readiness fails.

For a deployment containing SQL changes, apply and verify migrations before
reloading the services:

```bash
make db-create
make db-verify
sudo systemctl reload weather-platform.service
```

Stop without deleting data:

```bash
sudo systemctl stop weather-platform.service
```

Container logs remain available through Compose:

```bash
docker compose logs --follow --tail=200
```

## Recommended schedule

| Operation | Initial cadence |
|---|---|
| Capacity admission | Before every run/backfill; also every 5 minutes in monitoring |
| PostgreSQL backup | Daily, plus before reviewed schema changes |
| Filesystem integrity/retention report | Daily |
| Catalogue size comparison | Daily |
| Full checksum verification | Weekly or monthly, capacity permitting |
| Off-host backup replication | Immediately after each local backup |
| Restore drill | Monthly |

Automated timers should capture stdout/stderr, alert on nonzero exits, prevent
overlapping runs, and set bounded runtime limits. Scheduling is left to the host
operator because backup destinations and monitoring integrations are deployment
specific.
