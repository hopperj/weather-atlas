from __future__ import annotations

import hashlib
import os
import shutil
import stat
import subprocess
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
SCRIPTS = PROJECT_ROOT / "scripts"


def _run(
    script_name: str,
    *arguments: str,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPTS / script_name), *arguments],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def _environment_with_bin(fake_bin: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
    return environment


def test_disk_capacity_admits_and_blocks_without_writing(tmp_path: Path) -> None:
    data_root = tmp_path / "weather-data"
    fake_bin = tmp_path / "bin"
    data_root.mkdir()
    fake_bin.mkdir()
    fake_df = fake_bin / "df"
    fake_df.write_text(
        "#!/usr/bin/env bash\n"
        "echo 'Filesystem 1024-blocks Used Available Capacity Mounted on'\n"
        "echo '/dev/test 104857600 52428800 52428800 50% /weather'\n"
    )
    fake_df.chmod(0o755)
    environment = _environment_with_bin(fake_bin)

    admitted = _run(
        "check_disk_capacity.sh",
        "--data-root",
        str(data_root),
        "--minimum-free-gib",
        "10",
        "--minimum-free-percent",
        "10",
        "--required-gib",
        "5",
        environment=environment,
    )
    blocked = _run(
        "check_disk_capacity.sh",
        "--data-root",
        str(data_root),
        "--minimum-free-gib",
        "50",
        "--minimum-free-percent",
        "10",
        "--required-gib",
        "5",
        environment=environment,
    )

    assert admitted.returncode == 0, admitted.stderr
    assert "Capacity decision:      ADMIT" in admitted.stdout
    assert blocked.returncode == 1, blocked.stderr
    assert "Capacity decision:      BLOCKED" in blocked.stdout
    assert list(data_root.iterdir()) == []


def _write_fake_backup_commands(fake_bin: Path) -> None:
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

operation=""
database=""
previous=""
for argument in "$@"; do
  if [[ "$previous" == "--dbname" ]]; then
    database=$argument
    previous=""
    continue
  fi
  case "$argument" in
    pg_dump|pg_restore) operation=$argument ;;
    --dbname) previous="--dbname" ;;
  esac
done

case "$operation" in
  pg_dump)
    printf 'custom-format-test-dump:%s\n' "$database"
    ;;
  pg_restore)
    input=$(cat)
    [[ -n "$input" ]]
    ;;
  *)
    echo "unexpected Docker invocation" >&2
    exit 90
    ;;
