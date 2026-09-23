"""GDAL-backed validation and raster selection for reviewed NetCDF products."""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from weather_ingest.grib import (
    CommandResult,
    SubprocessCommandRunner,
    ToolUnavailableError,
)
from weather_ingest.models import ParsedSourceObject


class NetcdfValidationError(ValueError):
    pass


class NetcdfCommandRunner(Protocol):
    def run(self, args: Sequence[str], *, timeout_seconds: float) -> CommandResult: ...


@dataclass(frozen=True, slots=True)
class NetcdfRasterInspection:
    dataset_name: str
    variable_name: str
    width: int
    height: int
    band_count: int
    nodata_value: float | None
    units: str | None
    coordinate_system: str
    valid_time: datetime


_TIME_UNITS_RE = re.compile(
    r"^hours since (?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})$"
)


def hrepa_variable_name(parsed: ParsedSourceObject) -> str:
    """Map reviewed HREPA file semantics to the raster variable inside NetCDF."""

    variables = {
        "ensemble_members": "Precip-Accum06h",
        "percentile_25": "q025",
        "percentile_75": "q075",
    }
    try:
        return variables[str(parsed.analysis_revision)]
    except KeyError as exc:
        raise NetcdfValidationError(
            f"unsupported HREPA analysis revision: {parsed.analysis_revision!r}"
        ) from exc


def _metadata_value(payload: dict[str, Any], key: str) -> str | None:
    metadata = payload.get("metadata", {}).get("", {})
    if not isinstance(metadata, dict):
        return None
    value = metadata.get(key)
    return str(value) if value is not None else None


def parse_gdalinfo_netcdf(
    payload: str,
    *,
    dataset_name: str,
    variable_name: str,
) -> NetcdfRasterInspection:
    try:
        data: Any = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise NetcdfValidationError("gdalinfo returned invalid NetCDF JSON") from exc
    if not isinstance(data, dict) or data.get("driverShortName") != "netCDF":
        raise NetcdfValidationError("selected source is not a NetCDF raster")

    size = data.get("size")
    bands = data.get("bands")
    coordinate_system = data.get("coordinateSystem")
    if (
        not isinstance(size, list)
        or len(size) != 2
        or not all(isinstance(value, int) and value > 0 for value in size)
    ):
        raise NetcdfValidationError("NetCDF raster dimensions are invalid")
    if not isinstance(bands, list) or not bands:
        raise NetcdfValidationError("NetCDF variable contains no raster bands")
    if not isinstance(coordinate_system, dict) or not coordinate_system.get("wkt"):
        raise NetcdfValidationError("NetCDF variable has no coordinate reference system")
    if not data.get("wgs84Extent"):
        raise NetcdfValidationError("NetCDF variable has no WGS84 extent")

    first_band = bands[0]
    if not isinstance(first_band, dict):
        raise NetcdfValidationError("NetCDF band metadata is invalid")
    band_metadata = first_band.get("metadata", {}).get("", {})
    if not isinstance(band_metadata, dict):
        band_metadata = {}
    observed_variable = band_metadata.get("NETCDF_VARNAME")
    if observed_variable != variable_name:
        raise NetcdfValidationError(
            f"NetCDF variable {observed_variable!r} does not match {variable_name!r}"
        )

    time_units = _metadata_value(data, "time#units")
    match = _TIME_UNITS_RE.fullmatch(time_units or "")
    if match is None:
        raise NetcdfValidationError("NetCDF validity-time units are missing or invalid")
    valid_time = datetime.strptime(
        match.group("timestamp"), "%Y-%m-%d %H:%M:%S"
    ).replace(tzinfo=UTC)

    nodata = first_band.get("noDataValue")
    units = band_metadata.get("units")
    return NetcdfRasterInspection(
        dataset_name=dataset_name,
        variable_name=variable_name,
        width=size[0],
        height=size[1],
        band_count=len(bands),
        nodata_value=float(nodata) if nodata is not None else None,
        units=str(units) if units is not None else None,
        coordinate_system=str(coordinate_system["wkt"]),
        valid_time=valid_time,
    )


class GdalNetcdfInspector:
    def __init__(
        self,
        runner: NetcdfCommandRunner | None = None,
        *,
        executable: str = "gdalinfo",
        timeout_seconds: float = 120.0,
    ) -> None:
        self.runner = runner or SubprocessCommandRunner()
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    def inspect(
        self,
        path: Path | str,
        *,
        variable_name: str,
    ) -> NetcdfRasterInspection:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(source)
        if isinstance(self.runner, SubprocessCommandRunner) and shutil.which(
            self.executable
        ) is None:
            raise ToolUnavailableError(
                f"required GDAL tool is unavailable: {self.executable}"
            )
        dataset_name = f'NETCDF:"{source}":{variable_name}'
        result = self.runner.run(
            (self.executable, "-json", dataset_name),
            timeout_seconds=self.timeout_seconds,
        )
        if result.returncode:
            raise NetcdfValidationError(
                f"gdalinfo NetCDF inspection failed ({result.returncode}): "
                f"{result.stderr.strip()}"
            )
        return parse_gdalinfo_netcdf(
            result.stdout,
            dataset_name=dataset_name,
            variable_name=variable_name,
        )


def validate_hrepa_netcdf_content(
    inspection: NetcdfRasterInspection,
    parsed: ParsedSourceObject,
    *,
    expected_dimensions: tuple[int, int],
    expected_unit: str,
) -> None:
    if parsed.product_code != "hrepa" or parsed.data_format != "nc":
        raise NetcdfValidationError("NetCDF validation received a non-HREPA object")
    if inspection.valid_time != parsed.valid_time.astimezone(UTC):
        raise NetcdfValidationError(
            "NetCDF validity time does not match the registered analysis time"
        )
    if (inspection.width, inspection.height) != expected_dimensions:
        raise NetcdfValidationError(
            f"NetCDF dimensions {inspection.width}x{inspection.height} do not match "
            f"configured {expected_dimensions[0]}x{expected_dimensions[1]}"
        )
    expected_bands = 25 if parsed.analysis_revision == "ensemble_members" else 1
    if inspection.band_count != expected_bands:
        raise NetcdfValidationError(
            f"NetCDF variable has {inspection.band_count} bands; expected {expected_bands}"
        )
    normalized_unit = (
        (inspection.units or "")
        .replace("kg.m-2", "kg/m^2")
        .replace("kg m-2", "kg/m^2")
    )
    if normalized_unit != expected_unit:
        raise NetcdfValidationError(
            f"NetCDF units {inspection.units!r} do not match {expected_unit!r}"
        )
