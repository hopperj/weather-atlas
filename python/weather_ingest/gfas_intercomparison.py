"""Reproducible CFFEPS-to-GFAS inventory intercomparison pairs."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import sys
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np
from eccodes import (
    codes_get,
    codes_get_api_version,
    codes_get_array,
    codes_grib_new_from_file,
    codes_release,
)
from pyproj import Geod

SECONDS_PER_DAY = 86_400.0
SPECIES_TO_GFAS = {
    "PM25": "pm2p5fire",
    "CO": "cofire",
    "BC": "bcfire",
}


@dataclass(frozen=True, slots=True)
class RegularGrid:
    ni: int
    nj: int
    first_latitude: float
    first_longitude: float
    latitude_increment: float
    longitude_increment: float
    latitude_sign: int
    longitude_sign: int

    @classmethod
    def from_handle(cls, handle: int) -> RegularGrid:
        if int(codes_get(handle, "jPointsAreConsecutive")) != 0:
            raise ValueError("GFAS j-consecutive scanning is not supported")
        if int(codes_get(handle, "alternativeRowScanning")) != 0:
            raise ValueError("GFAS alternating-row scanning is not supported")
        return cls(
            ni=int(codes_get(handle, "Ni")),
            nj=int(codes_get(handle, "Nj")),
            first_latitude=float(codes_get(handle, "latitudeOfFirstGridPointInDegrees")),
            first_longitude=float(codes_get(handle, "longitudeOfFirstGridPointInDegrees")),
            latitude_increment=float(codes_get(handle, "jDirectionIncrementInDegrees")),
            longitude_increment=float(codes_get(handle, "iDirectionIncrementInDegrees")),
            latitude_sign=1 if int(codes_get(handle, "jScansPositively")) else -1,
            longitude_sign=-1 if int(codes_get(handle, "iScansNegatively")) else 1,
        )

    def latitudes(self) -> np.ndarray:
        return self.first_latitude + self.latitude_sign * self.latitude_increment * np.arange(
            self.nj
        )

    def longitudes(self) -> np.ndarray:
        return self.first_longitude + self.longitude_sign * self.longitude_increment * np.arange(
            self.ni
        )

    def canonical_longitudes(self) -> np.ndarray:
        return (self.longitudes() + 180.0) % 360.0 - 180.0

    def nearest_cell(self, latitude: float, longitude: float) -> tuple[int, int]:
        normalized_longitude = longitude % 360.0
        first_longitude = self.first_longitude % 360.0
        longitude_offset = (
            (normalized_longitude - first_longitude) % 360.0
        ) / self.longitude_increment
        if self.longitude_sign < 0:
            longitude_offset = (-longitude_offset) % self.ni
        latitude_offset = (latitude - self.first_latitude) / (
            self.latitude_sign * self.latitude_increment
        )
        # Points exactly on a cell boundary are assigned toward increasing
        # array index. The rule is deterministic and recorded in the manifest.
        i = int(math.floor(longitude_offset + 0.5 + 1e-10)) % self.ni
        j = int(math.floor(latitude_offset + 0.5 + 1e-10))
        if j < 0 or j >= self.nj:
            raise ValueError(f"latitude falls outside GFAS grid: {latitude}")
        return j, i

    def as_dict(self) -> dict[str, Any]:
        return {
            "ni": self.ni,
            "nj": self.nj,
            "first_latitude": self.first_latitude,
            "first_longitude": self.first_longitude,
            "latitude_increment": self.latitude_increment,
            "longitude_increment": self.longitude_increment,
            "latitude_sign": self.latitude_sign,
            "longitude_sign": self.longitude_sign,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_bbox(bbox: tuple[float, float, float, float]) -> None:
    west, south, east, north = bbox
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("bbox must be west,south,east,north without dateline wrapping")


def _bbox_indices(
    grid: RegularGrid, bbox: tuple[float, float, float, float]
) -> tuple[np.ndarray, np.ndarray]:
    _validate_bbox(bbox)
    west, south, east, north = bbox
    latitudes = grid.latitudes()
    longitudes = grid.canonical_longitudes()
    rows = np.flatnonzero((latitudes >= south) & (latitudes <= north))
    columns = np.flatnonzero((longitudes >= west) & (longitudes <= east))
    if rows.size == 0 or columns.size == 0:
        raise ValueError("bbox does not intersect GFAS grid-cell centres")
    return rows, columns


def _cell_area_m2(grid: RegularGrid, latitude: float, longitude: float) -> float:
    half_latitude = grid.latitude_increment / 2.0
    half_longitude = grid.longitude_increment / 2.0
    geod = Geod(ellps="WGS84")
    area, _ = geod.polygon_area_perimeter(
        [
            longitude - half_longitude,
            longitude + half_longitude,
            longitude + half_longitude,
            longitude - half_longitude,
        ],
        [
            latitude - half_latitude,
            latitude - half_latitude,
            latitude + half_latitude,
            latitude + half_latitude,
        ],
    )
    return abs(float(area))


def _text_array(variable: Any) -> list[str]:
    return [str(value) for value in variable[:].tolist()]


def _load_model_emissions(
    path: Path,
    species: tuple[str, ...],
    evaluation_dates: frozenset[date],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with netCDF4.Dataset(path) as dataset:
        required = {
            "event_id",
            "species",
            "source_time_start",
            "latitude",
            "longitude",
            "emitted_mass_kg",
        }
        missing = required.difference(dataset.variables)
        if missing:
            raise ValueError(f"emissions bundle is missing variables: {sorted(missing)}")
        event_ids = _text_array(dataset.variables["event_id"])
        row_species = _text_array(dataset.variables["species"])
        times = dataset.variables["source_time_start"][:]
        latitudes = dataset.variables["latitude"][:]
        longitudes = dataset.variables["longitude"][:]
        masses = dataset.variables["emitted_mass_kg"][:]
        for index, row_specie in enumerate(row_species):
            if row_specie not in species:
                continue
            day = datetime.fromtimestamp(int(times[index]), tz=UTC).date()
            if day not in evaluation_dates:
                continue
            mass = float(masses[index])
            if not math.isfinite(mass) or mass < 0:
                raise ValueError(f"invalid emitted mass on bundle row {index}")
            records.append(
                {
                    "day": day,
                    "species": row_specie,
                    "event_id": event_ids[index],
                    "latitude": float(latitudes[index]),
                    "longitude": float(longitudes[index]),
                    "mass_kg": mass,
                }
            )
    if not records:
        raise ValueError("emissions bundle has no requested rows in the evaluation interval")
    available_species = {record["species"] for record in records}
    missing_species = set(species).difference(available_species)
    if missing_species:
        raise ValueError(f"emissions bundle has no rows for species: {sorted(missing_species)}")
    return records, {
        "path": path.as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "selected_row_count": len(records),
    }


def _read_gfas(
    paths: Sequence[Path],
    species: tuple[str, ...],
    evaluation_dates: frozenset[date],
    bbox: tuple[float, float, float, float],
) -> tuple[
    RegularGrid,
    dict[str, dict[tuple[date, int, int], float]],
    dict[str, Any],
]:
    short_name_to_species = {SPECIES_TO_GFAS[name]: name for name in species}
    values_by_species: dict[str, dict[tuple[date, int, int], float]] = {
        name: {} for name in species
    }
    message_counts = defaultdict(int)
    grid: RegularGrid | None = None
    selected_rows: np.ndarray | None = None
    selected_columns: np.ndarray | None = None
    source_records = []
    for path in paths:
        source_records.append(
            {
                "path": path.as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
        with path.open("rb") as source:
            while True:
                handle = codes_grib_new_from_file(source)
                if handle is None:
                    break
                try:
                    short_name = str(codes_get(handle, "shortName"))
                    if short_name not in short_name_to_species:
                        continue
                    day_text = str(int(codes_get(handle, "dataDate")))
                    day = datetime.strptime(day_text, "%Y%m%d").date()
                    if day not in evaluation_dates:
                        continue
                    current_grid = RegularGrid.from_handle(handle)
                    if grid is None:
                        grid = current_grid
                        selected_rows, selected_columns = _bbox_indices(grid, bbox)
                    elif current_grid != grid:
                        raise ValueError("GFAS grid changed inside the selected message set")
                    assert selected_rows is not None and selected_columns is not None
                    raw = np.asarray(codes_get_array(handle, "values"), dtype=np.float64)
                    if raw.size != grid.ni * grid.nj:
                        raise ValueError("GFAS message value count does not match its grid")
                    selected = raw.reshape(grid.nj, grid.ni)[
                        np.ix_(selected_rows, selected_columns)
                    ]
                    if not np.all(np.isfinite(selected)) or np.any(selected < 0):
                        raise ValueError(f"GFAS contains invalid {short_name} values on {day}")
                    positive_j, positive_i = np.nonzero(selected > 0)
                    output = values_by_species[short_name_to_species[short_name]]
                    for subset_j, subset_i in zip(positive_j, positive_i, strict=True):
                        j = int(selected_rows[subset_j])
                        i = int(selected_columns[subset_i])
                        key = (day, j, i)
                        if key in output:
                            raise ValueError(f"duplicate GFAS {short_name} message for {day}")
                        output[key] = float(selected[subset_j, subset_i])
                    message_counts[short_name] += 1
                finally:
                    codes_release(handle)
    if grid is None:
        raise ValueError("GFAS contains no requested messages")
    expected_messages = len(evaluation_dates)
    for short_name in short_name_to_species:
        if message_counts[short_name] != expected_messages:
            raise ValueError(
                f"expected {expected_messages} {short_name} messages, "
                f"found {message_counts[short_name]}"
            )
    return (
        grid,
        values_by_species,
        {
            "files": source_records,
            "file_count": len(source_records),
            "total_size_bytes": sum(int(record["size_bytes"]) for record in source_records),
            "eccodes_api_version": codes_get_api_version(),
            "message_counts": dict(sorted(message_counts.items())),
        },
    )


def _write_pairs(
    path: Path,
    *,
    species: str,
    grid: RegularGrid,
    gfas_fluxes: dict[tuple[date, int, int], float],
    modelled: dict[tuple[date, int, int], float],
    events: dict[tuple[date, int, int], set[str]],
    numerical_zero_kg: float,
) -> dict[str, Any]:
    latitudes = grid.latitudes()
    longitudes = grid.canonical_longitudes()
    cell_areas = {
        j: _cell_area_m2(grid, float(latitudes[j]), float(longitudes[0]))
        for _, j, _ in set(gfas_fluxes) | set(modelled)
    }
    rows: list[dict[str, Any]] = []
    for key in sorted(set(gfas_fluxes) | set(modelled)):
        day, j, i = key
        flux = gfas_fluxes.get(key, 0.0)
        observed = flux * cell_areas[j] * SECONDS_PER_DAY
        candidate = modelled.get(key, 0.0)
        if observed <= numerical_zero_kg and candidate <= numerical_zero_kg:
            continue
        rows.append(
            {
                "observed": observed,
                "modelled": candidate,
                "date": day.isoformat(),
                "latitude": float(latitudes[j]),
                "longitude": float(longitudes[i]),
                "grid_row": j,
                "grid_column": i,
                "species": species,
                "gfas_flux_kg_m2_s": flux,
                "cell_area_m2": cell_areas[j],
                "event_id": ";".join(sorted(events.get(key, set()))),
            }
        )
    if not rows:
        raise ValueError(f"active-union filtering produced no {species} pairs")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.unlink(missing_ok=True)
    fields = (
        "observed",
        "modelled",
        "date",
        "latitude",
        "longitude",
        "grid_row",
        "grid_column",
        "species",
        "gfas_flux_kg_m2_s",
        "cell_area_m2",
        "event_id",
    )
    try:
        with temporary.open("x", newline="", encoding="utf-8") as destination:
            writer = csv.DictWriter(destination, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        **row,
                        "observed": format(row["observed"], ".17g"),
                        "modelled": format(row["modelled"], ".17g"),
                        "latitude": format(row["latitude"], ".8f"),
                        "longitude": format(row["longitude"], ".8f"),
                        "gfas_flux_kg_m2_s": format(row["gfas_flux_kg_m2_s"], ".17g"),
                        "cell_area_m2": format(row["cell_area_m2"], ".17g"),
                    }
                )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "path": path.as_posix(),
        "sha256": _sha256(path),
        "pair_count": len(rows),
        "gfas_total_kg": sum(float(row["observed"]) for row in rows),
        "cffeps_total_kg": sum(float(row["modelled"]) for row in rows),
        "gfas_positive_pair_count": sum(float(row["observed"]) > 0 for row in rows),
        "cffeps_positive_pair_count": sum(float(row["modelled"]) > 0 for row in rows),
    }


def build_gfas_pairs(
    *,
    emissions_path: Path,
    gfas_path: Path | Iterable[Path],
    output_directory: Path,
    start: date,
    end: date,
    bbox: tuple[float, float, float, float],
    species: Iterable[str] = SPECIES_TO_GFAS,
    evaluation_dates: Iterable[date] | None = None,
    reference_product: str = "gfas-v1.2",
    numerical_zero_kg: float = 1e-12,
    command: list[str] | None = None,
) -> dict[str, Any]:
    """Create species-specific, active-union grid-cell-day pair sets."""

    requested_species = tuple(dict.fromkeys(name.upper() for name in species))
    if not requested_species or any(name not in SPECIES_TO_GFAS for name in requested_species):
        raise ValueError(f"species must be selected from {sorted(SPECIES_TO_GFAS)}")
    if end < start:
        raise ValueError("end date must not precede start date")
    selected_dates = (
        frozenset(evaluation_dates)
        if evaluation_dates is not None
        else frozenset(
            date.fromordinal(ordinal) for ordinal in range(start.toordinal(), end.toordinal() + 1)
        )
    )
    if not selected_dates:
        raise ValueError("at least one evaluation date is required")
    if min(selected_dates) < start or max(selected_dates) > end:
        raise ValueError("evaluation dates must fall inside the declared interval")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", reference_product):
        raise ValueError("reference product must be a filesystem-safe lowercase label")
    if numerical_zero_kg < 0:
        raise ValueError("numerical zero must not be negative")
    _validate_bbox(bbox)

    model_records, model_source = _load_model_emissions(
        emissions_path, requested_species, selected_dates
    )
    gfas_paths = (
        (gfas_path,) if isinstance(gfas_path, Path) else tuple(Path(path) for path in gfas_path)
    )
    if not gfas_paths:
        raise ValueError("at least one GFAS file is required")
    grid, gfas_by_species, gfas_source = _read_gfas(
        gfas_paths, requested_species, selected_dates, bbox
    )
    west, south, east, north = bbox
    modelled: dict[str, dict[tuple[date, int, int], float]] = {
        name: defaultdict(float) for name in requested_species
    }
    events: dict[str, dict[tuple[date, int, int], set[str]]] = {
        name: defaultdict(set) for name in requested_species
    }
    for record in model_records:
        latitude = float(record["latitude"])
        longitude = float(record["longitude"])
        canonical_longitude = (longitude + 180.0) % 360.0 - 180.0
        if not (south <= latitude <= north and west <= canonical_longitude <= east):
            raise ValueError("evaluation bbox does not contain every selected CFFEPS emission row")
        key = (record["day"], *grid.nearest_cell(latitude, longitude))
        name = str(record["species"])
        modelled[name][key] += float(record["mass_kg"])
        events[name][key].add(str(record["event_id"]))

    output_directory.mkdir(parents=True, exist_ok=True)
    pair_sets = {}
    for name in requested_species:
        pair_sets[name] = _write_pairs(
            output_directory / f"{reference_product}-{name.lower()}-pairs.csv",
            species=name,
            grid=grid,
            gfas_fluxes=gfas_by_species[name],
            modelled=modelled[name],
            events=events[name],
            numerical_zero_kg=numerical_zero_kg,
        )
    manifest = {
        "schema_version": 1,
        "product": "cffeps_gfas_inventory_intercomparison_pairs",
        "reference_product": reference_product,
        "assessment_role": "diagnostic_inventory_intercomparison",
        "acceptance_capable": False,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "command": command if command is not None else sys.argv,
        "interval": {"start": start.isoformat(), "end_inclusive": end.isoformat()},
        "evaluation_dates": [day.isoformat() for day in sorted(selected_dates)],
        "bbox_wgs84": {"west": west, "south": south, "east": east, "north": north},
        "species": list(requested_species),
        "grid": grid.as_dict(),
        "cell_assignment": "nearest_gfas_cell_ties_toward_increasing_array_index_v1",
        "pair_selection": "active_union_after_numerical_zero_screen_v1",
        "gfas_conversion": "flux_kg_m2_s * WGS84_geodesic_cell_area_m2 * 86400_s",
        "numerical_zero_kg": numerical_zero_kg,
        "emissions_source": model_source,
        "gfas_source": gfas_source,
        "pair_sets": pair_sets,
    }
    manifest_path = output_directory / "manifest.json"
    _atomic_json(manifest_path, manifest)
    return manifest | {
        "manifest_path": manifest_path.as_posix(),
        "manifest_sha256": _sha256(manifest_path),
    }
