from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess

from weather_ingest import gfs_profiles


def test_nearest_values_does_not_require_unused_pressure_level_q(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "gfs.grib2"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(gfs_profiles.shutil, "which", lambda _name: "/usr/bin/grib_get")
    surface = "\n".join(
        (
            "sp 0 100000",
            "2t 2 290",
            "2sh 2 0.005",
            "2d 2 280",
            "10u 10 3",
            "10v 10 4",
            "orog 0 100",
        )
    )
    aloft = "\n".join(
        f"{name} {level} {value}"
        for level in range(100, 1100, 50)
        for name, value in (("t", 270.0), ("gh", float(level)))
    )
    calls = iter((surface, aloft))

    def fake_run(*_args, **_kwargs):
        return CompletedProcess([], 0, stdout=next(calls), stderr="")

    monkeypatch.setattr(gfs_profiles.subprocess, "run", fake_run)
    surface_values, aloft_values = gfs_profiles._nearest_values(
        source,
        latitude=60.0,
        longitude=-100.0,
    )

    assert surface_values["2sh"] == 0.005
    assert set(aloft_values) == {"t", "gh"}
    assert len(aloft_values["t"]) == 20
