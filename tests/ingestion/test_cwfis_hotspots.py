from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from weather_ingest.cwfis_hotspots import (
    CwfisHotspotSettings,
    candidate_dates,
    cwfis_filename,
    cwfis_url,
    discover_download_plan,
    geojson_relative_path,
    manifest_relative_path,
    normalize_cwfis_csv,
    publish_latest,
    raw_relative_path,
)
from weather_ingest.models import RemoteObject


def test_candidate_dates_target_finalized_previous_days() -> None:
    assert candidate_dates(
        datetime(2026, 7, 20, 17, 30, tzinfo=UTC),
        lag_days=1,
        lookback_days=3,
    ) == (
        date(2026, 7, 19),
        date(2026, 7, 18),
        date(2026, 7, 17),
    )


def test_settings_are_bounded_and_environment_configurable() -> None:
    settings = CwfisHotspotSettings.from_environment(
        {
            "CWFIS_LAG_DAYS": "1",
            "CWFIS_LOOKBACK_DAYS": "5",
            "CWFIS_MAXIMUM_DAYS_PER_RUN": "2",
            "CWFIS_MAXIMUM_ROWS": "1000",
            "CWFIS_MINIMUM_FREE_BYTES": "0",
            "CWFIS_MAXIMUM_DOWNLOAD_BYTES": "2000000",
            "CWFIS_TIMEOUT_SECONDS": "60",
        }
    )

    assert settings.lookback_days == 5
    assert settings.minimum_free_bytes == 0
    with pytest.raises(ValueError, match="lag"):
        CwfisHotspotSettings(lag_days=0)


def test_discovery_selects_available_missing_days_with_canonical_paths(
    tmp_path: Path,
) -> None:
    settings = CwfisHotspotSettings(
        lookback_days=4,
        maximum_days_per_run=2,
        minimum_free_bytes=0,
    )
    unavailable = date(2026, 7, 18)

    def head(data_date: date) -> RemoteObject | None:
        if data_date == unavailable:
            return None
        return RemoteObject(
            url=cwfis_url(data_date),
            filename=cwfis_filename(data_date),
            size_bytes=250_000,
        )

    plan = discover_download_plan(
        settings,
        tmp_path,
        now=datetime(2026, 7, 20, 17, tzinfo=UTC),
        head_object=head,
    )

    assert [request["data_date"] for request in plan["requests"]] == [
        "2026-07-19",
        "2026-07-17",
    ]
    assert plan["requests"][0]["relative_path"] == (
        "raw/nrcan/cwfis/firem3/2026/07/19/20260719.csv"
    )


def test_discovery_refreshes_a_completed_day_when_cwfis_revises_it(
    tmp_path: Path,
) -> None:
    data_date = date(2026, 7, 21)
    raw_relative = raw_relative_path(data_date)
    geojson_relative = geojson_relative_path(data_date)
    raw = tmp_path / raw_relative
    geojson = tmp_path / geojson_relative
    manifest = tmp_path / manifest_relative_path(data_date)
    raw.parent.mkdir(parents=True)
    geojson.parent.mkdir(parents=True)
    raw.write_bytes(b"partial")
    geojson.write_text('{"type":"FeatureCollection"}\n')
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "provider": "nrcan",
                "product": "cwfis_firem3_hotspots",
                "data_date": data_date.isoformat(),
                "sensor": "VIIRS-I",
                "source_etag": '"old"',
                "raw": {
                    "relative_path": raw_relative.as_posix(),
                    "size_bytes": raw.stat().st_size,
                },
                "geojson": {
                    "relative_path": geojson_relative.as_posix(),
                    "size_bytes": geojson.stat().st_size,
                },
            }
        )
    )

    plan = discover_download_plan(
        CwfisHotspotSettings(
            lookback_days=1,
            maximum_days_per_run=1,
            minimum_free_bytes=0,
        ),
        tmp_path,
        now=datetime(2026, 7, 22, 12, tzinfo=UTC),
        head_object=lambda _: RemoteObject(
            url=cwfis_url(data_date),
            filename=cwfis_filename(data_date),
            size_bytes=len(b"complete"),
            etag='"new"',
        ),
    )

    assert plan["requests"][0]["data_date"] == "2026-07-21"
    assert plan["requests"][0]["replace_existing"] is True


