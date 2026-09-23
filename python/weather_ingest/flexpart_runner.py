"""Bounded, run-local FLEXPART preparation, execution, and quarantine."""

from __future__ import annotations

import hashlib
import json
import os
import resource
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from weather_ingest.cffeps import EmissionRow
from weather_ingest.flexpart_config import (
    DEFAULT_DEPOSITION,
    SPECIES_NUMBERS,
    FlexpartDeposition,
    FlexpartDomain,
    validate_generated_options,
    write_command,
    write_outgrid,
    write_pathnames,
)
from weather_ingest.flexpart_releases import compile_releases, parse_release_mass, write_releases
from weather_ingest.gfs_profiles import resolve_complete_cycle


@dataclass(frozen=True, slots=True)
class FlexpartRunLimits:
    timeout_seconds: int = 10_800
    maximum_output_bytes: int = 20 * 1024**3
    maximum_releases: int = 20_000
    minimum_particles_per_release: int = 50
    threads: int = 8


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _copy_species(options: Path, flexpart_root: Path, species: tuple[str, ...]) -> None:
    species_dir = options / "SPECIES"
    species_dir.mkdir()
    sources = {
        "PM25": flexpart_root / "options/SPECIES/SPECIES_PM25_FIRE",
        "CO": flexpart_root / "options/SPECIES/SPECIES_CO",
        "BC": flexpart_root / "options/SPECIES/SPECIES_BC",
    }
    for item in species:
        shutil.copy2(sources[item], species_dir / f"SPECIES_{SPECIES_NUMBERS[item]:03d}")


def _link_meteorology(run_dir: Path, gfs_manifest: Path) -> dict[str, Any]:
    manifest, paths = resolve_complete_cycle(gfs_manifest)
    met = run_dir / "met"
    met.mkdir()
    available = [
        "XXXXXX EMPTY LINES XXXXXXXXX",
        "XXXXXX EMPTY LINES XXXXXXXX",
        "YYYYMMDD HHMMSS   name of the file(up to 80 characters)",
    ]
    for entry, source in zip(manifest["files"], paths, strict=True):
        destination = met / source.name
        try:
            os.link(source, destination)
        except OSError:
            destination.symlink_to(source)
        valid = datetime.fromisoformat(entry["valid_time"].replace("Z", "+00:00"))
        available.append(f"{valid:%Y%m%d %H%M%S}      {source.name}      ON DISK")
    (met / "AVAILABLE").write_text("\n".join(available) + "\n", encoding="ascii")
    return {"manifest_sha256": _sha256(gfs_manifest), "file_count": len(paths)}


