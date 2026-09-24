from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def installation(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "scripts").mkdir()
    for name in ("install.sh", "run.sh", ".env.example", "compose.yaml"):
        shutil.copy2(ROOT / name, repo / name)
    shutil.copy2(ROOT / "scripts/check_disk_capacity.sh", repo / "scripts")
    shutil.copy2(repo / ".env.example", repo / ".env")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name, contents in {
        "docker": 'echo "$*" >> "$DOCKER_LOG"\n',
        "df": "echo 'Filesystem 1024-blocks Used Available Capacity Mounted on'\n"
        "echo '/dev/test 1000000 100000 900000 10% /weather'\n",
        "findmnt": 'test "${MOUNT_PRESENT:-yes}" = yes || exit 1\n'
        'echo "${MOUNT_SOURCE:-nas:/weather}"\n',
    }.items():
        executable = fake_bin / name
        executable.write_text("#!/bin/sh\nset -eu\n" + contents)
        executable.chmod(0o755)
    env = os.environ.copy()
    env.update(
        PATH=f"{fake_bin}:{env['PATH']}",
        DOCKER_LOG=str(tmp_path / "docker.log"),
        WEATHER_INSTALL_SKIP_BUILD="1",
    )
    return repo, env


def configure(repo: Path, **settings: str) -> None:
    path = repo / ".env"
    lines = path.read_text().splitlines()
    path.write_text(
        "\n".join(
            f"{line.split('=', 1)[0]}={settings[line.split('=', 1)[0]]}"
            if line.split("=", 1)[0] in settings
            else line
            for line in lines
        )
        + "\n"
    )


def invoke(
    repo: Path, env: dict[str, str], script: str = "install.sh"
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(repo / script)], cwd=repo, env=env, capture_output=True, text=True, check=False
    )


def test_external_nas_is_untouched_by_install(tmp_path: Path) -> None:
    repo, env = installation(tmp_path)
    nas = tmp_path / "nas"
    for name in (
        "raw",
        "staging",
        "processed",
        "derived",
        "quarantine",
        "cache",
        "temporary",
        "amqp/inbox",
    ):
        (nas / name).mkdir(parents=True)
    sentinel = nas / "processed/existing.tif"
    sentinel.write_bytes(b"weather-data")
    sentinel.chmod(0o640)
    before = {str(p): (p.stat().st_mode, p.stat().st_mtime_ns) for p in nas.rglob("*")}
    configure(
        repo,
        WEATHER_DATA_DIR=str(nas),
        WEATHER_MANAGE_DATA_PERMISSIONS="false",
        WEATHER_DATA_MOUNTPOINT=str(nas),
        WEATHER_DATA_MOUNT_SOURCE="nas:/weather",
    )
    result = invoke(repo, env)
    assert result.returncode == 0, result.stderr
    assert (repo / "weatherapp_data/postgres").is_dir()
    assert not (repo / "weatherapp_data/weather").exists()
    assert before == {str(p): (p.stat().st_mode, p.stat().st_mtime_ns) for p in nas.rglob("*")}
    assert sentinel.read_bytes() == b"weather-data"


@pytest.mark.parametrize(
    "setting,value", [("MOUNT_PRESENT", "no"), ("MOUNT_SOURCE", "wrong:/share")]
)
def test_mount_guard_fails_before_creating_state_or_changing_secrets(
    tmp_path: Path, setting: str, value: str
) -> None:
    repo, env = installation(tmp_path)
    configure(
        repo, WEATHER_DATA_MOUNTPOINT="/missing-nas", WEATHER_DATA_MOUNT_SOURCE="nas:/weather"
    )
    before = (repo / ".env").read_bytes()
    env[setting] = value
    result = invoke(repo, env)
    assert result.returncode != 0
    assert not (repo / "weatherapp_data").exists()
    assert (repo / ".env").read_bytes() == before


