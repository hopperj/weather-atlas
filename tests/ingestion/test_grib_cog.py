import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from weather_ingest.cog import (
    CogValidationError,
    GdalCogPipeline,
    build_cog_command_plan,
    parse_gdalinfo_cog,
)
from weather_ingest.config import load_product_config
from weather_ingest.grib import (
    CommandResult,
    EcCodesCliInspector,
    GribMessageMetadata,
    GribMetadataInspection,
    GribValidationError,
    validate_grib2_envelopes,
    validate_grib_content,
)
from weather_ingest.models import ParsedSourceObject, RemoteObject

PROJECT_ROOT = Path(__file__).parents[2]


def _grib2_message(payload: bytes = b"") -> bytes:
    length = 16 + len(payload) + 4
    return b"GRIB" + b"\x00\x00\x00\x02" + length.to_bytes(8, "big") + payload + b"7777"


def test_basic_grib_validation_handles_multiple_messages_and_corruption(tmp_path: Path) -> None:
    valid = tmp_path / "valid.grib2"
    valid.write_bytes(_grib2_message(b"one") + _grib2_message(b"two"))

    inspection = validate_grib2_envelopes(valid)

    assert inspection.message_count == 2
    invalid = tmp_path / "invalid.grib2"
    invalid.write_bytes(_grib2_message()[:-1] + b"x")
    with pytest.raises(GribValidationError, match="trailer"):
        validate_grib2_envelopes(invalid)


class _MetadataRunner:
    def run(self, args: Sequence[str], *, timeout_seconds: float) -> CommandResult:
        del timeout_seconds
        payload = [
            {
                "shortName": "2t",
                "typeOfLevel": "heightAboveGround",
                "level": 2,
                "units": "K",
                "dataDate": 20260716,
                "dataTime": 1200,
                "stepRange": "6",
                "endStep": 6,
                "stepUnits": 1,
                "validityDate": 20260716,
                "validityTime": 1800,
                "gridType": "rotated_ll",
                "Ni": 2540,
                "Nj": 1290,
                "numberOfDataPoints": 3276600,
            }
        ]
        return CommandResult(tuple(args), 0, json.dumps(payload), "")


def test_eccodes_metadata_inspection_is_runner_injectable() -> None:
    inspection = EcCodesCliInspector(_MetadataRunner()).inspect("fixture.grib2")

    assert inspection.messages[0].short_name == "2t"
    assert inspection.messages[0].data_time == 1200
    assert inspection.messages[0].grid_width == 2540


def _parsed_temperature(*, forecast_hour: int = 6) -> ParsedSourceObject:
    initialization = datetime(2026, 7, 16, 12, tzinfo=UTC)
    filename = (
        "20260716T12Z_MSC_HRDPS_TMP_AGL-2m_"
        f"RLatLon0.0225_PT{forecast_hour:03d}H.grib2"
    )
    return ParsedSourceObject(
        remote=RemoteObject(f"https://dd.weather.gc.ca/{filename}", filename),
        product_code="hrdps",
        producer="HRDPS",
        domain_code="continental",
        initialization_time=initialization,
        valid_time=initialization + timedelta(hours=forecast_hour),
        forecast_hour=forecast_hour,
        parameter="TMP",
        source_level="AGL-2m",
        grid="RLatLon0.0225",
        data_format="grib2",
    )


def _metadata_message() -> GribMessageMetadata:
    return GribMessageMetadata(
        # Local definitions may be unavailable to ecCodes. These fields must
        # remain informational rather than rejecting an otherwise valid object.
        short_name="unknown",
        type_of_level="heightAboveGround",
        level="2",
        units="unknown",
        data_date=20260716,
        data_time=1200,
        step_range="6",
        end_step=6,
        step_units=1,
        validity_date=20260716,
        validity_time=1800,
        grid_type="rotated_ll",
        grid_width=2540,
        grid_height=1290,
        number_of_data_points=2540 * 1290,
    )


def _inspection(message: GribMessageMetadata) -> GribMetadataInspection:
    return GribMetadataInspection((message,), "fixture")


def test_content_validation_proves_temporal_and_grid_identity() -> None:
    result = validate_grib_content(
        _inspection(_metadata_message()),
        _parsed_temperature(),
        expected_grid="RLatLon0.0225",
        expected_dimensions=(2540, 1290),
    )

    assert result.forecast_hour == 6
    assert result.grid_type == "rotated_ll"
    assert (result.grid_width, result.grid_height) == (2540, 1290)