def prepare_flexpart_run(
    *,
    run_dir: Path,
    flexpart_root: Path,
    gfs_manifest: Path,
    rows: list[EmissionRow],
    species: tuple[str, ...],
    start: datetime,
    end: datetime,
    domain: FlexpartDomain,
    particle_budget: int,
    limits: FlexpartRunLimits,
    deposition: FlexpartDeposition = DEFAULT_DEPOSITION,
) -> dict[str, Any]:
    if len(species) != 1:
        raise ValueError(
            "FLEXPART disables gravitational settling when a release contains multiple "
            "species; prepare one transport member per species"
        )
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    options = run_dir / "options"
    output = run_dir / "output"
    options.mkdir()
    output.mkdir()
    for filename in ("AGECLASSES", "PARTOPTIONS", "IGBP_int1.dat", "sfcdata.t", "sfcdepo.t"):
        source = flexpart_root / "options" / filename
        if source.exists():
            shutil.copy2(source, options / filename)
    _copy_species(options, flexpart_root, species)
    write_command(
        options / "COMMAND",
        start,
        end,
        threads=limits.threads,
        deposition=deposition,
    )
    write_outgrid(options / "OUTGRID", domain)
    write_pathnames(run_dir / "pathnames")
    releases, release_summary = compile_releases(
        rows,
        species,
        particle_budget=particle_budget,
        minimum_particles=limits.minimum_particles_per_release,
        spatial_cell_degrees=domain.spacing if len(rows) > limits.maximum_releases else 0.0,
        maximum_releases=limits.maximum_releases,
    )
    write_releases(options / "RELEASES", releases, species)
    masses, parsed_particles = parse_release_mass(options / "RELEASES", len(species))
    if parsed_particles != release_summary["particle_count"]:
        raise AssertionError("generated particle count did not round-trip")
    parsed_mass = {
        item: sum(vector[index] for vector in masses) for index, item in enumerate(species)
    }
    if parsed_mass != release_summary["mass_kg_by_species"]:
        for item in species:
            if abs(parsed_mass[item] - release_summary["mass_kg_by_species"][item]) > 1e-6:
                raise AssertionError("generated release mass did not round-trip")
    met_summary = _link_meteorology(run_dir, gfs_manifest)
    validate_generated_options(options, start, end, domain, deposition)
    manifest = {
        "schema_version": 1,
        "status": "prepared",
        "species": list(species),
        "domain": asdict(domain),
        "deposition": asdict(deposition),
        "release_summary": release_summary,
        "meteorology": met_summary,
        "option_hashes": {path.name: _sha256(path) for path in options.iterdir() if path.is_file()},
    }
    (run_dir / "manifest.partial.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    return manifest


def derive_member_random_seed(base_seed: int, species: str) -> int:
    if not 1 <= base_seed <= 2_147_483_647:
        raise ValueError("FLEXPART base seed is outside the supported range")
    if species not in SPECIES_NUMBERS:
        raise ValueError("unknown FLEXPART species for random-seed derivation")
    return (base_seed + SPECIES_NUMBERS[species] - 1) % 2_147_483_647 + 1


def run_flexpart(
    run_dir: Path,
    executable: Path,
    limits: FlexpartRunLimits,
    *,
    random_seed: int | None = None,
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    executable = executable.resolve()
    if not executable.is_file() or executable.is_symlink():
        raise ValueError("FLEXPART executable is missing or unsafe")

    def set_limits() -> None:
        _stack_soft, stack_hard = resource.getrlimit(resource.RLIMIT_STACK)
        resource.setrlimit(resource.RLIMIT_STACK, (stack_hard, stack_hard))
        resource.setrlimit(
            resource.RLIMIT_FSIZE, (limits.maximum_output_bytes, limits.maximum_output_bytes)
        )

    env = {
        "PATH": os.environ.get("PATH", ""),
        "OMP_NUM_THREADS": str(limits.threads),
        "OMP_PLACES": "cores",
        "OMP_PROC_BIND": "true",
    }
    if random_seed is not None:
        if not 1 <= random_seed <= 2_147_483_647:
            raise ValueError("FLEXPART random seed is outside the supported range")
        env["FLEXPART_RANDOM_SEED"] = str(random_seed)
    started = time.perf_counter()
    try:
        process = subprocess.run(
            [str(executable)],
            cwd=run_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=limits.timeout_seconds,
            check=False,
            preexec_fn=set_limits,
        )
    except subprocess.TimeoutExpired as exc:
        (run_dir / "run.log").write_text(
            (exc.stdout or "") + "\nTIMEOUT\n" + (exc.stderr or ""), encoding="utf-8"
        )
        raise RuntimeError("FLEXPART exceeded its wall-time limit") from exc
    log = f"STDOUT\n{process.stdout}\nSTDERR\n{process.stderr}"
    (run_dir / "run.log").write_text(log, encoding="utf-8")
    outputs = sorted((run_dir / "output").glob("grid_conc_*.nc"))
    if "settling disabled" in process.stdout.lower():
        raise RuntimeError("FLEXPART disabled settling; species runs must be isolated")
    if process.returncode != 0 or not outputs:
        raise RuntimeError(f"FLEXPART failed with exit code {process.returncode}")
    total_size = sum(
        path.stat().st_size for path in (run_dir / "output").rglob("*") if path.is_file()
    )
    if total_size > limits.maximum_output_bytes:
        raise RuntimeError("FLEXPART output exceeded configured size")
    return {
        "status": "complete",
        "exit_code": process.returncode,
        "wall_time_seconds": round(time.perf_counter() - started, 3),
        "output_count": len(outputs),
        "output_bytes": total_size,
        "output_sha256": {path.name: _sha256(path) for path in outputs},
        "executable_sha256": _sha256(executable),
        "random_seed": random_seed,
    }


def prepare_species_runs(
    *,
    parent_dir: Path,
    flexpart_root: Path,
    gfs_manifest: Path,
    rows: list[EmissionRow],
    species: tuple[str, ...],
    start: datetime,
    end: datetime,
    domain: FlexpartDomain,
    particle_budget_per_species: int,
    limits: FlexpartRunLimits,
    deposition: FlexpartDeposition = DEFAULT_DEPOSITION,
) -> dict[str, dict[str, Any]]:
    """Prepare isolated transport members so aerosol settling remains active."""

    if parent_dir.exists():
        raise FileExistsError(parent_dir)
    parent_dir.mkdir(parents=True)
    results: dict[str, dict[str, Any]] = {}
    for item in species:
        results[item] = prepare_flexpart_run(
            run_dir=parent_dir / item.lower(),
            flexpart_root=flexpart_root,
            gfs_manifest=gfs_manifest,
            rows=rows,
            species=(item,),
            start=start,
            end=end,
            domain=domain,
            particle_budget=particle_budget_per_species,
            limits=limits,
            deposition=deposition,
        )
    return results
