# What belongs in the repository

The repository contains the code and configuration needed to build and operate
Weather Atlas, not its live weather archive or a backup of the development machine.
The root `.gitignore` implements this policy. Ignoring a file does not delete it.

## Keep in Git

- Python API, tile service, ETL and Airflow source; frontend source and public assets.
- Tests, small input fixtures, and scientific regression scripts/case definitions.
- Database migrations, bootstrap SQL and query files. Do not ignore `*.sql`.
- Dockerfiles, Compose configuration, installation/maintenance scripts, Makefiles,
  model configuration, and observability configuration.
- `pyproject.toml`, `uv.lock`, `frontend/package.json` and
  `frontend/package-lock.json`. Lockfiles make dependency installation reproducible.
- Sanitized `.env.example` / `.env.sample` files, including environment-specific
  examples. Real environment files and backup copies remain private.
- Documentation, app assets, provenance records and upstream licenses.
- Extracted FLEXPART and CFFEPS source, including local modifications. Their builds
  use source files, not the downloaded release tarballs or local executables.

`docker/sarracenia/credentials.conf` currently contains only ECCC's public anonymous
connection details and is copied by its Dockerfile. It remains trackable. Do not
replace these with private credentials in a commit; use a separate ignored secret
and an appropriate runtime configuration if private credentials are ever needed.

## Keep outside Git

- `data`, `weatherapp_data` and `weather-atlas-data`, whether directories, mount
  points or symlinks. This includes live weather data, database/container storage,
  downloaded imagery, tiles, and runtime caches beneath those locations.
- Local secrets, private keys, `.env` variants/backups, logs, database files/dumps,
  virtual environments, installed dependencies, compiled binaries, build bundles,
  test reports, editor backups and caches.
- Generated FLEXPART regression baselines, candidates, work directories and
  benchmarks. Keep the existing baseline reports and scripts in Git; preserve the
  actual reference runs in external storage when needed for scientific comparison.
  They cannot be assumed to exist in a fresh clone or replaced with new-code output
  when comparing changes against the original reference.
- The large monthly OH/photolysis NetCDF inputs in `flexpart/options/oh_fields`.
  Chemistry runs need these ancillary data restored separately from the matching
  upstream FLEXPART release or the existing data archive. Small bundled test inputs
  elsewhere are not excluded by a global NetCDF/GRIB rule.
- Downloaded FLEXPART/CFFEPS release tarballs and the separate PDF paper/manual
  collections in `flexpart/docs` and `hysplit/docs`. Their reading indexes and
  provenance remain in Git; local PDF links need the reference library restored.
- `hysplit/code`: standalone research checkouts with their own Git metadata, not
  dependencies of the current app. Repository URLs and snapshot commits are recorded
  in `hysplit/README.md`. If these become required, integrate them deliberately as
  dependencies or properly configured submodules rather than accidental Git links.
- Gated HYSPLIT source and model packages in `hysplit/model/source` and
  `hysplit/model/distributions`; retain `hysplit/model/SOURCE_ACCESS.md`.

The rules intentionally do not exclude all JSON, CSV, SQL, images, PDFs or nested
`data` directories: some of these are essential configuration, documentation,
assets or fixtures. Keep future bulk downloads under the ignored storage roots.

## Before the first commit

Run these from the actual Git checkout:

```bash
git status --short
git check-ignore -v data weatherapp_data .env .env~ frontend/node_modules
git add --dry-run .
```

Review files before staging. `.gitignore` is not a secret scanner and cannot catch
credentials embedded in arbitrary source/config files. Also check
`git ls-files -ci --exclude-standard` for files already tracked despite the rules.
If any appear, remove only the reviewed paths from Git's index while retaining the
local files; an ignore rule alone does not untrack files or erase earlier commits.

Recreate runtime storage with the project's setup scripts and restore any required
external research datasets separately. Never commit a mounted NFS data tree.