@pytest.mark.parametrize(
    ("message", "error"),
    [
        (replace(_metadata_message(), data_time=600), "initialization time"),
        (replace(_metadata_message(), validity_time=1900), "valid time"),
        (replace(_metadata_message(), end_step=5), "end step"),
        (replace(_metadata_message(), grid_type="regular_ll"), "grid type"),
        (replace(_metadata_message(), grid_width=2539), "grid dimensions"),
        (replace(_metadata_message(), number_of_data_points=None), "data points"),
    ],
)
def test_content_validation_rejects_mismatched_identity(
    message: GribMessageMetadata, error: str
) -> None:
    with pytest.raises(GribValidationError, match=error):
        validate_grib_content(
            _inspection(message),
            _parsed_temperature(),
            expected_grid="RLatLon0.0225",
            expected_dimensions=(2540, 1290),
        )


def test_content_validation_converts_eccodes_step_units() -> None:
    minute_step = replace(_metadata_message(), end_step=360, step_units=0)

    result = validate_grib_content(
        _inspection(minute_step),
        _parsed_temperature(),
        expected_grid="RLatLon0.0225",
        expected_dimensions=(2540, 1290),
    )

    assert result.forecast_hour == 6


def test_cog_plan_uses_gdal_decoded_temperature_in_bounded_cog_translation() -> None:
    config = load_product_config(PROJECT_ROOT / "config", "hrdps")
    field = config.field("air_temperature_2m")

    plan = build_cog_command_plan("source.grib2", "stage.tif.part", "final.tif", field)

    assert [command[0] for command in plan.commands] == ["gdal_translate"]
    assert "NUM_THREADS=2" in plan.commands[0]
    assert "ALL_CPUS" not in " ".join(plan.commands[0])


def test_gdalinfo_parser_requires_real_cog_layout_and_crs() -> None:
    payload = json.dumps(
        {
            "driverShortName": "GTiff",
            "size": [2540, 1290],
            "coordinateSystem": {"wkt": "PROJCRS[fixture]"},
            "metadata": {"IMAGE_STRUCTURE": {"LAYOUT": "COG", "COMPRESSION": "ZSTD"}},
            "bands": [{"noDataValue": -9999.0}],
        }
    )

    metadata = parse_gdalinfo_cog(payload)

    assert metadata.width == 2540
    assert metadata.compression == "ZSTD"
    with pytest.raises(CogValidationError, match="COG layout"):
        parse_gdalinfo_cog(payload.replace('"COG"', '"TILED"'))


class _CogPublicationRunner:
    def run(self, args: Sequence[str], *, timeout_seconds: float) -> CommandResult:
        del timeout_seconds
        if args[0] == "gdal_calc.py":
            output = Path(
                next(
                    value.removeprefix("--outfile=")
                    for value in args
                    if value.startswith("--outfile=")
                )
            )
            output.write_bytes(b"normalized")
            return CommandResult(tuple(args), 0, "", "")
        if args[0] == "gdal_translate":
            Path(args[-1]).write_bytes(b"cog")
            return CommandResult(tuple(args), 0, "", "")
        path = Path(args[-1])
        if path.name.endswith(".part"):
            Path(str(path) + ".aux.xml").write_text("<PAMDataset />")
        payload = json.dumps(
            {
                "driverShortName": "GTiff",
                "size": [2540, 1290],
                "coordinateSystem": {"wkt": "PROJCRS[fixture]"},
                "metadata": {"IMAGE_STRUCTURE": {"LAYOUT": "COG", "COMPRESSION": "ZSTD"}},
                "wgs84Extent": {
                    "coordinates": [[[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]]]
                },
                "bands": [
                    {
                        "noDataValue": -9999.0,
                        "minimum": -10.0,
                        "maximum": 20.0,
                    }
                ],
            }
        )
        return CommandResult(tuple(args), 0, payload, "")


def test_cog_publication_moves_gdal_sidecar_with_rotated_grid(tmp_path: Path) -> None:
    config = load_product_config(PROJECT_ROOT / "config", "hrdps")
    source = tmp_path / "source.grib2"
    staging = tmp_path / "stage.tif.part"
    final = tmp_path / "final.tif"
    source.write_bytes(b"grib")

    GdalCogPipeline(_CogPublicationRunner()).create(
        source, staging, final, config.field("air_temperature_2m")
    )

    assert final.read_bytes() == b"cog"
    assert Path(str(final) + ".aux.xml").read_text() == "<PAMDataset />"
    assert not Path(str(staging) + ".aux.xml").exists()
