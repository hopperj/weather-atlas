# Sparky migration (2026-09-22)

## 2026-09-24 collection handover in progress

The user authorized the final sync, moving collection to sparky, a 200 GiB
capacity floor with no percentage requirement, and collection autostart.
Public routing is deliberately unchanged.

- Source collection is stopped and all source DAGs are paused. Both source
  simulation-submission flags are disabled; its API continues serving reads.
  The source `.env` has `WEATHER_STARTUP_HOLD=collection-moved-to-sparky`.
- Fresh source snapshots were taken at 13:41:00 UTC (`weather_app`) and
  13:41:08 UTC (`weather_airflow`) after writers stopped. Both were restored
  into fresh candidates on sparky; all 102 table counts, ownership, database
  permissions and settings matched. All 29 schema checks passed after promotion.
- Previous target databases are retained as
  `weather_app_before_20260924t133800z` and
  `weather_airflow_before_20260924t133800z`.
- Source archive verification passed for 244,567 assets, 243,592 source records,
  6,602 imagery frames and 3 legends, including 50 sampled hashes.
- The full weather comparison identified 70,804 files (39.26 GiB) and 2,987
  directories to update/add. The non-deleting transfer is in progress; replaced
  weather files are backed up under the private migration directory. Serial and
  four-way transfers were deliberately interrupted for throughput improvements;
  their exit-20 records are expected. The active transfer is `queued_sync.py`,
  with 743 disjoint batches and eight workers. Its `queued-sync/completed.jsonl`
  journals successful batches for safe resume; `queued-sync.log` records overall
  completion. Already copied files are skipped. NFS writes are only a few MB/s,
  with no retransmissions or access errors observed.
- The throughput investigation found sparky's `enP7s7` Ethernet link negotiated
  at only 100 Mb/s, full duplex, despite both ends advertising at least 1 Gb/s.
  No interface errors/drops were observed. This limits the transfer independently
  of NAS workload; the cable/port/link negotiation needs checking. Do not force
  link settings or disconnect networking during the copy. The user reports no
  concurrent NAS transfer, deletion, scrub or rebuild.
  Rechecked the exact interface after the user's question: `enP7s7` holds
  `10.0.0.243`, and `ip route get 10.0.0.184` uses it for the NAS. Both ethtool
  and `/sys/class/net/enP7s7/speed` report 100 Mb/s. The adapter advertises
  2.5/5/10 Gb/s capability, but the link partner advertises only up to 1 Gb/s.
  Its MAC address is `4c:bb:47:2e:88:a8`; no network settings were changed.
- The transfer tool creates some new directories as 2755 rather than 2775.
  Run the private `check_transfer_permissions.py` after the copy, then its
  `--verify` mode, before starting collection. It is scoped to transferred paths
  and their parents, journals corrections, and preserves owners and contents.
- Sparky still has only PostgreSQL running. Its DAGs remain paused and its
  startup hold remains set until destination file verification passes.
- The capacity check now defaults to 200 GiB and a disabled percentage floor;
  sparky's private configuration explicitly uses those settings and passes.
- The root-only boot installer is prepared at `scripts/install_sparky_boot.sh`.
  It has not yet been confirmed installed. It adds the exact NAS dependency
  and mount checks to Docker, preserving other service overrides. No reboot or
  Docker restart is performed by that installer.
- The destination subscriber's private `ECCC_SUBSCRIBER_HOSTNAME` retains the
  outgoing container hostname, preserving the existing broker queue identity.
  Subscriber credential-file hashes match; credential values were not printed.
- The focused storage/startup/subscriber/imagery regression suite passes 61 tests.

Private target migration directory:
`/home/hopperj/weather-atlas/postgres_data/backups/cutover-20260924.f6cH7D`.
Local working records: `/tmp/weather-atlas-final-cutover.EErePI`.
The 22 previously enabled source DAGs are recorded in `airflow-enabled-dags.txt`;
resume only that set. The imported imagery task was `up_for_retry` because the
source Docker environment reported low free space. No running/queued source
tasks remained when the snapshots were taken.

Historical source Airflow logs are retained separately in
`/Volumes/BigMrStorage/weatherapp_data/backups/collector-cutover.pxs5yr` and in
`airflow-logs.tar.gz` under the private target migration directory. The transfer
checksum and gzip integrity check passed. This preserves about 1.16 million log
files (5.0 GiB uncompressed) without replacing fresh target task logs. Older
logs are archived, not extracted into the active Airflow log directory.

## 2026-09-24 shared-write inheritance repaired

