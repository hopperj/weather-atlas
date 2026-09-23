"""Extract and hourly-interpolate CFFEPS point profiles from a pinned GFS cycle."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

MET_LEVELS = 40
SURFACE_NAMES = ("sp", "2t", "2sh", "2d", "10u", "10v", "orog")


@dataclass(frozen=True, slots=True)
class AtmosphericProfile:
    valid_time: datetime
    latitude: float
    longitude: float
    specific_humidity_kg_kg: float
    wind_speed_knots: float
    dewpoint_k: float
    elevation_m: float
    pressure_pa: tuple[float, ...]
    temperature_k: tuple[float, ...]
    height_m_agl: tuple[float, ...]
    interpolation: str = "nearest-grid spatial; linear temporal; log-pressure vertical"

    def __post_init__(self) -> None:
        if self.valid_time.tzinfo is None:
            raise ValueError("profile time must be timezone-aware")
        if not all(
            len(values) == MET_LEVELS
            for values in (self.pressure_pa, self.temperature_k, self.height_m_agl)
        ):
            raise ValueError(f"profiles require exactly {MET_LEVELS} levels")
        if any(
            left <= right
            for left, right in zip(self.pressure_pa, self.pressure_pa[1:], strict=False)
        ):
            raise ValueError("pressure must strictly decrease")
        if any(
            left >= right
            for left, right in zip(self.height_m_agl, self.height_m_agl[1:], strict=False)
        ):
            raise ValueError("height must strictly increase")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["valid_time"] = self.valid_time.astimezone(UTC).isoformat().replace("+00:00", "Z")
        return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_complete_cycle(manifest_path: Path) -> tuple[dict[str, Any], list[Path]]:
    manifest_path = manifest_path.resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        payload.get("schema_version") != 1
        or payload.get("provider") != "noaa"
        or payload.get("product") != "gfs"
    ):
        raise ValueError("not a supported NOAA GFS manifest")
    expected_hours = payload.get("forecast_hours")
    files = payload.get("files")
    if not isinstance(expected_hours, list) or not isinstance(files, list):
        raise ValueError("incomplete GFS manifest")
    if sorted(item.get("forecast_hour") for item in files) != expected_hours:
        raise ValueError("GFS manifest does not contain one file per forecast hour")
    resolved: list[Path] = []
    for item in files:
        path = manifest_path.parent / item["filename"]
        if not path.is_file() or path.is_symlink() or path.stat().st_size != item["size_bytes"]:
            raise ValueError(f"missing or invalid GFS file {item['filename']}")
        if _sha256(path) != item["sha256"]:
            raise ValueError(f"GFS checksum mismatch for {item['filename']}")
        resolved.append(path)
    return payload, resolved


def _nearest_values(
    path: Path, latitude: float, longitude: float
) -> tuple[dict[str, float], dict[str, dict[int, float]]]:
    executable = shutil.which("grib_get")
    if executable is None:
        raise RuntimeError("ecCodes grib_get is required for GFS profile extraction")
    normalized_lon = longitude % 360.0

    def run(where: str) -> list[tuple[str, int, float]]:
        process = subprocess.run(
            [
                executable,
                "-l",
                f"{latitude},{normalized_lon},1",
                "-w",
                where,
                "-p",
                "shortName,level",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if process.returncode:
            raise RuntimeError(f"grib_get failed for {path.name}: {process.stderr.strip()}")
        rows: list[tuple[str, int, float]] = []
        for line in process.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 3:
                rows.append((parts[0], int(float(parts[1])), float(parts[2])))
        return rows

    surface_rows = run("shortName=" + "/".join(SURFACE_NAMES))
    surface = {name: value for name, _level, value in surface_rows}
    missing = set(SURFACE_NAMES) - surface.keys()
    if missing:
        raise ValueError(f"GFS file lacks required surface fields: {sorted(missing)}")
    # CFFEPS needs the pressure/temperature/height profile. Specific humidity
    # is the independently sampled near-surface scalar below; it is not read
    # from the pressure-level mapping. Historical GFS archives commonly carry
    # pressure-level relative humidity (r), rather than specific humidity (q),
    # so requiring q here rejected otherwise complete profiles even though the
    # value was never consumed.
    aloft_rows = run("typeOfLevel=isobaricInhPa,shortName=t/gh")
    aloft: dict[str, dict[int, float]] = {"t": {}, "gh": {}}
    for name, level, value in aloft_rows:
        aloft[name][level] = value
    common = set(aloft["t"]) & set(aloft["gh"])
    if len(common) < 20:
        raise ValueError("GFS file lacks a complete pressure-level profile")
    return surface, {
        name: {level: values[level] for level in common} for name, values in aloft.items()
    }


def _vertical_profile(
    valid_time: datetime,
    latitude: float,
    longitude: float,
    surface: dict[str, float],
    aloft: dict[str, dict[int, float]],
) -> AtmosphericProfile:
    source_levels = np.array(sorted(aloft["t"]), dtype=float)
    source_logp = np.log(source_levels * 100.0)
    order = np.argsort(source_logp)
    surface_pressure = max(surface["sp"], 50_000.0)
    top_pressure = max(10_000.0, min(source_levels) * 100.0)
    targets = np.geomspace(surface_pressure, top_pressure, MET_LEVELS)

    def interpolate(name: str) -> np.ndarray:
        values = np.array([aloft[name][int(level)] for level in source_levels], dtype=float)
        return np.interp(np.log(targets), source_logp[order], values[order])

    temperature = interpolate("t")
    height_asl = interpolate("gh")
    elevation = surface["orog"]
    height_agl = np.maximum(height_asl - elevation, 0.0)
    temperature[0] = surface["2t"]
    height_agl[0] = 2.0
    for index in range(1, MET_LEVELS):
        height_agl[index] = max(height_agl[index], height_agl[index - 1] + 1.0)
    wind_ms = math.hypot(surface["10u"], surface["10v"])
    return AtmosphericProfile(
        valid_time=valid_time,
        latitude=latitude,
        longitude=longitude,
        specific_humidity_kg_kg=surface["2sh"],
        wind_speed_knots=wind_ms * 1.9438444924406,
        dewpoint_k=surface["2d"],
        elevation_m=elevation,
        pressure_pa=tuple(float(value) for value in targets),
        temperature_k=tuple(float(value) for value in temperature),
        height_m_agl=tuple(float(value) for value in height_agl),
    )


def extract_cycle_profiles(
    manifest_path: Path, latitude: float, longitude: float
) -> tuple[list[AtmosphericProfile], dict[str, Any]]:
    manifest, paths = resolve_complete_cycle(manifest_path)
    initialization = datetime.fromisoformat(manifest["initialization_time"].replace("Z", "+00:00"))
    source_profiles: list[AtmosphericProfile] = []
    for file_entry, path in zip(manifest["files"], paths, strict=True):
        valid_time = initialization + timedelta(hours=file_entry["forecast_hour"])
        surface, aloft = _nearest_values(path, latitude, longitude)
        source_profiles.append(_vertical_profile(valid_time, latitude, longitude, surface, aloft))

    hourly: list[AtmosphericProfile] = []
    for offset in range(25):
        target = initialization + timedelta(hours=offset)
        if offset % 3 == 0:
            hourly.append(source_profiles[offset // 3])
            continue
        left = source_profiles[offset // 3]
        right = source_profiles[offset // 3 + 1]
        fraction = (offset % 3) / 3.0

        def blend(
            left_values: tuple[float, ...],
            right_values: tuple[float, ...],
            blend_fraction: float = fraction,
        ) -> tuple[float, ...]:
            return tuple(
                a + (b - a) * blend_fraction
                for a, b in zip(left_values, right_values, strict=True)
            )

        hourly.append(
            AtmosphericProfile(
                valid_time=target,
                latitude=latitude,
                longitude=longitude,
                specific_humidity_kg_kg=left.specific_humidity_kg_kg
                + (right.specific_humidity_kg_kg - left.specific_humidity_kg_kg) * fraction,
                wind_speed_knots=left.wind_speed_knots
                + (right.wind_speed_knots - left.wind_speed_knots) * fraction,
                dewpoint_k=left.dewpoint_k + (right.dewpoint_k - left.dewpoint_k) * fraction,
                elevation_m=left.elevation_m,
                pressure_pa=blend(left.pressure_pa, right.pressure_pa),
                temperature_k=blend(left.temperature_k, right.temperature_k),
                height_m_agl=blend(left.height_m_agl, right.height_m_agl),
            )
        )
    provenance = {
        "schema_version": 1,
        "gfs_manifest_sha256": _sha256(manifest_path),
        "initialization_time": manifest["initialization_time"],
        "source_files": [
            {"filename": item["filename"], "sha256": item["sha256"]} for item in manifest["files"]
        ],
        "spatial_interpolation": "nearest GFS grid point",
        "temporal_interpolation": "linear between three-hour forecasts",
        "vertical_interpolation": "linear in log pressure to 40 levels",
    }
    return hourly, provenance


def write_profiles_json(
    path: Path, profiles: list[AtmosphericProfile], provenance: dict[str, Any]
) -> str:
    payload = {
        "schema_version": 1,
        "provenance": provenance,
        "profiles": [profile.to_dict() for profile in profiles],
    }
    content = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()
