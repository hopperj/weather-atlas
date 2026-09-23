"""Parser and frozen observation operator for MISR MINX plume text products."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

INVALID_HEIGHT = -9999.0


@dataclass(frozen=True, slots=True)
class MinxRetrievalPoint:
    point_number: int
    longitude: float
    latitude: float
    terrain_asl_m: float
    no_wind_asl_m: float | None
    wind_corrected_asl_m: float | None
    filtered_asl_m: float | None

    def height_agl_m(self, field: str = "wind_corrected") -> float | None:
        value = {
            "wind_corrected": self.wind_corrected_asl_m,
            "no_wind": self.no_wind_asl_m,
            "filtered": self.filtered_asl_m,
        }[field]
        if value is None:
            return None
        height = value - self.terrain_asl_m
        return height if math.isfinite(height) else None


@dataclass(frozen=True, slots=True)
class MinxPlume:
    source_path: Path
    source_sha256: str
    region_name: str
    orbit_number: int
    acquired_at: datetime
    minx_version: str
    aerosol_type: str
    geometry_type: str
    retrieval_quality: str
    fire_elevation_asl_m: float | None
    polygon: tuple[tuple[float, float], ...]
    points: tuple[MinxRetrievalPoint, ...]

    def valid_heights_agl_m(
        self,
        *,
        field: str = "wind_corrected",
        minimum_agl_m: float = 250.0,
    ) -> np.ndarray:
        values = [
            value
            for point in self.points
            if (value := point.height_agl_m(field)) is not None and value >= minimum_agl_m
        ]
        return np.asarray(values, dtype=np.float64)

    def robust_height_agl_m(
        self,
        *,
        field: str = "wind_corrected",
        minimum_agl_m: float = 250.0,
        statistic: str = "median",
    ) -> float:
        values = self.valid_heights_agl_m(
            field=field,
            minimum_agl_m=minimum_agl_m,
        )
        if values.size == 0:
            raise ValueError(f"{self.region_name} has no valid {field} plume heights")
        if statistic == "median":
            return float(np.median(values))
        if statistic == "p95":
            return float(np.quantile(values, 0.95))
        raise ValueError(f"unsupported MINX aggregation statistic: {statistic}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _optional_height(value: str) -> float | None:
    number = float(value)
    return number if math.isfinite(number) and number > INVALID_HEIGHT else None


def _metadata(lines: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("POLYGON:"):
            break
        if ":" in stripped:
            key, value = stripped.split(":", 1)
            result[key.strip()] = value.strip()
    return result


def _numeric_rows(
    lines: list[str],
    *,
    section: str,
    minimum_columns: int,
) -> list[list[str]]:
    start = next(
        (index for index, line in enumerate(lines) if line.strip().startswith(section)),
        None,
    )
    if start is None:
        return []
    rows: list[list[str]] = []
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if rows and (not stripped or stripped.endswith(":")):
            break
        columns = stripped.split()
        if len(columns) >= minimum_columns and columns[0].lstrip("+-").isdigit():
            rows.append(columns)
    return rows


def parse_minx_plume(path: Path) -> MinxPlume:
    """Parse one public MINX plume text file without using model output."""

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    metadata = _metadata(lines)
    required = {
        "Orbit number",
        "Date acquired",
        "UTC time",
        "MINX version",
        "Region name",
        "Region aerosol type",
        "Region geometry type",
    }
    missing = sorted(required.difference(metadata))
    if missing:
        raise ValueError(f"MINX file lacks metadata {missing}: {path}")
    acquired_at = datetime.fromisoformat(
        f"{metadata['Date acquired']}T{metadata['UTC time']}+00:00"
    ).astimezone(UTC)
    polygon_rows = _numeric_rows(lines, section="POLYGON:", minimum_columns=3)
    polygon = tuple((float(row[1]), float(row[2])) for row in polygon_rows)
    if len(polygon) < 4:
        raise ValueError(f"MINX plume polygon has fewer than four vertices: {path}")
    if polygon[0] != polygon[-1]:
        polygon += (polygon[0],)

    result_rows = _numeric_rows(lines, section="RESULTS:", minimum_columns=13)
    points = tuple(
        MinxRetrievalPoint(
            point_number=int(row[0]),
            longitude=float(row[1]),
            latitude=float(row[2]),
            terrain_asl_m=float(row[9]),
            no_wind_asl_m=_optional_height(row[10]),
            wind_corrected_asl_m=_optional_height(row[11]),
            filtered_asl_m=_optional_height(row[12]),
        )
        for row in result_rows
    )
    if not points:
        raise ValueError(f"MINX plume contains no retrieval rows: {path}")
    fire_elevation = metadata.get("Fire elev. (m > MSL)")
    return MinxPlume(
        source_path=path,
        source_sha256=_sha256(path),
        region_name=metadata["Region name"],
        orbit_number=int(metadata["Orbit number"]),
        acquired_at=acquired_at,
        minx_version=metadata["MINX version"],
        aerosol_type=metadata["Region aerosol type"],
        geometry_type=metadata["Region geometry type"],
        retrieval_quality=metadata.get("Retrieval quality est.", "Not recorded"),
        fire_elevation_asl_m=float(fire_elevation) if fire_elevation else None,
        polygon=polygon,
        points=points,
    )