The NAS permission issue is now corrected for shared weather payloads. A scoped,
owner-only repair ran as `hopperj` (UID 1000), without sudo or privileged containers:

- Added shared GID 100 and setgid/group read-write-traverse permissions to 83,375
  directories: the `data` mount root and directories below `data/weather`.
- Corrected group/read-write permissions on 14,312 regular weather files,
  including newly transferred files. File owners, payload bytes and existing
  other-user permission bits were preserved. Symlinks were not followed.
- Left `data/services`, TLS keys, local PostgreSQL, and service ownership alone.
- Rebuilt the subscriber with a 0002 umask and explicit 0664/0775 delivery modes,
  disabling upstream mode copying. Rebuilt the Airflow image after fixing the
  imagery atomic writer so published files do not retain temporary-file mode 0600.

Fresh nested folders/files created by the actual subscriber, Airflow, and host
identities now inherit GID 100 with modes 2775/0664. All three identities passed
cross-user read/append/create/delete tests, and Airflow passed rename tests for
each creator. The actual imagery writer published a shared 0664 file. Both live
API containers could read these new files through their intentionally read-only
mounts. All scratch test files were removed. Readiness remains healthy.

The final full-tree permission scan passed: 83,375 directories and 1,161,043
regular files checked, with no remaining shared-group/mode corrections needed.
The scan skipped 729 symlink entries without following them.

The before-permission manifest, applied-change journal and one-time repair helper
are on sparky's local SSD at
`postgres_data/backups/nfs-permissions-20260924.ykTVPd`.
Previous images are retained with the `before-permissions-20260924` tag for
`weather-platform-eccc-subscriber` and `weather-platform-airflow`.
Code regression checks: 58 tests passed; the subscriber's real configuration
parser also confirmed the intended permission defaults without connecting to
the feed. Local verification logs are in `/tmp/weatheratlas-nfs-repair.FnAU5Y`.

This is **not** a production cutover: collection remains stopped, the startup hold
is unchanged, and public traffic still uses the original server. The missing-file
copy log reports all 14,311 files transferred; data-integrity/freshness review,
final synchronized database/file refresh, NAS capacity and routing/mount-order
checks remain separate cutover work. Do not clear the hold based only on permissions.

## 2026-09-23 API testing enabled; production cutover still pending

Sparky now runs PostgreSQL, Redis, the API, tile API/cache, frontend and HTTPS
gateway. Airflow and the subscriber are **not running**; all 23 target DAGs are
paused. Simulation and validation-run writes are disabled in sparky's private
configuration. The full-stack startup hold remains in place. The old production
server continues serving public traffic and collecting data; no router or DNS
changes were made.

Ordinary service state was copied to `data/services`, using each service's real
UID and shared GID 100, without chowning NAS files. `WEATHER_MANAGE_SERVICE_PERMISSIONS=false`
now prevents the initializer from changing NAS-managed service ownership/modes.
PostgreSQL remains in `postgres_data`; monitoring state uses
`postgres_data/monitoring`. Original service files remain in
`postgres_data/pending-service-migration` for rollback. There is no
`weatherapp_data` folder on sparky.

Verification passed for API/Redis/data readiness, the frontend, all eight model
products, Halifax daily and hourly endpoint responses, a numeric GDPS point
sample, and actual 256x256 model/radar/infrared/optical PNG tiles. TLS verification
was enabled, using the existing certificate hostname directed to sparky:

```bash
curl --resolve weatheratlas.ioresearch.ca:8443:10.0.0.243 \
  https://weatheratlas.ioresearch.ca:8443/health/ready
```

HTTP port 18080 still redirects to the public HTTPS hostname, which currently
reaches the original server. `https://sparky.iolan:8443` is not a valid test URL
for the public-name certificate; do not disable certificate verification.
Imagery is historical/stale in this standby snapshot, not a live radar feed.
The hourly endpoint returns 72 time slots but currently reports only one
available hour and zero complete hours because newer model files are still
missing. This is an API/renderer smoke test, **not** a complete forecast-data
readiness result. Re-test hourly coverage after the file sync.

The read-only archive audit ran as API UID 10001/GID 100 and checked 481,596
registered records. It found 14,311 missing files (7,074 assets, 7,074 raw source
files and 163 imagery frames), with no unreadable, size-mismatch or sampled-hash
errors among the existing files. All missing source files were located on the
original server: 36.80 GiB total. A non-deleting, `--ignore-existing` sync of only
that validated file list is in progress. Do not mark the archive verified until
the transfer finishes and the audit is repeated. The latest regional-forecast
JSON was also copied separately after preserving the prior version; Halifax now
reports the September 23 14:00 UTC bulletin rather than September 22.

