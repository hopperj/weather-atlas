"""Mass-conserving FLEXPART release aggregation and particle allocation."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from weather_ingest.cffeps import EmissionRow
from weather_ingest.flexpart_config import SPECIES_NUMBERS

MINIMUM_PARTICLES_PER_RELEASE = 50
MAXIMUM_RELEASE_GROUPS_PER_EVENT_HOUR = 36


@dataclass(frozen=True, slots=True)
class CompiledRelease:
    start: datetime
    end: datetime
    longitude: float
    latitude: float
    bottom_m_agl: float
    top_m_agl: float
    mass_kg: tuple[float, ...]
    particles: int
    comment: str


def compile_releases(
    rows: list[EmissionRow],
    species: tuple[str, ...],
    *,
    particle_budget: int,
    minimum_particles: int = MINIMUM_PARTICLES_PER_RELEASE,
    spatial_cell_degrees: float = 0.0,
    maximum_releases: int = 20_000,
) -> tuple[list[CompiledRelease], dict[str, object]]:
    if not rows:
        raise ValueError("cannot compile an empty emission bundle")
    if not species or set(species) - SPECIES_NUMBERS.keys():
        raise ValueError("invalid FLEXPART species selection")
    if particle_budget < minimum_particles:
        raise ValueError("particle budget is below one minimum release")
    grouped: dict[tuple[object, ...], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in rows:
        if row.species not in species or row.emitted_mass_kg <= 0:
            continue
        lon = row.longitude
        lat = row.latitude
        if spatial_cell_degrees > 0:
            lon = round(lon / spatial_cell_degrees) * spatial_cell_degrees
            lat = round(lat / spatial_cell_degrees) * spatial_cell_degrees
        key = (
            row.source_time_start,
            row.source_time_end,
            lon,
            lat,
            row.vertical_layer_bottom_m_agl,
            row.vertical_layer_top_m_agl,
        )
        grouped[key][row.species] += row.emitted_mass_kg
    if not grouped or len(grouped) > maximum_releases:
        raise ValueError("release count is zero or exceeds the configured maximum")
    if len(grouped) * minimum_particles > particle_budget:
        raise ValueError("particle budget cannot represent every non-zero release")
    totals = {key: sum(masses.values()) for key, masses in grouped.items()}
    total_mass = sum(totals.values())
    remaining = particle_budget - len(grouped) * minimum_particles
    allocations = {
        key: minimum_particles + math.floor(remaining * mass / total_mass)
        for key, mass in totals.items()
    }
    spare = particle_budget - sum(allocations.values())
    for key in sorted(grouped, key=lambda item: (-totals[item], item))[:spare]:
        allocations[key] += 1
    releases: list[CompiledRelease] = []
    for index, key in enumerate(sorted(grouped)):
        start, end, lon, lat, bottom, top = key
        releases.append(
            CompiledRelease(
                start=start,
                end=end,
                longitude=float(lon),
                latitude=float(lat),
                bottom_m_agl=float(bottom),
                top_m_agl=float(top),
                mass_kg=tuple(grouped[key].get(item, 0.0) for item in species),
                particles=allocations[key],
                comment=f"SMOKE_{index + 1:05d}",
            )
        )
    input_mass = {
        item: sum(row.emitted_mass_kg for row in rows if row.species == item) for item in species
    }
    output_mass = {
        item: sum(release.mass_kg[index] for release in releases)
        for index, item in enumerate(species)
    }
    for item in species:
        if not math.isclose(input_mass[item], output_mass[item], rel_tol=1e-12, abs_tol=1e-9):
            raise AssertionError(f"release compiler lost {item} mass")
    return releases, {
        "pre_aggregation_row_count": len(rows),
        "release_count": len(releases),
        "particle_count": sum(item.particles for item in releases),
        "mass_kg_by_species": output_mass,
        "spatial_cell_degrees": spatial_cell_degrees,
    }


def _date_time(value: datetime) -> tuple[int, int]:
    value = value.astimezone(UTC)
    return int(value.strftime("%Y%m%d")), int(value.strftime("%H%M%S"))


def write_releases(path: Path, releases: list[CompiledRelease], species: tuple[str, ...]) -> None:
    numbers = ",".join(str(SPECIES_NUMBERS[item]) for item in species)
    lines = ["&RELEASES_CTRL", f" NSPEC={len(species)},", f" SPECNUM_REL={numbers},", "/"]
    for release in releases:
        start_date, start_time = _date_time(release.start)
        end_date, end_time = _date_time(release.end)
        mass = ",".join(f"{value:.12E}" for value in release.mass_kg)
        lines.extend(
            [
                "&RELEASE",
                f" IDATE1={start_date}, ITIME1={start_time:06d},",
                f" IDATE2={end_date}, ITIME2={end_time:06d},",
                f" LON1={release.longitude:.7f}, LON2={release.longitude:.7f},",
                f" LAT1={release.latitude:.7f}, LAT2={release.latitude:.7f},",
                f" Z1={release.bottom_m_agl:.3f}, Z2={release.top_m_agl:.3f}, ZKIND=1,",
                f" MASS={mass}, PARTS={release.particles}, COMMENT='{release.comment}',",
                "/",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def parse_release_mass(path: Path, species_count: int) -> tuple[list[tuple[float, ...]], int]:
    masses: list[tuple[float, ...]] = []
    particles = 0
    for line in path.read_text(encoding="ascii").splitlines():
        stripped = line.strip()
        if stripped.startswith("MASS="):
            value = stripped.split("=", 1)[1].split("PARTS", 1)[0].rstrip(" ,")
            parsed = tuple(float(item) for item in value.split(",") if item.strip())
            if len(parsed) != species_count:
                raise ValueError("generated RELEASES has wrong mass vector length")
            masses.append(parsed)
            if "PARTS=" in stripped:
                particles += int(stripped.split("PARTS=", 1)[1].split(",", 1)[0])
        elif "PARTS=" in stripped:
            particles += int(stripped.split("PARTS=", 1)[1].split(",", 1)[0])
    if not masses:
        raise ValueError("generated RELEASES contains no releases")
    return masses, particles
