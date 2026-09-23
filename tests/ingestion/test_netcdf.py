from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
from weather_ingest.grib import CommandResult
from weather_ingest.models import ParsedSourceObject, RemoteObject
from weather_ingest.netcdf import (
    GdalNetcdfInspector,
    NetcdfValidationError,
    hrepa_variable_name,
    parse_gdalinfo_netcdf,
    validate_hrepa_netcdf_content,
)


def _parsed(revision: str = "percentile_25") -> ParsedSourceObject:
    valid_time = datetime(2026, 7, 19, 6, tzinfo=UTC)
    parameter = {
        "ensemble_members": "Precip-Accum06h",
        "percentile_25": "Precip-Accum06h-Pct25",
        "percentile_75": "Precip-Accum06h-Pct75",
    }[revision]
    filename = (
        f"20260719T06Z_MSC_HREPA_{parameter}_"
        "Sfc_RLatLon0.0225_PT0H.nc"
    )
    return ParsedSourceObject(
        remote=RemoteObject(f"https://dd.weather.gc.ca/{filename}", filename),
        product_code="hrepa",
        producer="HREPA",
        domain_code="canada_northern_us",
        initialization_time=valid_time,
        valid_time=valid_time,
        forecast_hour=0,
        parameter=parameter,
        source_level="Sfc",
        grid="RLatLon0.0225",
        data_format="nc",
        time_kind="ensemble_analysis",
        interval_start=datetime(2026, 7, 19, 0, tzinfo=UTC),
        interval_end=valid_time,
        accumulation_hours=6,
        analysis_revision=revision,
    )


def _payload(variable: str = "q025", bands: int = 1) -> str:
    return json.dumps(
        {
            "driverShortName": "netCDF",
            "size": [2438, 1188],
            "coordinateSystem": {"wkt": "PROJCRS[fixture]"},
            "wgs84Extent": {"type": "Polygon", "coordinates": []},
            "metadata": {
                "": {"time#units": "hours since 2026-07-19 06:00:00"}
            },
            "bands": [
                {
                    "noDataValue": 9.96921e36,
                    "metadata": {
                        "": {
                            "NETCDF_VARNAME": variable,
                            "units": "kg.m-2",
                        }
                    },
                }
                for _ in range(bands)
            ],
        }
    )


def test_hrepa_variable_selection_distinguishes_members_and_percentiles() -> None:
    assert hrepa_variable_name(_parsed("ensemble_members")) == "Precip-Accum06h"
    assert hrepa_variable_name(_parsed("percentile_25")) == "q025"
    assert hrepa_variable_name(_parsed("percentile_75")) == "q075"


def test_netcdf_metadata_validation_checks_time_grid_units_and_band_count() -> None:
    parsed = _parsed()
    inspection = parse_gdalinfo_netcdf(
        _payload(),
        dataset_name='NETCDF:"fixture.nc":q025',
        variable_name="q025",
    )

    validate_hrepa_netcdf_content(
        inspection,
        parsed,
        expected_dimensions=(2438, 1188),
        expected_unit="kg/m^2",
    )
    with pytest.raises(NetcdfValidationError, match="25"):
        validate_hrepa_netcdf_content(
            inspection,
            _parsed("ensemble_members"),
            expected_dimensions=(2438, 1188),
            expected_unit="kg/m^2",
        )


class _NetcdfRunner:
    def run(self, args: Sequence[str], *, timeout_seconds: float) -> CommandResult:
        del timeout_seconds
        return CommandResult(tuple(args), 0, _payload(), "")


def test_gdal_netcdf_inspector_uses_a_bounded_subdataset_name(tmp_path: Path) -> None:
    source = tmp_path / "fixture.nc"
    source.write_bytes(b"fixture")

    inspection = GdalNetcdfInspector(_NetcdfRunner()).inspect(
        source,
        variable_name="q025",
    )

    assert inspection.dataset_name == f'NETCDF:"{source}":q025'
    assert inspection.band_count == 1