Audit records and the previous regional forecast are under
`postgres_data/backups/file-audit.zHNWjK` on sparky. The local transfer list,
progress log and QA results are in `/tmp/weather-atlas-api-start.GIbRrV` on the
source Mac. The log is `missing-files-sync.log`; the source list is
`missing-files.txt`. The transfer replaces no existing files and deletes none.

Remaining blockers at this checkpoint before production collection/cutover
(permissions were subsequently repaired above):

- Actual write probes now succeed for hopperj at the NAS root and for Airflow's
  UID 1000 in forecast history and the inbox. Subscriber UID 50000 with GID 100
  can write at the inbox root but still receives **Permission denied** inside
  `data/weather/amqp/inbox/20260923`. Grant the intended `users` group read/write
  and directory traversal throughout the NAS inbox tree, including inheritance.
  No weather-folder permission/ownership policy was changed by this work.
- NAS free space remains below the existing 10% ingestion floor. The threshold
  was not lowered; the fixed 36.80 GiB migration copy is not new ETL collection.
- Finish the file transfer/audit, reconcile remaining non-catalogued operational
  snapshots/history, then coordinate a final database/file sync with production
  writers stopped. Resolve gateway/router routing before switching public traffic.

The updated storage/operations regression suite passed 41 tests. Reboot/mount
ordering still needs final cutover review; do not remove the startup hold yet.

## 2026-09-23 database-only refresh completed

Both canonical databases on sparky were refreshed from production using
read-only exported snapshots: `weather_app` at **17:25:15 UTC** and
`weather_airflow` at **17:25:22 UTC** (14:25 Halifax time). Production remained
online and collecting throughout. This is a one-time point-in-time refresh,
not continuous replication or a completed application/data cutover.

Custom-format dumps were checksum-verified after transfer, restored into fresh
candidate databases, and validated before promotion. All **102 table counts**
(31 weather, 71 Airflow) match counts taken from the same exported snapshots.
Database ownership, locale, grants and per-role database settings also match.
Both candidates were renamed into place in one transaction; all 29 migration
checks and authenticated API/Airflow database reads passed afterward.

- Current catalogue: 237,983 assets, 237,120 source records, 6,602 imagery frames,
  and 43,903 forecast revisions.
- Current Airflow history: 857,664 task instances and 3,937,240 XCom records.
- All 23 target DAGs are paused. The snapshot's 22 enabled production DAG IDs
  are retained in its private manifest for eventual cutover. One imported task
  was `up_for_retry`; review that state before starting the target scheduler.
- Previous canonical databases are retained as
  `weather_app_before_20260923t172335z` and
  `weather_airflow_before_20260923t172335z`. The older September 22 staging
  databases were also left untouched. No databases were dropped.
- Verified dumps, manifests, restore logs, table-count checks and promotion
  records are in the private local directory
  `/home/hopperj/weather-atlas/postgres_data/backups/sync-20260923T172335Z`.

At completion of that database-only refresh, PostgreSQL used
`/home/hopperj/weather-atlas/postgres_data` and only that service was running on
sparky (the API-testing section above supersedes this status). The startup hold
was unchanged. No NAS weather files
or service files were copied in this refresh, no NAS permissions were changed,
and no public traffic was switched. Production can create new records after
these snapshots; a final coordinated sync is still required before cutover.

## 2026-09-23 local database directory

PostgreSQL's independent host path is now
`/home/hopperj/weather-atlas/postgres_data` (`POSTGRES_DATA_DIR`). The existing
standby cluster is relocated while stopped, retaining both canonical databases
and the September 22 staging databases. This is a local-directory move, not a
new production snapshot or a public cutover. The production source is unchanged.

Verification after the move: PostgreSQL is healthy with the same cluster system
identifier and all four restored database names. Canonical counts still match
236,525 assets, 235,662 source records, 6,602 imagery frames, 43,662 forecast
revisions and 853,149 Airflow task instances. All 23 imported DAGs remain paused.
Both September 22 staging database counts also match. All 29 application
migration checks and 36 focused storage/operations tests passed. The old stopped
service containers were removed without deleting their bind-mounted files, so
they cannot restart with obsolete `weatherapp_data` paths. Only PostgreSQL is
running on sparky; production's public readiness check remains healthy.

The remaining former `weatherapp_data` contents are preserved under
`postgres_data/pending-service-migration`. There is no longer a `weatherapp_data`
directory in sparky's checkout. The planned destination for ordinary service
files is `data/services`, but the NAS mount root currently has mode 0755 owned by
UID 1026 and is not writable by hopperj. Do not bypass that permission boundary.
Keep the startup hold and move those files only after NAS permissions are ready.
The latest capacity check reports about 3,576 GiB free (5.41%), still below the
existing 10% floor; no capacity policy was changed.