esac
"""
    )
    fake_docker.chmod(0o755)

    fake_date = fake_bin / "date"
    fake_date.write_text("#!/usr/bin/env bash\necho 20260716T220000Z\n")
    fake_date.chmod(0o755)


def test_backup_is_verified_private_and_never_overwritten(tmp_path: Path) -> None:
    output_dir = tmp_path / "backups"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_fake_backup_commands(fake_bin)
    environment = _environment_with_bin(fake_bin)
    environment["WEATHER_BACKUP_PASSWORD"] = "test-only"

    first = _run(
        "backup_postgres.sh",
        "--database",
        "app",
        "--output-dir",
        str(output_dir),
        environment=environment,
    )

    dump = output_dir / "weather_app_20260716T220000Z.dump"
    checksum = output_dir / "weather_app_20260716T220000Z.dump.sha256"
    assert first.returncode == 0, first.stderr
    assert dump.read_bytes() == b"custom-format-test-dump:weather_app\n"
    assert checksum.read_text().split()[0] == hashlib.sha256(dump.read_bytes()).hexdigest()
    assert stat.S_IMODE(dump.stat().st_mode) == 0o600
    original = dump.read_bytes()

    second = _run(
        "backup_postgres.sh",
        "--database",
        "app",
        "--output-dir",
        str(output_dir),
        environment=environment,
    )

    assert second.returncode == 1
    assert "Refusing to overwrite existing backup" in second.stderr
    assert dump.read_bytes() == original


def test_retention_report_never_deletes_candidates(tmp_path: Path) -> None:
    data_root = tmp_path / "weather-data"
    raw = data_root / "raw"
    raw.mkdir(parents=True)
    old_file = raw / "old.grib2"
    new_file = raw / "new.grib2"
    old_file.write_bytes(b"old forecast")
    new_file.write_bytes(b"new forecast")
    old_timestamp = time.time() - 40 * 24 * 60 * 60
    os.utime(old_file, (old_timestamp, old_timestamp))

    report = _run(
        "report_storage_maintenance.sh",
        "--data-root",
        str(data_root),
        "--raw-days",
        "30",
        "--verbose",
    )

    assert report.returncode == 0, report.stderr
    assert "DRY RUN" in report.stdout
    assert "old.grib2" in report.stdout
    assert "Retention candidates: 1" in report.stdout
    assert old_file.read_bytes() == b"old forecast"
    assert new_file.read_bytes() == b"new forecast"


def test_integrity_report_can_fail_monitoring_without_deleting(tmp_path: Path) -> None:
    data_root = tmp_path / "weather-data"
    processed = data_root / "processed"
    processed.mkdir(parents=True)
    empty_file = processed / "empty.tif"
    empty_file.touch()

    report = _run(
        "report_storage_maintenance.sh",
        "--data-root",
        str(data_root),
        "--fail-on-integrity",
        "--verbose",
    )

    assert report.returncode == 1
    assert "INTEGRITY zero-byte file" in report.stdout
    assert empty_file.exists()


def test_systemd_example_preserves_data_on_stop() -> None:
    unit = (PROJECT_ROOT / "docs" / "systemd" / "weather-platform.service.example").read_text()
    retention_script = (SCRIPTS / "report_storage_maintenance.sh").read_text()

    assert "ExecStart=/usr/bin/docker compose up -d --wait" in unit
    assert "ExecStop=/usr/bin/docker compose stop" in unit
    assert "compose down" not in unit
    assert "--volumes" not in unit
    assert "--delete" not in retention_script


def test_zero_argument_install_and_run_scripts_are_safe_orchestrators() -> None:
    install_path = PROJECT_ROOT / "install.sh"
    run_path = PROJECT_ROOT / "run.sh"

    for path in (install_path, run_path):
        assert path.is_file()
        assert path.stat().st_mode & stat.S_IXUSR
        syntax = subprocess.run(
            ["bash", "-n", str(path)],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert syntax.returncode == 0, syntax.stderr

        rejected = subprocess.run(
            ["bash", str(path), "unexpected-argument"],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert rejected.returncode == 2

    install_source = install_path.read_text()
    run_source = run_path.read_text()

    assert "openssl rand" in install_source
    assert 'chmod 600 "$env_file"' in install_source
    assert "build --pull" in install_source
    assert "--ignore-buildable" in install_source
    assert "WEATHERAPP_DATA_DIR" in install_source
    assert "docker volume inspect" not in install_source
    assert "--profile observability" in run_source
    assert "WEATHER_INSTALL_SKIP_BUILD=1" in run_source
    assert "apply_migrations.sh" in run_source
    assert "verify_database.sh" in run_source
    assert "/health/ready" in run_source
    assert "--wait" in run_source

    caddy_source = (PROJECT_ROOT / "docker" / "caddy" / "Caddyfile").read_text()
    assert "@api_docs path /docs" in caddy_source
    assert "/openapi.json" in caddy_source
    assert "acme_ca https://acme-v02.api.letsencrypt.org/directory" in caddy_source

    combined = install_source + run_source
    assert "--volumes" not in combined
    assert "docker compose down" not in combined


def test_run_all_collection_dags_is_bounded_and_waits_for_results() -> None:
    script_path = SCRIPTS / "run_all_data_collection_dags.sh"
    source = script_path.read_text()

    assert script_path.stat().st_mode & stat.S_IXUSR
    syntax = subprocess.run(
        ["bash", "-n", str(script_path)],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert syntax.returncode == 0, syntax.stderr
    assert "load_ingestion_dag_definitions" in source
    assert "airflow dags trigger" in source
    assert "airflow dags state" in source
    assert "airflow tasks states-for-dag-run" in source
    assert "--conf" not in source
    assert "INGESTION_WAIT_TIMEOUT_SECONDS" in source
    assert "eccc_city_forecasts_ingest" in source
    assert "eccc_imagery_ingest" in source
    assert "nrcan_cwfis_cffdrs_ingest" in source
    assert source.index("airflow dags trigger fire_event_reconcile") > source.index(
        "if (( failure_count > 0 ))"
    )


def test_single_collection_trigger_requires_only_a_product() -> None:
    script_path = SCRIPTS / "trigger_ingestion.sh"
    source = script_path.read_text()

    assert script_path.stat().st_mode & stat.S_IXUSR
    assert "Usage: $0 PRODUCT" in source
    assert "build-trigger" not in source
    assert "--conf" not in source
    assert "airflow dags trigger" in source
    assert "airflow dags state" in source


def test_compose_persists_every_mutable_service_under_weatherapp_data() -> None:
    compose = (PROJECT_ROOT / "compose.yaml").read_text()

    expected_mounts = (
        "/airflow/logs:/opt/airflow/logs",
        "/caddy/data:/data",
        "/caddy/config:/config",
        "/tile-cache:/var/cache/nginx/weather",
        "/postgres:/var/lib/postgresql",
        "/redis:/data",
        "/sarracenia:/var/lib/sarracenia",
        "/prometheus:/prometheus",
        "/grafana:/var/lib/grafana",
    )
    for mount in expected_mounts:
        assert f"${{WEATHERAPP_DATA_DIR:-./weatherapp_data}}{mount}" in compose

    assert "${WEATHER_DATA_DIR:-./weatherapp_data/weather}:/srv/weather-platform/data" in compose
    assert "storage-init:" in compose
    assert "condition: service_completed_successfully" in compose
    assert "http://127.0.0.1/health" in compose
    assert "http://127.0.0.1/health/live" in compose
    subscriber = (PROJECT_ROOT / "docker" / "sarracenia" / "weatherapp.conf").read_text()
    assert "acceptUnmatched False" in subscriber
    assert "GDPS_TotalCloudCover_Sfc" in subscriber
    assert "HRDPS_TCDC_Sfc" in subscriber
    assert "RDPS_TotalCloudCover_Sfc" in subscriber
    assert "GDPS_WindGust_AGL-10m" in subscriber
    assert "HRDPS-WEonG_VISIFG_Sfc" in subscriber
    assert "RDPS_Snow-Accum1h_Sfc" in subscriber
    tile_cache = (PROJECT_ROOT / "docker" / "tile-cache" / "nginx.conf").read_text()
    assert "resolver 127.0.0.11" in tile_cache
    assert "server tile-api:8000 resolve;" in tile_cache
    assert "\nvolumes:\n" not in compose
    for legacy_volume in (
        "postgres_data:",
        "redis_data:",
        "caddy_data:",
        "caddy_config:",
        "tile_cache:",
        "prometheus_data:",
        "grafana_data:",
    ):
        assert legacy_volume not in compose


def test_lan_binding_exposes_only_the_web_gateway() -> None:
    compose = (PROJECT_ROOT / "compose.yaml").read_text()
    assert '"${APP_BIND_ADDRESS:-0.0.0.0}:${APP_PORT:-8080}:80"' in compose
    assert '"${APP_BIND_ADDRESS:-0.0.0.0}:${HTTPS_PORT:-8443}:443"' in compose
    for port in (
        "POSTGRES_HOST_PORT:-5433}:5432",
        "AIRFLOW_PORT:-8081}:8080",
        "PROMETHEUS_PORT:-9090}:9090",
        "GRAFANA_PORT:-3000}:3000",
    ):
        assert '"127.0.0.1:${' + port + '"' in compose
    assert "APP_BIND_ADDRESS=0.0.0.0" in (PROJECT_ROOT / ".env.example").read_text()


def test_web_gateway_is_https_only_with_canonical_http_redirects() -> None:
    caddy = (PROJECT_ROOT / "docker/caddy/Caddyfile").read_text()
    compose = (PROJECT_ROOT / "compose.yaml").read_text()
    example = (PROJECT_ROOT / ".env.example").read_text()
    run = (PROJECT_ROOT / "run.sh").read_text()

    assert "https://{$CADDY_SITE_ADDRESS} {" in caddy
    assert "{$CADDY_SITE_ADDRESS::80}" not in caddy
    http_block = caddy.split(":80 {", 1)[1].split("\n}", 1)[0]
    assert "redir https://{$CADDY_SITE_ADDRESS}{uri} 308" in http_block
    assert "reverse_proxy" not in http_block
    assert "file_server" not in http_block
    assert "{host}" not in http_block
    assert "${CADDY_SITE_ADDRESS:?" in compose
    assert "CADDY_SITE_ADDRESS=:80" not in example
    assert 'app_url="https://${CADDY_SITE_ADDRESS}"' in run
    assert 'echo "  Forecast:   ${app_url}/forecast"' in run
    assert "http://localhost:${app_port}" not in run


def test_postgis_image_is_reproducible_and_multi_architecture() -> None:
    compose = (PROJECT_ROOT / "compose.yaml").read_text()
    dockerfile = (PROJECT_ROOT / "docker" / "postgres" / "Dockerfile").read_text()

    assert "dockerfile: docker/postgres/Dockerfile" in compose
    assert "POSTGRES_BASE_IMAGE: ${POSTGRES_BASE_IMAGE:-postgres:18.4-alpine3.23}" in compose
    assert "ARG POSTGRES_BASE_IMAGE=postgres:18.4-alpine3.23" in dockerfile
    assert 'apk add --no-cache "postgis~3.6"' in dockerfile
    assert "/usr/share/postgresql18/extension/*" in dockerfile
    assert "/usr/local/share/postgresql/extension/" in dockerfile
    assert "/usr/lib/postgresql18/*.so" in dockerfile
    assert "/usr/local/lib/postgresql/" in dockerfile
    assert "POSTGRES_EXEC_PATH" not in compose
    assert "POSTGRES_LIBRARY_PATH" not in compose

    bootstrap = (PROJECT_ROOT / "docker" / "postgres" / "init-databases.sh").read_text()
    assert "WHERE NOT EXISTS" in bootstrap
    assert bootstrap.count("\\gexec") >= 10

    for service in ("api", "tiles"):
        dockerfile = (PROJECT_ROOT / "docker" / service / "Dockerfile").read_text()
        assert "apt-get install --yes --no-install-recommends libexpat1" in dockerfile

    assert "airflow-init:" in compose
    airflow_init = compose.split("  airflow-init:", 1)[1].split("  airflow-api-server:", 1)[0]
    assert "entrypoint:" not in airflow_init
    assert 'user: "0:0"' not in airflow_init
    assert "      - bash" in airflow_init

    airflow_cli = compose.split("  airflow-cli:", 1)[1]
    assert "entrypoint:" not in airflow_cli


def test_run_bootstraps_a_fresh_installation_without_arguments(tmp_path: Path) -> None:
    sandbox = tmp_path / "weather-platform"
    sandbox_scripts = sandbox / "scripts"
    fake_bin = tmp_path / "bin"
    sandbox_scripts.mkdir(parents=True)
    fake_bin.mkdir()

    for name in ("install.sh", "run.sh", ".env.example", "compose.yaml"):
        shutil.copy2(PROJECT_ROOT / name, sandbox / name)
    shutil.copy2(SCRIPTS / "check_disk_capacity.sh", sandbox_scripts)

    action_log = tmp_path / "actions.log"
    docker_log = tmp_path / "docker.log"
    for name, action in (
        ("apply_migrations.sh", "apply_migrations"),
        ("verify_database.sh", "verify_database"),
    ):
        stub = sandbox_scripts / name
        stub.write_text(
            f'#!/usr/bin/env bash\nset -euo pipefail\necho {action} >> "$FAKE_ACTION_LOG"\n'
        )
        stub.chmod(0o755)

    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'echo "$*" >> "$FAKE_DOCKER_LOG"\n'
        'if [[ "${1:-}" == volume && "${2:-}" == inspect ]]; then exit 1; fi\n'
        'if [[ "$*" == *" config"* ]]; then echo \'name: weather-platform\'; fi\n'
    )
    fake_docker.chmod(0o755)
    fake_df = fake_bin / "df"
    fake_df.write_text(
        "#!/usr/bin/env bash\n"
        "echo 'Filesystem 1024-blocks Used Available Capacity Mounted on'\n"
        "echo '/dev/test 104857600 52428800 52428800 50% /weather'\n"
    )
    fake_df.chmod(0o755)

    environment = _environment_with_bin(fake_bin)
    environment["FAKE_ACTION_LOG"] = str(action_log)
    environment["FAKE_DOCKER_LOG"] = str(docker_log)
    result = subprocess.run(
        ["bash", str(sandbox / "run.sh")],
        cwd=sandbox,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    generated_env = (sandbox / ".env").read_text()
    assert "change-me-" not in generated_env
    assert "AIRFLOW_FERNET_KEY=\n" not in generated_env
    assert stat.S_IMODE((sandbox / ".env").stat().st_mode) == 0o600
    storage_root = sandbox / "weatherapp_data"
    for directory in (
        "postgres",
        "redis",
        "weather/processed",
        "weather/amqp/inbox",
        "airflow/logs",
        "sarracenia/cache",
        "caddy/data",
        "caddy/config",
        "tile-cache",
        "prometheus",
        "grafana",
        "backups/postgres",
    ):
        assert (storage_root / directory).is_dir()
    assert action_log.read_text().splitlines() == ["apply_migrations", "verify_database"]

    docker_actions = docker_log.read_text()
    assert "compose version" in docker_actions
    assert "volume inspect" not in docker_actions
    assert "--profile observability up --build -d --wait" in docker_actions
    assert "exec -T weather-api" in docker_actions
    assert "exec -T tile-api" in docker_actions