def test_missing_external_directory_is_not_created(tmp_path: Path) -> None:
    repo, env = installation(tmp_path)
    missing = tmp_path / "missing-weather"
    configure(repo, WEATHER_DATA_DIR=str(missing), WEATHER_MANAGE_DATA_PERMISSIONS="false")
    result = invoke(repo, env)
    assert result.returncode != 0
    assert "must already exist" in result.stderr
    assert not missing.exists()


@pytest.mark.parametrize("absolute", [False, True])
def test_postgres_directory_is_independent_of_service_storage(
    tmp_path: Path, absolute: bool
) -> None:
    repo, env = installation(tmp_path)
    target = repo / "postgres_data"
    configure(repo, POSTGRES_DATA_DIR=str(target) if absolute else "./postgres_data")
    result = invoke(repo, env)
    assert result.returncode == 0, result.stderr
    assert target.is_dir()
    assert not (repo / "weatherapp_data/postgres").exists()
    assert (repo / "weatherapp_data/airflow/logs").is_dir()
    # A subsequent install must preserve the established database credentials.
    before = (repo / ".env").read_bytes()
    result = invoke(repo, env)
    assert result.returncode == 0, result.stderr
    assert (repo / ".env").read_bytes() == before


def test_existing_independent_postgres_preserves_credentials(tmp_path: Path) -> None:
    repo, env = installation(tmp_path)
    (repo / "postgres_data").mkdir()
    configure(repo, POSTGRES_DATA_DIR="./postgres_data")
    before = (repo / ".env").read_bytes()
    result = invoke(repo, env)
    assert result.returncode == 0, result.stderr
    assert "credentials were not rotated" in result.stderr
    assert (repo / ".env").read_bytes() == before
    assert not (repo / "weatherapp_data/postgres").exists()


def test_nested_service_state_does_not_look_like_an_existing_cluster(tmp_path: Path) -> None:
    repo, env = installation(tmp_path)
    configure(
        repo,
        POSTGRES_DATA_DIR="./postgres_data",
        WEATHERAPP_DATA_DIR="./postgres_data/pending-service-migration",
        WEATHER_DATA_DIR="./data/weather",
    )
    result = invoke(repo, env)
    assert result.returncode == 0, result.stderr
    assert "Generated installation secrets" in result.stdout
    assert "change-me-" not in (repo / ".env").read_text()
    assert (repo / "postgres_data").is_dir()
    assert (repo / "postgres_data/pending-service-migration/airflow/logs").is_dir()
    assert not (repo / "postgres_data/pending-service-migration/postgres").exists()
    assert not (repo / "weatherapp_data").exists()


def test_local_database_storage_is_excluded_from_git_and_builds() -> None:
    assert "/postgres_data" in (ROOT / ".gitignore").read_text().splitlines()
    assert "postgres_data" in (ROOT / ".dockerignore").read_text().splitlines()


def test_nas_services_are_not_created_or_modified_by_installer(tmp_path: Path) -> None:
    repo, env = installation(tmp_path)
    service_root = tmp_path / "nas/services"
    for name in (
        "redis",
        "airflow/logs",
        "sarracenia/cache",
        "caddy/data",
        "caddy/config",
        "tile-cache",
        "backups/postgres",
    ):
        (service_root / name).mkdir(parents=True)
    sentinel = service_root / "caddy/data/certificate"
    sentinel.write_bytes(b"existing-private-state")
    sentinel.chmod(0o600)
    before = {str(p): (p.stat().st_mode, p.stat().st_mtime_ns) for p in service_root.rglob("*")}
    configure(
        repo,
        WEATHERAPP_DATA_DIR=str(service_root),
        POSTGRES_DATA_DIR="./postgres_data",
        WEATHER_MONITORING_DIR="./postgres_data/monitoring",
        WEATHER_MANAGE_SERVICE_PERMISSIONS="false",
    )
    result = invoke(repo, env)
    assert result.returncode == 0, result.stderr
    assert (repo / "postgres_data/monitoring/prometheus").is_dir()
    assert (repo / "postgres_data/monitoring/grafana").is_dir()
    assert not (service_root / "postgres").exists()
    assert not (service_root / "prometheus").exists()
    assert before == {
        str(p): (p.stat().st_mode, p.stat().st_mtime_ns) for p in service_root.rglob("*")
    }
    assert sentinel.read_bytes() == b"existing-private-state"


