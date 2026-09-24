from __future__ import annotations

import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts/download_smoke_validation_inputs.py"


@pytest.fixture(scope="module")
def configured_data_root():
    return runpy.run_path(str(SCRIPT))["configured_data_root"]


@pytest.mark.parametrize(
    "container_root,host_root,expected",
    [
        (None, None, None),
        (
            None,
            "/home/hopperj/weather-atlas/data/weather",
            "/home/hopperj/weather-atlas/data/weather",
        ),
        ("/srv/weather-platform/data", "/host/data/weather", "/srv/weather-platform/data"),
        ("", "/host/data/weather", "/host/data/weather"),
    ],
)
def test_validation_uses_configured_storage(
    monkeypatch, configured_data_root, container_root, host_root, expected
):
    for key, value in (("WEATHER_DATA_ROOT", container_root), ("WEATHER_DATA_DIR", host_root)):
        monkeypatch.delenv(key, raising=False)
        if value is not None:
            monkeypatch.setenv(key, value)
    assert configured_data_root() == (Path(expected) if expected else None)


def test_validation_requires_explicit_storage_before_any_download():
    environment = os.environ.copy()
    environment.pop("WEATHER_DATA_ROOT", None)
    environment.pop("WEATHER_DATA_DIR", None)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--start", "2025-07-01", "--end", "2025-07-01"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "provide --data-root or set WEATHER_DATA_ROOT/WEATHER_DATA_DIR" in result.stderr
