"""Validate FLEXPART smoke NetCDF and derive map-ready Cloud-Optimized GeoTIFFs."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np
import rasterio
from rasterio.shutil import copy as raster_copy
from rasterio.transform import from_origin

from weather_ingest.cffeps import EmissionRow

SPECIES_FIELDS = {
    "PM25_FIRE": "wildfire_pm25_surface",
    "CO": "wildfire_co_surface",
    "BC": "wildfire_bc_surface",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _finite_nonnegative(variable: netCDF4.Variable) -> np.ndarray:
    values = np.ma.asarray(variable[:])
    compressed = values.compressed()
    if not np.all(np.isfinite(compressed)) or np.any(compressed < 0):
        raise ValueError(f"FLEXPART variable {variable.name} is non-finite or negative")
    return values.filled(0.0)


def validate_flexpart_output(path: Path, *, expected_hours: int = 24) -> dict[str, Any]:
    with netCDF4.Dataset(path) as dataset:
        required_dimensions = {"time", "longitude", "latitude", "height", "numspec"}
        if required_dimensions - dataset.dimensions.keys():
            raise ValueError("FLEXPART NetCDF lacks required dimensions")
        if len(dataset.dimensions["time"]) != expected_hours:
            raise ValueError("FLEXPART NetCDF has an unexpected output-time count")
        longitude = np.asarray(dataset.variables["longitude"][:], dtype=float)
        latitude = np.asarray(dataset.variables["latitude"][:], dtype=float)
        height = np.asarray(dataset.variables["height"][:], dtype=float)
        if np.any(np.diff(longitude) <= 0) or np.any(np.diff(latitude) <= 0):
            raise ValueError("FLEXPART horizontal coordinates are not monotonic")
        if np.any(np.diff(height) <= 0):
            raise ValueError("FLEXPART height coordinate is not monotonic")
        concentration_names = sorted(
            name for name in dataset.variables if name.startswith("spec") and name.endswith("_mr")
        )
        if len(concentration_names) != len(dataset.dimensions["numspec"]):
            raise ValueError("FLEXPART species variables do not match numspec")
        summary: dict[str, Any] = {
            "time_count": expected_hours,
            "bounds": [
                float(longitude.min()),
                float(latitude.min()),
                float(longitude.max()),
                float(latitude.max()),
            ],
            "species": {},
        }
        for name in concentration_names:
            variable = dataset.variables[name]
            values = _finite_nonnegative(variable)
            species = str(variable.long_name).strip()
            summary["species"][species] = {
                "units": str(variable.units),
                "maximum": float(values.max()),
                "nonzero_cells": int(np.count_nonzero(values)),
            }
            for prefix in ("WD_", "DD_"):
                deposition_name = prefix + name.removesuffix("_mr")
                if deposition_name not in dataset.variables:
                    raise ValueError(f"FLEXPART output lacks {deposition_name}")
                _finite_nonnegative(dataset.variables[deposition_name])
        return summary


def _write_cog(
    path: Path,
    values: np.ndarray,
    longitude: np.ndarray,
    latitude: np.ndarray,
    *,
    unit: str,
    field: str,
    valid_time: datetime,
) -> dict[str, Any]:
    if values.shape != (len(latitude), len(longitude)):
        raise ValueError("display raster has wrong dimensions")
    dx = float(np.median(np.diff(longitude)))
    dy = float(np.median(np.diff(latitude)))
    transform = from_origin(float(longitude.min() - dx / 2), float(latitude.max() + dy / 2), dx, dy)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".working.tif")
    source_tiff = path.with_suffix(".source.tif")
    profile = {
        "driver": "GTiff",
        "height": len(latitude),
        "width": len(longitude),
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": transform,
        "nodata": -9999.0,
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
        "compress": "ZSTD",
    }
    with rasterio.open(source_tiff, "w", **profile) as destination:
        output_values = np.where(np.isfinite(values), values, -9999.0)
        destination.write(np.flipud(output_values).astype("float32"), 1)
        destination.update_tags(
            field=field,
            unit=unit,
            valid_time=valid_time.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            caveat="Research estimate of primary wildfire emissions; not a regulatory forecast",
        )
    raster_copy(source_tiff, temporary, driver="COG", compress="ZSTD", blocksize=256)
    source_tiff.unlink()
    temporary.replace(path)
    with rasterio.open(path) as source:
        if source.driver != "GTiff" or source.crs.to_epsg() != 4326 or source.count != 1:
            raise ValueError("generated smoke COG failed validation")
    return {
        "relative_path": path.as_posix(),
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
        "field": field,
        "unit": unit,
        "valid_time": valid_time.astimezone(UTC).isoformat().replace("+00:00", "Z"),
    }


def derive_smoke_cogs(
    netcdf_path: Path, output_dir: Path, *, expected_hours: int = 24
) -> dict[str, Any]:
    validation = validate_flexpart_output(
        netcdf_path, expected_hours=expected_hours
    )
    assets: list[dict[str, Any]] = []
    with netCDF4.Dataset(netcdf_path) as dataset:
        longitude = np.asarray(dataset.variables["longitude"][:], dtype=float)
        latitude = np.asarray(dataset.variables["latitude"][:], dtype=float)
        heights = np.asarray(dataset.variables["height"][:], dtype=float)
        time_variable = dataset.variables["time"]
        times = netCDF4.num2date(
            time_variable[:],
            time_variable.units,
            calendar=getattr(time_variable, "calendar", "standard"),
            only_use_cftime_datetimes=False,
        )
        for variable_name in sorted(
            name for name in dataset.variables if name.startswith("spec") and name.endswith("_mr")
        ):
            variable = dataset.variables[variable_name]
            species = str(variable.long_name).strip()
            if species not in SPECIES_FIELDS:
                raise ValueError(f"unmapped FLEXPART species {species}")
            field = SPECIES_FIELDS[species]
            values = _finite_nonnegative(variable)[0, 0]
            for index, raw_time in enumerate(times):
                valid_time = datetime(
                    raw_time.year,
                    raw_time.month,
                    raw_time.day,
                    raw_time.hour,
                    raw_time.minute,
                    raw_time.second,
                    tzinfo=UTC,
                )
                surface = values[index, 0] / 1000.0  # ng m-3 to ug m-3
                filename = f"{field}_{valid_time:%Y%m%dT%H%M%SZ}.tif"
                assets.append(
                    _write_cog(
                        output_dir / filename,
                        surface,
                        longitude,
                        latitude,
                        unit="ug m-3",
                        field=field,
                        valid_time=valid_time,
                    )
                )
                if species == "PM25_FIRE":
                    layer_thickness = np.diff(np.concatenate(([0.0], heights)))
                    column = np.sum(values[index] * layer_thickness[:, None, None], axis=0) * 1e-6
                    column_field = "wildfire_pm25_column"
                    assets.append(
                        _write_cog(
                            output_dir / f"{column_field}_{valid_time:%Y%m%dT%H%M%SZ}.tif",
                            column,
                            longitude,
                            latitude,
                            unit="mg m-2",
                            field=column_field,
                            valid_time=valid_time,
                        )
                    )
                    for prefix, deposition_field in (
                        ("WD_", "wildfire_pm25_wet_deposition"),
                        ("DD_", "wildfire_pm25_dry_deposition"),
                    ):
                        deposition = (
                            _finite_nonnegative(
                                dataset.variables[prefix + variable_name.removesuffix("_mr")]
                            )[0, 0, index]
                            * 1e-6
                        )
                        assets.append(
                            _write_cog(
                                output_dir / f"{deposition_field}_{valid_time:%Y%m%dT%H%M%SZ}.tif",
                                deposition,
                                longitude,
                                latitude,
                                unit="mg m-2",
                                field=deposition_field,
                                valid_time=valid_time,
                            )
                        )
    manifest = {
        "schema_version": 1,
        "source_netcdf_sha256": _sha256(netcdf_path),
        "validation": validation,
        "asset_count": len(assets),
        "assets": assets,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return manifest


def derive_injection_height_cogs(
    rows: list[EmissionRow], reference_netcdf: Path, output_dir: Path
) -> dict[str, Any]:
    """Create source-grid, mass-weighted plume injection-height diagnostics."""

    if not rows:
        raise ValueError("cannot derive injection heights from an empty emission bundle")
    represented_species = {row.species for row in rows}
    selected_species = "PM25" if "PM25" in represented_species else sorted(represented_species)[0]
    assets: list[dict[str, Any]] = []
    with netCDF4.Dataset(reference_netcdf) as dataset:
        longitude = np.asarray(dataset.variables["longitude"][:], dtype=float)
        latitude = np.asarray(dataset.variables["latitude"][:], dtype=float)
        time_variable = dataset.variables["time"]
        times = netCDF4.num2date(
            time_variable[:],
            time_variable.units,
            calendar=getattr(time_variable, "calendar", "standard"),
            only_use_cftime_datetimes=False,
        )
        for raw_time in times:
            valid_time = datetime(
                raw_time.year,
                raw_time.month,
                raw_time.day,
                raw_time.hour,
                raw_time.minute,
                raw_time.second,
                tzinfo=UTC,
            )
            weighted_height = np.zeros((len(latitude), len(longitude)), dtype=float)
            mass = np.zeros_like(weighted_height)
            for row in rows:
                if row.species != selected_species or row.source_time_end != valid_time:
                    continue
                y_index = int(np.abs(latitude - row.latitude).argmin())
                x_index = int(np.abs(longitude - row.longitude).argmin())
                layer_height = (row.vertical_layer_bottom_m_agl + row.vertical_layer_top_m_agl) / 2
                weighted_height[y_index, x_index] += row.emitted_mass_kg * layer_height
                mass[y_index, x_index] += row.emitted_mass_kg
            values = np.full_like(mass, np.nan)
            np.divide(weighted_height, mass, out=values, where=mass > 0)
            field = "wildfire_injection_height"
            assets.append(
                _write_cog(
                    output_dir / f"{field}_{valid_time:%Y%m%dT%H%M%SZ}.tif",
                    values,
                    longitude,
                    latitude,
                    unit="m",
                    field=field,
                    valid_time=valid_time,
                )
            )
    manifest = {
        "schema_version": 1,
        "diagnostic": "emission_mass_weighted_vertical_layer_midpoint",
        "represented_species": selected_species,
        "asset_count": len(assets),
        "assets": assets,
    }
    (output_dir / "injection-height-manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return manifest
