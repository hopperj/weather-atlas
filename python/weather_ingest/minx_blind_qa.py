"""Height-blind parsing and quality checks for MISR MINX plume files."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REGION_NAME = re.compile(
    r"^O(?P<orbit>[0-9]{6})-B(?P<block>[0-9]{3})-"
    r"SPW(?P<band>[BR])(?P<plume>[0-9]{2})$"
)
ALLOWED_METADATA = {
    "Orbit number",
    "Date acquired",
    "UTC time",
    "MINX version",
    "Region name",
    "Region aerosol type",
    "Region geometry type",
    "Retrieval quality est.",
}
QUALITY_RANK = {"Good": 0, "Fair": 1, "Poor": 2}


@dataclass(frozen=True, slots=True)
class BlindMinxPlume:
    source_path: Path
    source_sha256: str
    region_name: str
    orbit_number: int
    acquired_at: datetime
    minx_version: str
    aerosol_type: str
    geometry_type: str
    retrieval_quality: str
    band: str
    polygon: tuple[tuple[float, float], ...]
    raw_retrieval_count: int
    retrieval_point_numbers_unique: bool
    retrieval_coordinates_finite: bool
    terrain_values_finite: bool


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def plume_family_name(region_name: str) -> str:
    """Return the band-independent identity of one MINX plume delineation."""

    match = REGION_NAME.fullmatch(region_name)
    if match is None:
        raise ValueError(f"unrecognized MINX region name: {region_name}")
    return f"O{match.group('orbit')}-B{match.group('block')}-SPW{match.group('plume')}"


def _section_rows(
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


def parse_minx_without_heights(path: Path) -> BlindMinxPlume:
    """Parse only fields permitted before the plume-height selection freeze.

    RESULT columns 10–12 contain the observed height measurements. They are
    deliberately neither converted nor retained by this parser.
    """

    lines = path.read_text(encoding="utf-8", errors="strict").splitlines()
    metadata: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("POLYGON:"):
            break
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        normalized = key.strip()
        if normalized in ALLOWED_METADATA:
            metadata[normalized] = value.strip()
    missing = sorted(ALLOWED_METADATA - metadata.keys())
    if missing:
        raise ValueError(f"MINX file lacks blind-QA metadata {missing}: {path}")
    match = REGION_NAME.fullmatch(metadata["Region name"])
    if match is None:
        raise ValueError(f"unrecognized MINX region name: {metadata['Region name']}")
    acquired_at = datetime.fromisoformat(
        f"{metadata['Date acquired']}T{metadata['UTC time']}+00:00"
    ).astimezone(UTC)
    polygon_rows = _section_rows(lines, section="POLYGON:", minimum_columns=3)
    polygon = tuple((float(row[1]), float(row[2])) for row in polygon_rows)
    if polygon and polygon[0] != polygon[-1]:
        polygon += (polygon[0],)

    result_rows = _section_rows(lines, section="RESULTS:", minimum_columns=13)
    numbers: list[int] = []
    coordinates: list[tuple[float, float]] = []
    terrains: list[float] = []
    for row in result_rows:
        # Stop at terrain. Height-bearing columns 10–12 remain opaque strings.
        numbers.append(int(row[0]))
        coordinates.append((float(row[1]), float(row[2])))
        terrains.append(float(row[9]))
    return BlindMinxPlume(
        source_path=path.resolve(),
        source_sha256=sha256(path),
        region_name=metadata["Region name"],
        orbit_number=int(metadata["Orbit number"]),
        acquired_at=acquired_at,
        minx_version=metadata["MINX version"],
        aerosol_type=metadata["Region aerosol type"],
        geometry_type=metadata["Region geometry type"],
        retrieval_quality=metadata["Retrieval quality est."],
        band=match.group("band"),
        polygon=polygon,
        raw_retrieval_count=len(result_rows),
        retrieval_point_numbers_unique=len(numbers) == len(set(numbers)),
        retrieval_coordinates_finite=all(
            math.isfinite(longitude)
            and math.isfinite(latitude)
            and -180 <= longitude <= 180
            and -90 <= latitude <= 90
            for longitude, latitude in coordinates
        ),
        terrain_values_finite=all(math.isfinite(value) for value in terrains),
    )


def polygon_area_degrees2(polygon: tuple[tuple[float, float], ...]) -> float:
    if len(polygon) < 4:
        return 0.0
    return (
        abs(
            sum(
                first[0] * second[1] - second[0] * first[1]
                for first, second in zip(polygon, polygon[1:], strict=False)
            )
        )
        / 2.0
    )


def point_in_polygon(
    longitude: float,
    latitude: float,
    polygon: tuple[tuple[float, float], ...],
) -> bool:
    inside = False
    for first, second in zip(polygon, polygon[1:], strict=False):
        x1, y1 = first
        x2, y2 = second
        if (y1 > latitude) != (y2 > latitude):
            crossing = (x2 - x1) * (latitude - y1) / (y2 - y1) + x1
            if longitude < crossing:
                inside = not inside
    return inside


def source_to_polygon_km(
    longitude: float,
    latitude: float,
    polygon: tuple[tuple[float, float], ...],
) -> float:
    """Approximate minimum source-to-polygon distance on a local tangent plane."""

    if point_in_polygon(longitude, latitude, polygon):
        return 0.0
    cosine = math.cos(math.radians(latitude))

    def projected(point: tuple[float, float]) -> tuple[float, float]:
        return (
            (point[0] - longitude) * 111.32 * cosine,
            (point[1] - latitude) * 110.57,
        )

    minimum = math.inf
    for first, second in zip(polygon, polygon[1:], strict=False):
        x1, y1 = projected(first)
        x2, y2 = projected(second)
        dx = x2 - x1
        dy = y2 - y1
        denominator = dx * dx + dy * dy
        fraction = 0.0 if denominator == 0 else -(x1 * dx + y1 * dy) / denominator
        fraction = min(1.0, max(0.0, fraction))
        minimum = min(
            minimum,
            math.hypot(x1 + fraction * dx, y1 + fraction * dy),
        )
    return minimum


def blind_quality_checks(
    plume: BlindMinxPlume,
    *,
    expected_orbit: int,
    expected_time: datetime,
    expected_region_name: str,
    expected_retrieval_count: int,
    source_latitude: float,
    source_longitude: float,
    minimum_raw_retrievals: int = 10,
    maximum_source_polygon_distance_km: float = 5.0,
) -> dict[str, bool]:
    return {
        "region_name_matches": plume.region_name == expected_region_name,
        "orbit_matches": plume.orbit_number == expected_orbit,
        "acquisition_time_matches": plume.acquired_at == expected_time,
        "provider_successful_retrieval_count_bounded_by_rows": (
            0 < expected_retrieval_count <= plume.raw_retrieval_count
        ),
        "supported_product_version": plume.minx_version == "V4.0",
        "smoke_aerosol": plume.aerosol_type == "Smoke",
        "polygon_geometry": plume.geometry_type == "Polygon",
        "quality_good_or_fair": plume.retrieval_quality in {"Good", "Fair"},
        "minimum_raw_retrievals": (plume.raw_retrieval_count >= minimum_raw_retrievals),
        "polygon_has_four_unique_vertices": len(set(plume.polygon[:-1])) >= 4,
        "polygon_is_closed": bool(plume.polygon) and plume.polygon[0] == plume.polygon[-1],
        "polygon_has_positive_area": polygon_area_degrees2(plume.polygon) > 0,
        "source_connected_to_polygon": source_to_polygon_km(
            source_longitude,
            source_latitude,
            plume.polygon,
        )
        <= maximum_source_polygon_distance_km,
        "retrieval_point_numbers_unique": plume.retrieval_point_numbers_unique,
        "retrieval_coordinates_finite": plume.retrieval_coordinates_finite,
        "terrain_values_finite": plume.terrain_values_finite,
    }


def blind_selection_rank(plume: BlindMinxPlume) -> tuple[int, int, int, str]:
    """Prefer provider quality, then blue for land smoke, then sample support."""

    return (
        QUALITY_RANK.get(plume.retrieval_quality, 99),
        0 if plume.band == "B" else 1,
        -plume.raw_retrieval_count,
        plume.region_name,
    )
