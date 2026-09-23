from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from weather_ingest.models import RemoteObject
from weather_ingest.noaa_gfs import (
    GfsIngestionSettings,
    candidate_cycles,
    discover_download_plan,
    gfs_filename,
    gfs_object_url,
    object_relative_path,
    write_cycle_manifests,
)


def test_candidate_cycles_are_six_hourly_and_newest_first() -> None:
    assert candidate_cycles(
        datetime(2026, 7, 20, 16, 45, tzinfo=UTC), lookback_hours=18
    ) == (
        datetime(2026, 7, 20, 12, tzinfo=UTC),
        datetime(2026, 7, 20, 6, tzinfo=UTC),
        datetime(2026, 7, 20, 0, tzinfo=UTC),
    )


def test_settings_are_bounded_and_environment_configurable() -> None:
    settings = GfsIngestionSettings.from_environment(
        {
            "GFS_RESOLUTION": "1p00",
            "GFS_FORECAST_HOURS": "0,3,6",
            "GFS_LOOKBACK_HOURS": "12",
            "GFS_MAXIMUM_CYCLES_PER_RUN": "1",
            "GFS_MINIMUM_FREE_BYTES": "0",
            "GFS_MAXIMUM_DOWNLOAD_BYTES": "100000000",
            "GFS_TIMEOUT_SECONDS": "60",
        }
    )

    assert settings.forecast_hours == (0, 3, 6)
    assert settings.dimensions == (360, 181)
    with pytest.raises(ValueError, match="three-hourly"):
        GfsIngestionSettings(forecast_hours=(0, 1))


def test_discovery_selects_complete_missing_cycles_and_canonical_paths(
    tmp_path: Path,
) -> None:
    settings = GfsIngestionSettings(
        forecast_hours=(0, 3),
        lookback_hours=18,
        maximum_cycles_per_run=2,
        minimum_free_bytes=0,
    )
    now = datetime(2026, 7, 20, 16, 45, tzinfo=UTC)

    def head(cycle: datetime, hour: int, resolution: str) -> RemoteObject | None:
        # Pretend the newest cycle is still publishing f003.
        if cycle.hour == 12 and hour == 3:
            return None
        filename = gfs_filename(cycle, hour, resolution)
        return RemoteObject(
            gfs_object_url(cycle, hour, resolution),
            filename,
            size_bytes=42_000_000,
        )

    plan = discover_download_plan(
        settings, tmp_path, now=now, head_object=head
    )

    assert plan["cycles"] == [
        "2026-07-20T06:00:00Z",
        "2026-07-20T00:00:00Z",
    ]
    assert len(plan["requests"]) == 4
    assert plan["requests"][0]["relative_path"] == (
        "raw/noaa/gfs/global_1p00/2026/07/20/06/"
        "gfs.t06z.pgrb2.1p00.f000"
    )


def test_manifests_make_a_cycle_idempotently_complete(tmp_path: Path) -> None:
    settings = GfsIngestionSettings(
        forecast_hours=(0, 3),
        lookback_hours=6,
        maximum_cycles_per_run=1,
        minimum_free_bytes=0,
    )
    cycle = datetime(2026, 7, 20, 12, tzinfo=UTC)
    results = []
    for hour in settings.forecast_hours:
        relative_path = object_relative_path(settings, cycle, hour)
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"validated-grib")
        results.append(
            {
                "initialization_time": "2026-07-20T12:00:00Z",
                "valid_time": f"2026-07-20T{12 + hour:02d}:00:00Z",
                "forecast_hour": hour,
                "filename": destination.name,
                "relative_path": relative_path.as_posix(),
                "size_bytes": len(b"validated-grib"),
                "sha256": str(hour) * 64,
                "message_count": 500,
                "common_pressure_level_count": 41,
            }
        )
    plan = {
        "settings": settings.as_dict(),
        "cycles": ["2026-07-20T12:00:00Z"],
        "requests": [],
    }

    published = write_cycle_manifests(plan, results, tmp_path)
    assert published["file_count"] == 2
    assert (tmp_path / published["manifests"][0]).is_file()

    no_head_calls = 0

    def unexpected_head(
        _cycle: datetime, _hour: int, _resolution: str
    ) -> RemoteObject | None:
        nonlocal no_head_calls
        no_head_calls += 1
        raise AssertionError("completed cycles must not hit NOAA")

    second_plan = discover_download_plan(
        settings,
        tmp_path,
        now=datetime(2026, 7, 20, 17, tzinfo=UTC),
        head_object=unexpected_head,
    )
    assert second_plan["status"] == "no_new_data"
    assert no_head_calls == 0


def test_recovering_an_older_cycle_does_not_regress_latest_pointer(
    tmp_path: Path,
) -> None:
    settings = GfsIngestionSettings(
        forecast_hours=(0,),
        lookback_hours=12,
        maximum_cycles_per_run=1,
        minimum_free_bytes=0,
    )
    latest_path = tmp_path / "raw/noaa/gfs/global_1p00/latest.json"
    latest_path.parent.mkdir(parents=True)
    latest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "initialization_time": "2026-07-20T12:00:00Z",
                "manifest": "newer/manifest.json",
            }
        )
    )
    older_cycle = datetime(2026, 7, 20, 6, tzinfo=UTC)
    relative_path = object_relative_path(settings, older_cycle, 0)
    destination = tmp_path / relative_path
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"validated-grib")
    result = {
        "initialization_time": "2026-07-20T06:00:00Z",
        "valid_time": "2026-07-20T06:00:00Z",
        "forecast_hour": 0,
        "filename": destination.name,
        "relative_path": relative_path.as_posix(),
        "size_bytes": len(b"validated-grib"),
        "sha256": "0" * 64,
        "message_count": 500,
        "common_pressure_level_count": 41,
    }
    plan = {
        "settings": settings.as_dict(),
        "cycles": ["2026-07-20T06:00:00Z"],
        "requests": [],
    }

    write_cycle_manifests(plan, [result], tmp_path)

    assert json.loads(latest_path.read_text())["initialization_time"] == (
        "2026-07-20T12:00:00Z"
    )
