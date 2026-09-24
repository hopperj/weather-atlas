from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
ENTRYPOINT = ROOT / "docker/sarracenia/entrypoint.sh"


def test_subscriber_entrypoint_creates_group_writable_files_and_directories(tmp_path: Path) -> None:
    # Do not change the test runner's umask; exercise the entrypoint in a child.
    command = """
import json, os, pathlib, stat, sys
directory = pathlib.Path(sys.argv[1]) / 'new delivery'
directory.mkdir()
payload = directory / 'weather data.grib2'
payload.write_bytes(b'weather')
print(json.dumps([stat.S_IMODE(path.stat().st_mode) for path in (directory, payload)]))
"""
    result = subprocess.run(
        ["sh", str(ENTRYPOINT), sys.executable, "-c", command, str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
        umask=0o077,
    )
    assert json.loads(result.stdout) == [0o775, 0o664]
    assert (tmp_path / "new delivery/weather data.grib2").read_bytes() == b"weather"


def test_entrypoint_preserves_command_exit_status() -> None:
    result = subprocess.run(["sh", str(ENTRYPOINT), "sh", "-c", "exit 23"], check=False)
    assert result.returncode == 23


def test_delivery_permissions_do_not_copy_restrictive_remote_modes() -> None:
    options = {}
    for line in (ROOT / "docker/sarracenia/weatherapp.conf").read_text().splitlines():
        words = line.split()
        if words and words[0] in {"permCopy", "permDefault", "permDirDefault"}:
            assert words[0] not in options
            options[words[0]] = words[1]
    assert options == {"permCopy": "False", "permDefault": "0664", "permDirDefault": "0775"}


def test_image_applies_the_entrypoint_as_the_normal_non_root_subscriber() -> None:
    dockerfile = (ROOT / "docker/sarracenia/Dockerfile").read_text()
    assert 'ENTRYPOINT ["/usr/local/bin/weather-subscriber-entrypoint"]' in dockerfile
    assert "COPY --chmod=755 docker/sarracenia/entrypoint.sh" in dockerfile
    assert "USER 50000:0" in dockerfile
    assert "--chmod=600 docker/sarracenia/credentials.conf" in dockerfile


def test_subscriber_can_preserve_its_broker_queue_identity_on_handover() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    assert compose["services"]["eccc-subscriber"]["hostname"] == "${ECCC_SUBSCRIBER_HOSTNAME:-}"
    configuration = (ROOT / "docker/sarracenia/weatherapp.conf").read_text()
    assert "queueName q_${BROKER_USER}.${PROGRAM}.${CONFIG}.${HOSTNAME}" in configuration