def test_normalization_filters_modis_and_deduplicates_viirs(
    tmp_path: Path,
) -> None:
    source = tmp_path / "20260719.csv"
    source.write_text(
        "lat, lon, rep_date, source, sensor, fwi, fuel, ros, sfc, tfc, bfc, hfi, estarea\n"
        "45.0,-63.0,2026-07-19 12:00:00,NASA_z,MODIS,4,C2,1,2,3,4,5,6\n"
        "46.0,-64.0,2026-07-19 13:00:00,HMS,VIIRS-I,,C3,1,2,3,4,5,6\n"
        "46.0,-64.0,2026-07-19 13:00:00,NASA,VIIRS-I,9,C3,1,2,3,4,5,6\n"
        "47.0,-65.0,2026-07-19 14:00:00,NASA,VIIRS-I,10,C4,2,3,4,5,6,7\n"
    )
    destination = tmp_path / "hotspots.geojson"

    result = normalize_cwfis_csv(
        source,
        date(2026, 7, 19),
        destination,
        maximum_rows=100,
        generated_at=datetime(2026, 7, 20, tzinfo=UTC),
    )
    payload = json.loads(destination.read_text())

    assert result == {
        "raw_row_count": 4,
        "viirs_row_count": 3,
        "feature_count": 2,
        "duplicate_count": 1,
        "first_observation": "2026-07-19T13:00:00Z",
        "last_observation": "2026-07-19T14:00:00Z",
        "bbox": [-65.0, 46.0, -64.0, 47.0],
    }
    assert payload["nominal_resolution_metres"] == 375
    assert payload["features"][0]["properties"]["fwi"] == 9.0
    assert payload["features"][0]["geometry"]["coordinates"] == [-64.0, 46.0]


def test_normalization_rejects_wrong_day_and_unbounded_rows(tmp_path: Path) -> None:
    source = tmp_path / "bad.csv"
    source.write_text(
        "lat,lon,rep_date,source,sensor,fwi,fuel,ros,sfc,tfc,bfc,hfi,estarea\n"
        "46,-64,2026-07-18 12:00:00,NASA,VIIRS-I,1,C2,1,1,1,1,1,1\n"
    )

    with pytest.raises(ValueError, match="outside"):
        normalize_cwfis_csv(
            source,
            date(2026, 7, 19),
            tmp_path / "bad.geojson",
            maximum_rows=1,
        )


def test_older_recovery_does_not_regress_latest_snapshot(tmp_path: Path) -> None:
    def result_for(data_date: date, value: str) -> dict[str, object]:
        relative = geojson_relative_path(data_date)
        path = tmp_path / relative
        path.parent.mkdir(parents=True)
        path.write_text(value)
        return {
            "data_date": data_date.isoformat(),
            "manifest": f"{data_date}/manifest.json",
            "raw_relative_path": raw_relative_path(data_date).as_posix(),
            "raw_size_bytes": 100,
            "geojson_relative_path": relative.as_posix(),
            "geojson_size_bytes": len(value),
            "feature_count": 1,
        }

    newer = result_for(date(2026, 7, 19), '{"newer":true}\n')
    older = result_for(date(2026, 7, 18), '{"older":true}\n')

    publish_latest([newer], tmp_path)
    publish_latest([older], tmp_path)

    latest_directory = tmp_path / "processed/nrcan/cwfis/firem3"
    assert (latest_directory / "latest.geojson").read_text() == '{"newer":true}\n'
    assert json.loads((latest_directory / "latest.json").read_text())["data_date"] == ("2026-07-19")
