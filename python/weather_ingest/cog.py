"""Restricted GDAL COG command planning, validation, and atomic publication."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from weather_ingest.config import FieldConfig
from weather_ingest.grib import CommandResult, SubprocessCommandRunner, ToolUnavailableError
from weather_ingest.units import GDAL_CALC_EXPRESSIONS


class CogValidationError(ValueError):
    pass


class CogCommandRunner(Protocol):
    def run(self, args: Sequence[str], *, timeout_seconds: float) -> CommandResult: ...


@dataclass(frozen=True, slots=True)
class CogOptions:
    block_size: int = 512
    compression: str = "ZSTD"
    compression_level: int = 9
    big_tiff: str = "IF_SAFER"
    threads: int = 2

    def __post_init__(self) -> None:
        if self.block_size not in {128, 256, 512, 1024}:
            raise ValueError("COG block_size must be a supported power-of-two tile size")
        if self.compression not in {"ZSTD", "DEFLATE"}:
            raise ValueError("COG compression must be ZSTD or DEFLATE")
        if not 1 <= self.threads <= 8:
            raise ValueError("COG threads must be bounded between 1 and 8")


DEFAULT_COG_OPTIONS = CogOptions()


@dataclass(frozen=True, slots=True)
class CogCommandPlan:
    commands: tuple[tuple[str, ...], ...]
    intermediate_path: Path | None
    staging_path: Path
    final_path: Path


@dataclass(frozen=True, slots=True)
class CogMetadata:
    width: int
    height: int
    band_count: int
    nodata_value: float | None
    coordinate_system: str
    compression: str | None
    wgs84_bounds: tuple[float, float, float, float] | None
    minimum_value: float | None
    maximum_value: float | None


def _wgs84_bounds(data: dict[str, Any]) -> tuple[float, float, float, float] | None:
    extent = data.get("wgs84Extent")
    if not isinstance(extent, dict):
        return None
    coordinates = extent.get("coordinates")
    points: list[tuple[float, float]] = []

    def collect(value: Any) -> None:
        if (
            isinstance(value, list)
            and len(value) >= 2
            and isinstance(value[0], (int, float))
            and isinstance(value[1], (int, float))
        ):
            points.append((float(value[0]), float(value[1])))
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(coordinates)
    if not points:
        return None
    longitudes = [point[0] for point in points]
    latitudes = [point[1] for point in points]
    return min(longitudes), min(latitudes), max(longitudes), max(latitudes)


def build_cog_command_plan(
    source_path: Path | str,
    staging_path: Path | str,
    final_path: Path | str,
    field: FieldConfig,
    *,
    source_dataset: str | None = None,
    options: CogOptions = DEFAULT_COG_OPTIONS,
) -> CogCommandPlan:
    source = Path(source_path)
    staging = Path(staging_path)
    final = Path(final_path)
    expression = GDAL_CALC_EXPRESSIONS[field.conversion_key]
    commands: list[tuple[str, ...]] = []
    translate_source: Path | str = source_dataset or source
    intermediate: Path | None = None
    if expression is not None:
        intermediate = staging.with_name(staging.name + ".normalized.tif")
        calculation = ["gdal_calc.py", "-A", str(source)]
        if field.source_band is not None:
            calculation.append(f"--A_band={field.source_band}")
        calculation.extend(
            (
                f"--outfile={intermediate}",
                f"--calc={expression}",
                f"--NoDataValue={field.nodata_value}",
                f"--type={field.output_data_type}",
                "--format=GTiff",
                "--overwrite",
                "--quiet",
            )
        )
        commands.append(tuple(calculation))
        translate_source = intermediate
    translation = [
        "gdal_translate",
        "-of",
        "COG",
        "-ot",
        field.output_data_type,
    ]
    if field.source_band is not None and intermediate is None:
        translation.extend(("-b", str(field.source_band)))
    translation.extend(
        (
            "-a_nodata",
            str(field.nodata_value),
            "-r",
            field.resampling,
            "-co",
            f"BLOCKSIZE={options.block_size}",
            "-co",
            f"COMPRESS={options.compression}",
            "-co",
            f"LEVEL={options.compression_level}",
            "-co",
            f"BIGTIFF={options.big_tiff}",
            "-co",
            f"NUM_THREADS={options.threads}",
            str(translate_source),
            str(staging),
        )
    )
    commands.append(tuple(translation))
    return CogCommandPlan(tuple(commands), intermediate, staging, final)


def parse_gdalinfo_cog(payload: str) -> CogMetadata:
    try:
        data: Any = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise CogValidationError("gdalinfo returned invalid JSON") from exc
    if not isinstance(data, dict) or data.get("driverShortName") != "GTiff":
        raise CogValidationError("output is not a GeoTIFF")
    size = data.get("size")
    bands = data.get("bands")
    coordinate_system = data.get("coordinateSystem")
    image_structure = data.get("metadata", {}).get("IMAGE_STRUCTURE", {})
    if (
        not isinstance(size, list)
        or len(size) != 2
        or not all(isinstance(value, int) and value > 0 for value in size)
    ):
        raise CogValidationError("COG has invalid raster dimensions")
    if not isinstance(bands, list) or not bands:
        raise CogValidationError("COG has no bands")
    if not isinstance(coordinate_system, dict) or not coordinate_system.get("wkt"):
        raise CogValidationError("COG has no coordinate reference system")
    if image_structure.get("LAYOUT") != "COG":
        raise CogValidationError("GeoTIFF is not marked with COG layout")
    nodata = bands[0].get("noDataValue") if isinstance(bands[0], dict) else None
    first_band = bands[0]
    minimum = first_band.get("minimum") if isinstance(first_band, dict) else None
    maximum = first_band.get("maximum") if isinstance(first_band, dict) else None
    statistics = first_band.get("metadata", {}).get("", {}) if isinstance(first_band, dict) else {}
    if minimum is None and isinstance(statistics, dict):
        minimum = statistics.get("STATISTICS_MINIMUM")
    if maximum is None and isinstance(statistics, dict):
        maximum = statistics.get("STATISTICS_MAXIMUM")
    return CogMetadata(
        width=size[0],
        height=size[1],
        band_count=len(bands),
        nodata_value=float(nodata) if nodata is not None else None,
        coordinate_system=coordinate_system["wkt"],
        compression=image_structure.get("COMPRESSION"),
        wgs84_bounds=_wgs84_bounds(data),
        minimum_value=float(minimum) if minimum is not None else None,
        maximum_value=float(maximum) if maximum is not None else None,
    )


class GdalCogPipeline:
    def __init__(
        self,
        runner: CogCommandRunner | None = None,
        *,
        timeout_seconds: float = 900.0,
        options: CogOptions = DEFAULT_COG_OPTIONS,
    ) -> None:
        self.runner = runner or SubprocessCommandRunner()
        self.timeout_seconds = timeout_seconds
        self.options = options

    def create(
        self,
        source_path: Path | str,
        staging_path: Path | str,
        final_path: Path | str,
        field: FieldConfig,
        *,
        source_dataset: str | None = None,
        replace_existing: bool = False,
    ) -> CogMetadata:
        source = Path(source_path)
        staging = Path(staging_path)
        final = Path(final_path)
        if not source.is_file():
            raise FileNotFoundError(source)
        final.parent.mkdir(parents=True, exist_ok=True)
        staging.parent.mkdir(parents=True, exist_ok=True)
        if final.exists() and not replace_existing:
            try:
                return self.validate(final)
            except CogValidationError:
                # A prior interrupted/older publication may have left a TIFF
                # without its GDAL persistent-auxiliary metadata. Rebuild it
                # from the retained raw source instead of making retries fail
                # forever on the same invalid output.
                final.unlink()
                self._sidecar(final).unlink(missing_ok=True)
        elif final.exists():
            final.unlink()
            self._sidecar(final).unlink(missing_ok=True)
        plan = build_cog_command_plan(
            source,
            staging,
            final,
            field,
            source_dataset=source_dataset,
            options=self.options,
        )
        self._check_tools(plan)
        self._remove_with_sidecar(staging)
        if plan.intermediate_path is not None:
            self._remove_with_sidecar(plan.intermediate_path)
        try:
            for command in plan.commands:
                result = self.runner.run(command, timeout_seconds=self.timeout_seconds)
                if result.returncode:
                    raise RuntimeError(
                        f"COG command {command[0]} failed ({result.returncode}): "
                        f"{result.stderr.strip()}"
                    )
            self.validate(staging)
            staging_sidecar = self._sidecar(staging)
            final_sidecar = self._sidecar(final)
            if staging_sidecar.is_file():
                os.replace(staging_sidecar, final_sidecar)
            else:
                final_sidecar.unlink(missing_ok=True)
            os.replace(staging, final)
            return self.validate(final)
        finally:
            self._remove_with_sidecar(staging)
            if plan.intermediate_path is not None:
                self._remove_with_sidecar(plan.intermediate_path)

    def validate(self, path: Path | str) -> CogMetadata:
        result = self.runner.run(
            ("gdalinfo", "-json", "-stats", str(Path(path))),
            timeout_seconds=self.timeout_seconds,
        )
        if result.returncode:
            raise CogValidationError(f"gdalinfo failed: {result.stderr.strip()}")
        return parse_gdalinfo_cog(result.stdout)

    def _check_tools(self, plan: CogCommandPlan) -> None:
        if not isinstance(self.runner, SubprocessCommandRunner):
            return
        required = {command[0] for command in plan.commands} | {"gdalinfo"}
        missing = sorted(tool for tool in required if shutil.which(tool) is None)
        if missing:
            raise ToolUnavailableError(f"required GDAL tools are unavailable: {', '.join(missing)}")

    @staticmethod
    def _sidecar(path: Path) -> Path:
        return Path(str(path) + ".aux.xml")

    @classmethod
    def _remove_with_sidecar(cls, path: Path) -> None:
        path.unlink(missing_ok=True)
        cls._sidecar(path).unlink(missing_ok=True)