Before changing the service root to the NAS, adapt the initializer to leave
NAS-managed service permissions alone and verify access as the actual service
UIDs. Keep monitoring databases on the local SSD alongside PostgreSQL:
[Prometheus explicitly does not support NFS](https://prometheus.io/docs/prometheus/latest/storage/).
Do not start the full stack just to verify a database-directory move.

## 2026-09-23 cutover attempt: blocked by NAS permissions

The old deployment has been resumed and remains the production server. Its
original private configuration and 22 previously enabled DAGs were restored.
Public DNS, forwarding and proxy routing were not changed. Sparky's application
and Airflow services are stopped; only its local PostgreSQL remains running.
Its startup hold is `NAS-subfolder-permissions-and-final-cutover-pending`.

Completed during this attempt:

- Fresh, checksum-verified database backups and restores, stored privately under
  `postgres_data/pending-service-migration/migration-20260923/` on sparky (relocated
  from the former service root). The prior standby databases were
  preserved as `weather_app_staging_20260922` and
  `weather_airflow_staging_20260922` rather than overwritten.
- All 29 SQL migration checks passed. Source/restored row counts matched:
  236,525 assets, 235,662 source records, 6,602 imagery frames and 43,662 forecast
  revisions.
- A read-only source archive check verified 236,525 asset paths, 235,550 downloaded
  source paths, 6,602 imagery paths and 3 legends, plus 48 sampled SHA-256 hashes,
  with no integrity issues. Destination verification remains pending.
- HTTPS certificate, API health, forecast/catalogue reads, container startup and
  Airflow health passed on sparky. Its collection DAGs remained paused and no
  target ETL tasks ran.
- The 13 ignored FLEXPART ancillary NetCDF inputs were copied separately and the
  target Airflow image rebuilt to include them.

The final non-deleting rsync was stopped after permission errors. Some newer
files were copied successfully; none were deleted. Many nested weather folders
have mode `0755`, NAS owner UID `1026`, and group `100` (`users`). Sparky's user is
UID `1000` with supplementary group `100`; the containers also have that shared
group. Top-level write access does not grant access inside these nested folders.

The NAS administrator must grant the intended weather service group read/write
access throughout **only** `/volume1/data/weather-atlas-data/weather`, including
directory traversal and inheritance. Setgid directories can keep newly created
content in group 100. Do not solve this by changing ownership of the whole share,
using world-writable permissions, impersonating the NAS owner, or disabling NFS
security. The NAS-side permission policy has deliberately not been changed.

After permissions are corrected, test existing nested paths as both the syncing
user and actual container users, then repeat the pause/final sync/fresh database
restore sequence. The September 23 standby snapshot is now historical because
the production collectors were resumed. No final public cutover has occurred.

## Current deployment layout

Repository on sparky: `/home/hopperj/weather-atlas`.

The mounted folder is named **`data`** and PostgreSQL's local directory is
**`postgres_data`**. Do not point PostgreSQL at `data/postgres`. The checked-in
[.env.sparky.example](../.env.sparky.example) records this split without including
private credentials. Docker's internal
weather path remains `/srv/weather-platform/data`; that stable container path
does not need to change when a host mount is renamed.

- Local PostgreSQL: `/home/hopperj/weather-atlas/postgres_data`.
- Local monitoring databases: `/home/hopperj/weather-atlas/postgres_data/monitoring`.
- Active ordinary service state: `/home/hopperj/weather-atlas/data/services`.
- Preserved service-state rollback copies:
  `/home/hopperj/weather-atlas/postgres_data/pending-service-migration`.
- NAS mount: `/home/hopperj/weather-atlas/data`, from
  `databanks.iolan:/volume1/data/weather-atlas-data`.
- Weather payloads: `/home/hopperj/weather-atlas/data/weather`.
- Migration backups: `postgres_data/pending-service-migration/migration-20260922/`
  and `migration-20260923/` on sparky (private).
- Runtime `.env` is private, ignored by Git, and retains the source passwords,
  Airflow Fernet key, JWT secret and layer-signing secret. Do not replace it with
  `.env.example` or regenerate credentials during migration.

The `postgres`, Redis, monitoring and other service directories copied to the NAS
are **not** the active service state on sparky. In particular, do not start
PostgreSQL using the copied NAS `postgres` directory. The migration uses verified
custom-format logical dumps of `weather_app` and `weather_airflow` instead.

The existing source deployment remains running. The restored databases are a
point-in-time **staging snapshot**, not a completed production cutover. Public DNS
and forwarding have not been changed. Sparky's API/map stack is up for testing,
with collection stopped and simulation writes disabled. PostgreSQL is bound to
loopback, not exposed on the LAN.

September 22 snapshot checks (superseded by the attempt above): both dump SHA-256
checksums and restores passed; all 29 application
migration checksums and the PostGIS/pgcrypto extensions verified. The restored
catalogue contains 230,909 assets, 6,450 imagery frames and 42,289 forecast
revisions. The copied Airflow schedules are paused on sparky as an additional
standby safeguard; the source schedules are unchanged. Their originally enabled
IDs are retained in the private migration backup directory.

## Installation while the NAS transfer continues

After the migration checks pass, run on sparky:

```bash
cd /home/hopperj/weather-atlas
./install.sh
```

This pulls/builds the remaining containers. It does not start the application or
ETL. It preserves the existing secrets and, with this deployment's
`WEATHER_MANAGE_DATA_PERMISSIONS=false`, does not create or change NAS weather
directories. The NAS mount/source are checked before creating local state.

`WEATHER_STARTUP_HOLD=NAS-subfolder-permissions-and-final-cutover-pending` deliberately
blocks `./run.sh`. Do not bypass that guard with `docker compose up`; Compose
itself does not enforce this host-script setting. The installer is safe to run
while the hold is present and reports the hold after a successful build.

## NFS permissions

The original transfer used NAS UID 1026. The NAS administrator subsequently
made the shared weather tree owned by sparky's UID 1000; the September 24 repair
preserves that owner and enforces shared group 100 and setgid directories. The
weather-reading/writing containers receive supplementary group 100 through
`WEATHER_DATA_GID`. Airflow runs as local UID 1000; the subscriber retains the
UID 50000 required by its image and private feed configuration. API and tile
services remain unprivileged UID 10001.

The storage initializer manages local service permissions only for this NAS
deployment. It does not recursively chown or chmod transferred files. Verify
representative files and new ETL output are readable by both API and tile service
users before enabling collection. The one-time, explicitly authorized September
24 repair is recorded above; the initializer still leaves NAS-managed state alone.
Do not apply recursive ownership changes or permissive weather-file modes to
private service state. Check new-file inheritance, not just existing-file access.

The NAS had about 5.2 TiB free (8.1%) at preparation time. The existing capacity
check warns because the configured floor is 10%. No threshold was lowered and no
data was deleted. Review capacity/reservation before resuming ingestion.

## Required final cutover

1. Finish the bulk weather-file transfer; verify file counts, sizes and sample
   checksums against the catalogue. A directory existing is not proof that its
   contents are fully transferred.
2. Coordinate a short collection pause on the old deployment. Let in-flight ETL
   work finish, then stop its schedulers, processors, subscriber and any other
   writers. Keep serving the old API while reconciling the final files.
3. Make a final non-deleting weather-file sync and fresh database dumps with
   writers stopped. Verify the dump checksums. The restricted `weather_backup`
   role was missing a sequence permission during preparation; the migration
   snapshot used the existing `weather_admin` account without granting new
   privileges on the source.
4. With sparky's application and ETL still stopped, restore the final databases
   into an explicitly identified fresh local cluster/database. Preserve the
   staging snapshot until the final restore is verified; never restore over the
   live source. Verify migration checksums with `./scripts/verify_database.sh`,
   catalogue row counts, registered file paths, forecasts, imagery and tiles.
5. Review any imported Airflow running/queued work and enable only the intended
   collection DAGs. Do not run two independent catalogues writing the same NAS
   archive. Retain the old deployment as the rollback source.
6. Clear the startup hold only after those checks, run `./run.sh`, and test the
   new API/UI before changing public traffic. The configured hostname remains
   `weatheratlas.ioresearch.ca`, HTTP redirect port 18080 and HTTPS port 8443;
   routing/certificate renewal must reach sparky at cutover.

TLS state is preserved in `postgres_data/pending-service-migration/caddy` until
the NAS service-directory move is verified.
Redis/tile caches can rebuild. Historical Airflow logs and monitoring files in
the NAS copy are retained but are not used as active writable service state.

Do not install the generic systemd example unchanged for this setup: it invokes
Compose directly. A future service unit must depend on the NAS mount
(`RequiresMountsFor=/home/hopperj/weather-atlas/data`) and retain the startup hold
and mount checks. Docker restart policies alone do not provide that mount-order
guarantee; configure reboot behavior as part of cutover, not during the transfer.
