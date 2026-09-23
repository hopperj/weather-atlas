#!/usr/bin/env python3
"""Prepare, run, and fingerprint the FLEXPART compact regression suite."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

try:
    from netCDF4 import Dataset
except ImportError as exc:  # pragma: no cover - useful diagnostic for fresh machines
    raise SystemExit(
        "netCDF4 is required. Run: "
        "python3 -m pip install -r tests/regression_suite/requirements.txt"
    ) from exc


SUITE_DIR = Path(__file__).resolve().parent
FLEXPART_ROOT = SUITE_DIR.parents[1]
TESTS_DIR = FLEXPART_ROOT / "tests"
MET_DIR = TESTS_DIR / "testdata" / "compact_ecmwf"
BASE_OPTIONS = TESTS_DIR / "smoke_standard" / "options"
AVAILABLE = TESTS_DIR / "smoke_standard" / "AVAILABLE"
CASES_FILE = SUITE_DIR / "cases.json"
VOLATILE_ATTRIBUTES = {"history"}


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def json_value(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def command_output(argv: list[str]) -> str:
    try:
        result = subprocess.run(
            argv, check=False, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except FileNotFoundError:
        return "not installed"
    return result.stdout.strip()


def replace_namelist_values(path: Path, overrides: dict[str, Any]) -> None:
    text = path.read_text()
    for key, value in overrides.items():
        if isinstance(value, str) and value.isdigit():
            rendered = value
        elif isinstance(value, str):
            rendered = f'"{value}"'
        elif isinstance(value, float):
            rendered = f"{value:.8g}"
        else:
            rendered = str(value)
        pattern = re.compile(rf"(?im)^\s*{re.escape(key)}\s*=.*$")
        replacement = f" {key}={rendered},"
        if pattern.search(text):
            text = pattern.sub(replacement, text, count=1)
        else:
            slash = text.rfind("/")
            if slash < 0:
                raise ValueError(f"No namelist terminator in {path}")
            text = text[:slash] + replacement + "\n" + text[slash:]
    path.write_text(text)


def write_releases(
    path: Path, species: list[dict[str, Any]], releases: list[dict[str, Any]]
) -> None:
    species_numbers = ", ".join(str(item["number"]) for item in species)
    lines = [
        "&RELEASES_CTRL",
        f" NSPEC={len(species)},",
        f" SPECNUM_REL={species_numbers},",
        "/",
    ]
    for release in releases:
        masses = ", ".join(f"{float(value):.9g}" for value in release["mass"])
        lines.extend(
            [
                "&RELEASE",
                " IDATE1=20210905,",
                f" ITIME1={release['start']},",
                " IDATE2=20210905,",
                f" ITIME2={release['end']},",
                f" LON1={release['lon1']:.8g},",
                f" LON2={release['lon2']:.8g},",
                f" LAT1={release['lat1']:.8g},",
                f" LAT2={release['lat2']:.8g},",
                f" Z1={release['z1']:.8g},",
                f" Z2={release['z2']:.8g},",
                f" ZKIND={release['zkind']},",
                f" MASS={masses},",
                f" PARTS={release['parts']},",
                f' COMMENT="{release["comment"]}",',
                "/",
            ]
        )
    path.write_text("\n".join(lines) + "\n")


def crop_chemistry_fields(inputs: Path) -> None:
    """Create limited-area OH inputs compatible with the compact met grid."""
    target_dir = inputs / "oh_fields"
    target_dir.mkdir()
    for month in ("08", "09"):
        source_path = FLEXPART_ROOT / "options" / "oh_fields" / f"OH_{month}.nc"
        target_path = target_dir / source_path.name
        with Dataset(source_path) as source:
            lon = np.asarray(source.variables["lon"][:])
            lat = np.asarray(source.variables["lat"][:])
            lon_indices = np.flatnonzero((lon >= 3.5) & (lon <= 6.5))
            lat_indices = np.flatnonzero((lat >= 48.5) & (lat <= 52.5))
            with Dataset(target_path, "w", format="NETCDF3_CLASSIC") as target:
                for name in source.ncattrs():
                    target.setncattr(name, source.getncattr(name))
                for name, dimension in source.dimensions.items():
                    if name == "lon":
                        size = len(lon_indices)
                    elif name == "lat":
                        size = len(lat_indices)
                    else:
                        size = None if dimension.isunlimited() else len(dimension)
                    target.createDimension(name, size)
                for name, variable in source.variables.items():
                    fill_value = (
                        variable.getncattr("_FillValue")
                        if "_FillValue" in variable.ncattrs()
                        else None
                    )
                    output = target.createVariable(
                        name,
                        variable.datatype,
                        variable.dimensions,
                        fill_value=fill_value,
                    )
                    output.setncatts(
                        {
                            attr: variable.getncattr(attr)
                            for attr in variable.ncattrs()
                            if attr != "_FillValue"
                        }
                    )
                    values = variable[:]
                    for axis, dimension_name in enumerate(variable.dimensions):
                        if dimension_name == "lon":
                            values = np.take(values, lon_indices, axis=axis)
                        elif dimension_name == "lat":
                            values = np.take(values, lat_indices, axis=axis)
                    output[:] = values


def write_auxiliary_inputs(inputs: Path, chemistry: bool, receptors: bool) -> None:
    (inputs / "AGECLASSES").write_text(
        "&NAGE\n NAGECLASS=3,\n/\n"
        "&AGECLASS\n LAGE=900, 1800, 3600,\n/\n"
    )
    (inputs / "OUTGRID_NEST").write_text(
        "&OUTGRIDN\n"
        " OUTLON0N=4.4,\n"
        " OUTLAT0N=50.0,\n"
        " NUMXGRIDN=25,\n"
        " NUMYGRIDN=25,\n"
        " DXOUTN=0.05,\n"
        " DYOUTN=0.05,\n"
        "/\n"
    )
    if receptors:
        (inputs / "RECEPTORS").write_text(
            '&RECEPTORS\n RECEPTOR="SOURCE",\n LON=5.0,\n LAT=50.5,\n ALT=50.0,\n/\n'
            '&RECEPTORS\n RECEPTOR="RAIN",\n LON=4.4,\n LAT=50.6,\n ALT=20.0,\n/\n'
        )
    if chemistry:
        (inputs / "REAGENTS").write_text(
            '&REAGENT_PARAMS\n PREAGENT="OH",\n'
            ' PREAG_PATH="inputs/oh_fields/",\n PHOURLY=0,\n/\n'
        )
        crop_chemistry_fields(inputs)


def fingerprint_variable(variable: Any) -> dict[str, Any]:
    value = variable[:]
    mask = np.ma.getmaskarray(value) if np.ma.isMaskedArray(value) else None
    array = np.asarray(value.filled(0) if np.ma.isMaskedArray(value) else value)
    contiguous = np.ascontiguousarray(array)
    result: dict[str, Any] = {
        "dimensions": list(variable.dimensions),
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "data_sha256": hashlib.sha256(contiguous.tobytes()).hexdigest(),
        "attributes": {
            name: json_value(variable.getncattr(name))
            for name in sorted(variable.ncattrs())
            if name not in VOLATILE_ATTRIBUTES
        },
    }
    if mask is not None and np.any(mask):
        result["mask_sha256"] = hashlib.sha256(
            np.ascontiguousarray(mask).tobytes()
        ).hexdigest()
        result["masked_count"] = int(np.count_nonzero(mask))
    if np.issubdtype(array.dtype, np.number):
        numeric = array.astype(np.float64, copy=False)
        valid = numeric[~mask] if mask is not None else numeric.reshape(-1)
        finite = valid[np.isfinite(valid)]
        result.update(
            {
                "count": int(array.size),
                "finite_count": int(finite.size),
                "nan_count": int(np.count_nonzero(np.isnan(valid))),
                "positive_inf_count": int(np.count_nonzero(np.isposinf(valid))),
                "negative_inf_count": int(np.count_nonzero(np.isneginf(valid))),
            }
        )
        if finite.size:
            result.update(
                {
                    "min": float(np.min(finite)),
                    "max": float(np.max(finite)),
                    "mean": float(np.mean(finite, dtype=np.float64)),
                    "sum": float(np.sum(finite, dtype=np.float64)),
                    "l1": float(np.sum(np.abs(finite), dtype=np.float64)),
                    "l2_squared": float(
                        np.sum(np.square(finite), dtype=np.float64)
                    ),
                    "nonzero_count": int(np.count_nonzero(finite)),
                }
            )
    return result


def fingerprint_netcdf(path: Path) -> dict[str, Any]:
    with Dataset(path, "r") as dataset:
        variables = {
            name: fingerprint_variable(dataset.variables[name])
            for name in sorted(dataset.variables)
        }
        dimensions = {
            name: {
                "size": len(dimension),
                "unlimited": dimension.isunlimited(),
            }
            for name, dimension in sorted(dataset.dimensions.items())
        }
        attributes = {
            name: json_value(dataset.getncattr(name))
            for name in sorted(dataset.ncattrs())
            if name not in VOLATILE_ATTRIBUTES
        }
    canonical = hashlib.sha256()
    for name, variable in variables.items():
        canonical.update(name.encode())
        canonical.update(json.dumps(variable, sort_keys=True).encode())
    return {
        "dimensions": dimensions,
        "attributes": attributes,
        "variables": variables,
        "scientific_sha256": canonical.hexdigest(),
    }


def output_inventory(outputs: Path) -> dict[str, Any]:
    inventory: dict[str, Any] = {}
    for path in sorted(item for item in outputs.rglob("*") if item.is_file()):
        relative = str(path.relative_to(outputs))
        entry: dict[str, Any] = {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        if path.suffix == ".nc":
            entry["netcdf"] = fingerprint_netcdf(path)
        inventory[relative] = entry
    return inventory


def input_inventory(inputs: Path) -> dict[str, Any]:
    return {
        str(path.relative_to(inputs)): {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(item for item in inputs.rglob("*") if item.is_file())
    }


def prepare_case(
    case: dict[str, Any],
    config: dict[str, Any],
    case_dir: Path,
    executable_root: Path,
    completed: dict[str, Path],
) -> tuple[Path, Path]:
    inputs = case_dir / "inputs"
    outputs = case_dir / "outputs"
    shutil.copytree(BASE_OPTIONS, inputs)
    outputs.mkdir(parents=True)

    command = dict(config["common_command"])
    command.update(case.get("command", {}))
    replace_namelist_values(inputs / "COMMAND", command)

    species = config["species_profiles"][case["species"]]
    species_dir = inputs / "SPECIES"
    shutil.rmtree(species_dir)
    species_dir.mkdir()
    for item in species:
        source = FLEXPART_ROOT / item["source"]
        shutil.copy2(source, species_dir / f"SPECIES_{item['number']:03d}")

    releases = config["release_profiles"][case["releases"]]
    write_releases(inputs / "RELEASES", species, releases)
    write_auxiliary_inputs(
        inputs, bool(case.get("chemistry")), bool(case.get("receptors"))
    )

    if case.get("restart_from"):
        source_case = completed.get(case["restart_from"])
        if source_case is None:
            raise RuntimeError(
                f"{case['name']} requires prior case {case['restart_from']}"
            )
        restart_source = inputs / "restart_source"
        shutil.copytree(source_case / "outputs", restart_source)
        shutil.copytree(restart_source, outputs, dirs_exist_ok=True)
        source = restart_source / case["restart_pattern"]
        if not source.exists():
            raise FileNotFoundError(f"Required restart not produced: {source}")
        shutil.copy2(source, inputs / "restart.bin")
        shutil.copy2(source, outputs / "restart.bin")

    shutil.copy2(AVAILABLE, inputs / "AVAILABLE")
    (case_dir / "met").symlink_to(MET_DIR.resolve(), target_is_directory=True)
    pathnames = case_dir / "pathnames"
    pathnames.write_text(
        "inputs/\n"
        "outputs/\n"
        "met/\n"
        "inputs/AVAILABLE\n"
    )
    executable = executable_root / case["executable"]
    if not executable.exists():
        raise FileNotFoundError(f"Missing executable: {executable}")
    return executable, pathnames


def run_case(
    case: dict[str, Any],
    config: dict[str, Any],
    root: Path,
    executable_root: Path,
    completed: dict[str, Path],
) -> dict[str, Any]:
    name = case["name"]
    case_dir = root / "cases" / name
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)
    executable, pathnames = prepare_case(
        case, config, case_dir, executable_root, completed
    )

    env = os.environ.copy()
    env.update(
        {
            "OMP_NUM_THREADS": str(case["threads"]),
            "OMP_DYNAMIC": "FALSE",
        }
    )
    start = time.monotonic()
    result = subprocess.run(
        [str(executable), str(pathnames)],
        cwd=case_dir,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    elapsed = time.monotonic() - start
    (case_dir / "run.log").write_text(result.stdout)
    success_marker = (
        "CONGRATULATIONS: YOU HAVE SUCCESSFULLY COMPLETED A FLEXPART MODEL RUN!"
    )
    passed = result.returncode == 0 and success_marker in result.stdout
    manifest = {
        "name": name,
        "description": case["description"],
        "passed": passed,
        "returncode": result.returncode,
        "runtime_seconds": elapsed,
        "executable": str(executable.resolve()),
        "executable_sha256": sha256_file(executable),
        "threads": case["threads"],
        "environment": {
            "OMP_NUM_THREADS": env["OMP_NUM_THREADS"],
            "OMP_DYNAMIC": env["OMP_DYNAMIC"],
        },
        "pathnames": {
            "contents": pathnames.read_text().splitlines(),
            "sha256": sha256_file(pathnames),
        },
        "inputs": input_inventory(case_dir / "inputs"),
        "outputs": output_inventory(case_dir / "outputs"),
        "log_sha256": sha256_file(case_dir / "run.log"),
    }
    (case_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    completed[name] = case_dir
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name}: {elapsed:.3f}s, {len(manifest['outputs'])} files")
    if not passed:
        tail = "\n".join(result.stdout.splitlines()[-30:])
        print(tail, file=sys.stderr)
    return manifest


def source_inventory() -> dict[str, str]:
    files = list((FLEXPART_ROOT / "src").glob("*.f90"))
    files.extend((FLEXPART_ROOT / "src").glob("makefile_*"))
    return {
        str(path.relative_to(FLEXPART_ROOT)): sha256_file(path)
        for path in sorted(files)
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=SUITE_DIR / "baselines" / "flexpart-11.1-original",
        help="Artifact root to create",
    )
    parser.add_argument(
        "--executable-root",
        type=Path,
        default=FLEXPART_ROOT / "src",
        help="Directory containing FLEXPART and FLEXPART_ETA",
    )
    parser.add_argument(
        "--cases",
        nargs="*",
        help="Optional case names; dependencies must also be selected",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete an existing artifact root",
    )
    args = parser.parse_args()

    root = args.output.resolve()
    if root.exists():
        if not args.replace:
            raise SystemExit(f"Output already exists: {root}; use --replace")
        shutil.rmtree(root)
    root.mkdir(parents=True)

    config = json.loads(CASES_FILE.read_text())
    selected = [
        case for case in config["cases"]
        if not args.cases or case["name"] in args.cases
    ]
    if not selected:
        raise SystemExit("No cases selected")

    met_files = {
        path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in sorted(MET_DIR.iterdir())
        if path.is_file()
    }
    suite_manifest: dict[str, Any] = {
        "suite_version": config["suite_version"],
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": sys.version,
        "cases_file_sha256": sha256_file(CASES_FILE),
        "source_files": source_inventory(),
        "meteorology": met_files,
        "toolchain": {
            "gfortran": command_output(["gfortran", "--version"]),
            "eccodes": command_output(["codes_info", "-v"]),
            "netcdf_c": command_output(["nc-config", "--version"]),
            "netcdf_fortran": command_output(["nf-config", "--version"]),
        },
        "cases": {},
    }
    completed: dict[str, Path] = {}
    failed = 0
    for case in selected:
        manifest = run_case(
            case, config, root, args.executable_root.resolve(), completed
        )
        suite_manifest["cases"][case["name"]] = {
            "passed": manifest["passed"],
            "runtime_seconds": manifest["runtime_seconds"],
            "manifest": f"cases/{case['name']}/manifest.json",
        }
        failed += not manifest["passed"]
        (root / "suite_manifest.json").write_text(
            json.dumps(suite_manifest, indent=2, sort_keys=True) + "\n"
        )

    suite_manifest["completed_utc"] = datetime.now(timezone.utc).isoformat()
    suite_manifest["passed"] = failed == 0
    suite_manifest["case_count"] = len(selected)
    suite_manifest["failed_count"] = failed
    (root / "suite_manifest.json").write_text(
        json.dumps(suite_manifest, indent=2, sort_keys=True) + "\n"
    )
    print(f"Suite complete: {len(selected) - failed}/{len(selected)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