def test_missing_nas_service_directory_is_not_created(tmp_path: Path) -> None:
    repo, env = installation(tmp_path)
    service_root = tmp_path / "nas/services"
    configure(
        repo,
        WEATHERAPP_DATA_DIR=str(service_root),
        WEATHER_MONITORING_DIR="./postgres_data/monitoring",
        WEATHER_MANAGE_SERVICE_PERMISSIONS="false",
    )
    before = (repo / ".env").read_bytes()
    result = invoke(repo, env)
    assert result.returncode != 0
    assert "Externally managed service directory" in result.stderr
    assert not service_root.exists()
    assert (repo / ".env").read_bytes() == before


def test_nas_services_require_explicit_local_monitoring_storage(tmp_path: Path) -> None:
    repo, env = installation(tmp_path)
    configure(repo, WEATHER_MANAGE_SERVICE_PERMISSIONS="false")
    result = invoke(repo, env)
    assert result.returncode != 0
    assert "Set WEATHER_MONITORING_DIR" in result.stderr
    assert not (repo / "weatherapp_data").exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permissions")
def test_reinstall_does_not_enter_private_container_state(tmp_path: Path) -> None:
    repo, env = installation(tmp_path)
    assert invoke(repo, env).returncode == 0
    private = repo / "weatherapp_data/sarracenia"
    private.chmod(0o000)
    try:
        result = invoke(repo, env)
        assert result.returncode == 0, result.stderr
        assert private.stat().st_mode & 0o777 == 0
    finally:
        private.chmod(0o700)


def test_startup_hold_stops_before_docker_or_install(tmp_path: Path) -> None:
    repo, env = installation(tmp_path)
    configure(repo, WEATHER_STARTUP_HOLD="migration-pending")
    result = invoke(repo, env, "run.sh")
    assert result.returncode != 0
    assert "migration-pending" in result.stderr
    assert not Path(env["DOCKER_LOG"]).exists()
    assert not (repo / "weatherapp_data").exists()


@pytest.mark.parametrize("managed", ["true", "false"])
def test_storage_init_only_manages_nas_when_enabled(tmp_path: Path, managed: str) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "actions"
    for name in ("mkdir", "chmod", "chown"):
        command = fake_bin / name
        command.write_text(f'#!/bin/sh\nprintf "%s\\n" "{name} $*" >> "$ACTION_LOG"\n')
        command.chmod(0o755)
    env = os.environ.copy()
    env.update(
        PATH=f"{fake_bin}:{env['PATH']}",
        ACTION_LOG=str(log),
        AIRFLOW_UID="1000",
        WEATHER_DATA_GID="100",
        WEATHER_MANAGE_DATA_PERMISSIONS=managed,
    )
    result = subprocess.run(
        ["sh", str(ROOT / "docker/storage/init-storage.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    actions = log.read_text()
    assert "chown 50000:0 /storage/sarracenia" in actions
    assert "chown 1000:0 /storage/airflow" in actions
    assert "/storage/postgres" not in actions
    if managed == "false":
        assert "/weather-data" not in actions
    else:
        assert "chown 1000:100 /weather-data/processed" in actions
        assert "chmod 2770 /weather-data/processed" in actions


@pytest.mark.parametrize("missing", [False, True])
def test_storage_initializer_does_not_modify_managed_nas_services(
    tmp_path: Path, missing: bool
) -> None:
    nas = tmp_path / "nas-services"
    monitoring = tmp_path / "local-monitoring"
    for name in (
        "redis",
        "airflow/logs",
        "sarracenia/cache",
        "caddy/data",
        "caddy/config",
        "tile-cache",
        "backups/postgres",
    ):
        if missing and name == "caddy/config":
            continue
        (nas / name).mkdir(parents=True)
    before = {str(p): (p.stat().st_mode, p.stat().st_mtime_ns) for p in nas.rglob("*")}
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "actions"
    for name in ("chmod", "chown"):
        command = fake_bin / name
        command.write_text(f'#!/bin/sh\nprintf "%s\\n" "{name} $*" >> "$ACTION_LOG"\n')
        command.chmod(0o755)
    script = tmp_path / "init.sh"
    script.write_text(
        (ROOT / "docker/storage/init-storage.sh")
        .read_text()
        .replace("/storage", str(nas))
        .replace("/monitoring", str(monitoring))
    )
    env = os.environ.copy()
    env.update(
        PATH=f"{fake_bin}:{env['PATH']}",
        ACTION_LOG=str(log),
        WEATHER_MANAGE_DATA_PERMISSIONS="false",
        WEATHER_MANAGE_SERVICE_PERMISSIONS="false",
        WEATHER_MONITORING_DIR=str(monitoring),
    )
    result = subprocess.run(
        ["sh", str(script)], env=env, capture_output=True, text=True, check=False
    )
    if missing:
        assert result.returncode != 0
        assert "must already exist" in result.stderr
        assert not (nas / "caddy/config").exists()
        assert not log.exists()
    else:
        assert result.returncode == 0, result.stderr
        assert str(nas) not in log.read_text()
        assert str(monitoring) in log.read_text()
    assert before == {str(p): (p.stat().st_mode, p.stat().st_mtime_ns) for p in nas.rglob("*")}


def test_all_weather_consumers_receive_shared_group() -> None:
    import yaml

    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    for name in (
        "weather-api",
        "tile-api",
        "eccc-subscriber",
        "airflow-scheduler",
        "airflow-dag-processor",
        "redis",
        "reverse-proxy",
        "storage-init",
    ):
        assert "${WEATHER_DATA_GID:-0}" in compose["services"][name]["group_add"]
    assert (
        "${WEATHER_DATA_DIR:-./weatherapp_data/weather}:/weather-data"
        in compose["services"]["storage-init"]["volumes"]
    )


def test_sparky_profile_separates_nas_data_from_local_databases() -> None:
    import yaml

    profile = dict(
        line.split("=", 1)
        for line in (ROOT / ".env.sparky.example").read_text().splitlines()
        if line and not line.startswith("#")
    )
    deployment = Path("/home/hopperj/weather-atlas")
    assert Path(profile["WEATHER_DATA_MOUNTPOINT"]) == deployment / "data"
    assert Path(profile["WEATHER_DATA_DIR"]) == deployment / "data/weather"
    assert Path(profile["WEATHERAPP_DATA_DIR"]) == deployment / "data/services"
    assert Path(profile["POSTGRES_DATA_DIR"]) == deployment / "postgres_data"
    assert Path(profile["WEATHER_MONITORING_DIR"]) == deployment / "postgres_data/monitoring"
    assert Path(profile["WEATHER_BACKUP_DIR"]).is_relative_to(Path(profile["WEATHERAPP_DATA_DIR"]))
    assert profile["WEATHER_MANAGE_DATA_PERMISSIONS"] == "false"
    assert profile["WEATHER_MANAGE_SERVICE_PERMISSIONS"] == "false"
    assert profile["REDIS_RUN_USER"] == "999:1000"
    assert profile["WEATHER_DATA_GID"] == "100"
    assert profile["WEATHER_STARTUP_HOLD"] not in ("", "false")
    assert "weatherapp_data" not in " ".join(profile.values())
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    for name in ("weather-api", "tile-api", "eccc-subscriber", "airflow-scheduler"):
        assert any(
            volume.startswith("${WEATHER_DATA_DIR:") and ":/srv/weather-platform/data" in volume
            for volume in compose["services"][name]["volumes"]
        )
    assert any(
        volume.startswith("${POSTGRES_DATA_DIR:") and ":/var/lib/postgresql" in volume
        for volume in compose["services"]["postgres"]["volumes"]
    )
