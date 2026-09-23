#!/usr/bin/env python3
"""Capture and replay the frozen FLEXPART wet-deposition failure."""

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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np
from netCDF4 import Dataset, num2date
from weather_ingest.flexpart_runner import FlexpartRunLimits, run_flexpart

SCIENCE_VARIABLE_PREFIXES = ("spec", "WD_", "DD_")
NAN_COUNTER_PATTERN = re.compile(r"nan_synctime\s+(\d+)\s+nan_tl\s+(\d+)")
MAXTHREADGRID_PATTERN = re.compile(r"MAXTHREADGRID\s*=\s*\d+")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_value(value: Any) -> Any:
    if np.ma.isMaskedArray(value):
        return json_value(value.filled(np.nan).tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, float) and not np.isfinite(value):
        if np.isnan(value):
            return "NaN"
        return "Infinity" if value > 0 else "-Infinity"
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    return value


def write_json(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(json_value(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    digest = sha256(path)
    path.with_suffix(f"{path.suffix}.sha256").write_text(
        f"{digest}  {path.name}\n",
        encoding="ascii",
    )
    return digest


def file_evidence(path: Path, *, relative_to: Path | None = None) -> dict[str, Any]:
    display_path = path.relative_to(relative_to).as_posix() if relative_to else str(path)
    evidence: dict[str, Any] = {
        "path": display_path,
        "exists": path.exists(),
        "is_symlink": path.is_symlink(),
    }
    if path.is_symlink():
        evidence["symlink_target"] = os.readlink(path)
    if path.is_file():
        evidence.update({"bytes": path.stat().st_size, "sha256": sha256(path)})
    return evidence


def member_input_evidence(member: Path) -> dict[str, Any]:
    files = [
        member / "pathnames",
        member / "manifest.partial.json",
        member / "met/AVAILABLE",
        *sorted(path for path in (member / "options").rglob("*") if path.is_file()),
        *sorted(
            path
            for path in (member / "met").iterdir()
            if path.is_file() and path.name != "AVAILABLE"
        ),
    ]
    return {
        "member": str(member),
        "files": [file_evidence(path, relative_to=member) for path in files],
    }


def system_evidence(executable: Path | None = None) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "captured_at": datetime.now(UTC).isoformat(),
        "platform": platform.platform(),
        "python": sys.version,
        "numpy": np.__version__,
        "netcdf4_python": netCDF4.__version__,
        "netcdf_c": netCDF4.getlibversion(),
        "uname": json_value(platform.uname()._asdict()),
    }
    if executable is not None:
        evidence["executable"] = file_evidence(executable)
        for command, key in ((["otool", "-L", str(executable)], "linked_libraries"),):
            try:
                process = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                evidence[key] = {"error": str(exc)}
            else:
                evidence[key] = {
                    "command": command,
                    "exit_code": process.returncode,
                    "stdout": process.stdout,
                    "stderr": process.stderr,
                }
    return evidence


def coordinate_value(dataset: Dataset, dimension: str, index: int) -> Any:
    if dimension not in dataset.variables:
        return None
    variable = dataset.variables[dimension]
    if variable.ndim != 1 or index >= variable.shape[0]:
        return None
    variable.set_auto_mask(False)
    return json_value(variable[index])


def decoded_time(dataset: Dataset, index: int) -> str | None:
    if "time" not in dataset.variables:
        return None
    variable = dataset.variables["time"]
    try:
        value = num2date(
            variable[index],
            units=variable.units,
            calendar=getattr(variable, "calendar", "standard"),
            only_use_cftime_datetimes=False,
        )
    except (AttributeError, IndexError, TypeError, ValueError):
        return None
    return value.isoformat()


def neighborhood(
    array: np.ndarray,
    comparison: np.ndarray | None,
    dimensions: tuple[str, ...],
    index: tuple[int, ...],
) -> list[dict[str, Any]]:
    if "latitude" not in dimensions or "longitude" not in dimensions:
        return []
    latitude_axis = dimensions.index("latitude")
    longitude_axis = dimensions.index("longitude")
    latitude_index = index[latitude_axis]
    longitude_index = index[longitude_axis]
    records: list[dict[str, Any]] = []
    for latitude in range(
        max(0, latitude_index - 1),
        min(array.shape[latitude_axis], latitude_index + 2),
    ):
        for longitude in range(
            max(0, longitude_index - 1),
            min(array.shape[longitude_axis], longitude_index + 2),
        ):
            neighbour = list(index)
            neighbour[latitude_axis] = latitude
            neighbour[longitude_axis] = longitude
            neighbour_tuple = tuple(neighbour)
            record = {
                "index": list(neighbour_tuple),
                "value": json_value(array[neighbour_tuple]),
            }
            if comparison is not None:
                record["comparison_value"] = json_value(comparison[neighbour_tuple])
            records.append(record)
    return records


def science_output_evidence(path: Path, comparison_path: Path | None = None) -> dict[str, Any]:
    comparison_dataset = Dataset(comparison_path) if comparison_path else None
    try:
        with Dataset(path) as dataset:
            dimensions = {name: len(value) for name, value in dataset.dimensions.items()}
            variables: dict[str, Any] = {}
            for name, variable in dataset.variables.items():
                if not name.startswith(SCIENCE_VARIABLE_PREFIXES):
                    continue
                variable.set_auto_mask(False)
                array = np.asarray(variable[:])
                comparison = None
                if comparison_dataset is not None and name in comparison_dataset.variables:
                    comparison_variable = comparison_dataset.variables[name]
                    comparison_variable.set_auto_mask(False)
                    candidate_comparison = np.asarray(comparison_variable[:])
                    if candidate_comparison.shape == array.shape:
                        comparison = candidate_comparison
                finite = np.isfinite(array)
                invalid_records = []
                for raw_index in np.argwhere(~finite):
                    index = tuple(int(item) for item in raw_index)
                    index_by_dimension = dict(zip(variable.dimensions, index, strict=True))
                    record: dict[str, Any] = {
                        "index": list(index),
                        "index_by_dimension": index_by_dimension,
                        "coordinates": {
                            dimension: coordinate_value(dataset, dimension, item)
                            for dimension, item in index_by_dimension.items()
                        },
                        "value": json_value(array[index]),
                        "neighborhood": neighborhood(
                            array,
                            comparison,
                            variable.dimensions,
                            index,
                        ),
                    }
                    if "time" in index_by_dimension:
                        record["decoded_time"] = decoded_time(
                            dataset,
                            index_by_dimension["time"],
                        )
                    if comparison is not None:
                        record["comparison_value"] = json_value(comparison[index])
                    invalid_records.append(record)
                finite_values = array[finite]
                variables[name] = {
                    "dimensions": list(variable.dimensions),
                    "shape": list(variable.shape),
                    "dtype": str(variable.dtype),
                    "attributes": {
                        attribute: json_value(getattr(variable, attribute))
                        for attribute in variable.ncattrs()
                    },
                    "finite_count": int(finite.sum()),
                    "nonfinite_count": int((~finite).sum()),
                    "negative_finite_count": int((finite & (array < 0)).sum()),
                    "finite_min": json_value(finite_values.min()) if finite_values.size else None,
                    "finite_max": json_value(finite_values.max()) if finite_values.size else None,
                    "finite_sum": json_value(finite_values.astype(np.float64).sum()),
                    "nonfinite_values": invalid_records,
                }
            return {
                "file": file_evidence(path),
                "comparison_file": file_evidence(comparison_path) if comparison_path else None,
                "dimensions": dimensions,
                "variables": variables,
            }
    finally:
        if comparison_dataset is not None:
            comparison_dataset.close()


def log_nan_counters(path: Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    matches = []
    for line_number, line in enumerate(lines, start=1):
        match = NAN_COUNTER_PATTERN.search(line)
        if match and (int(match.group(1)) or int(match.group(2))):
            matches.append(
                {
                    "line": line_number,
                    "nan_synctime": int(match.group(1)),
                    "nan_tl": int(match.group(2)),
                    "text": line.strip(),
                }
            )
    return {
        "file": file_evidence(path),
        "nonzero_counter_lines": matches,
        "first_nonzero_counter_line": matches[0] if matches else None,
    }


def manifest_member(path: Path, date: str, species: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "file": file_evidence(path),
        "execution": payload.get("execution"),
        "transport_member": payload["transport_days"][date],
        "selected_species": species,
    }


def baseline(args: argparse.Namespace) -> int:
    failed_member = args.failed_member.resolve()
    comparison_member = args.comparison_member.resolve()
    failed_output = next((failed_member / "output").glob("grid_conc_*.nc"))
    comparison_output = next((comparison_member / "output").glob("grid_conc_*.nc"))
    payload = {
        "schema_version": 1,
        "artifact_type": "flexpart-thread-deposition-baseline",
        "created_at": datetime.now(UTC).isoformat(),
        "command": [str(item) for item in sys.argv],
        "hypothesis_status": "root_cause_unassigned",
        "system": system_evidence(args.executable.resolve() if args.executable else None),
        "failed_member_inputs": member_input_evidence(failed_member),
        "comparison_member_inputs": member_input_evidence(comparison_member),
        "failed_candidate_manifest": manifest_member(
            args.failed_manifest.resolve(),
            args.date,
            args.species,
        ),
        "comparison_candidate_manifest": manifest_member(
            args.comparison_manifest.resolve(),
            args.date,
            args.species,
        ),
        "failed_log": log_nan_counters(failed_member / "run.log"),
        "comparison_log": log_nan_counters(comparison_member / "run.log"),
        "failed_output": science_output_evidence(failed_output, comparison_output),
    }
    digest = write_json(args.output.resolve(), payload)
    print(json.dumps({"output": str(args.output.resolve()), "sha256": digest}, indent=2))
    return 0


def materialize_replay(source: Path, destination: Path, threads: int) -> dict[str, Any]:
    if destination.exists():
        raise FileExistsError(destination)
    destination.mkdir(parents=True)
    shutil.copytree(source / "options", destination / "options")
    shutil.copy2(source / "pathnames", destination / "pathnames")
    shutil.copy2(source / "manifest.partial.json", destination / "manifest.partial.json")
    (destination / "output").mkdir()
    (destination / "met").mkdir()
    shutil.copy2(source / "met/AVAILABLE", destination / "met/AVAILABLE")
    for path in sorted((source / "met").iterdir()):
        if path.name == "AVAILABLE":
            continue
        (destination / "met" / path.name).symlink_to(path.resolve())
    command_path = destination / "options/COMMAND"
    command_text = command_path.read_text(encoding="ascii")
    updated_text, replacements = MAXTHREADGRID_PATTERN.subn(
        f"MAXTHREADGRID={threads}",
        command_text,
        count=1,
    )
    if replacements != 1:
        raise ValueError("COMMAND does not contain exactly one MAXTHREADGRID assignment")
    command_path.write_text(updated_text, encoding="ascii")
    return member_input_evidence(destination)


def replay(args: argparse.Namespace) -> int:
    source = args.source_member.resolve()
    attempt = (
        args.attempt_root.resolve()
        / f"threads-{args.threads}-replicate-{args.replicate:02d}"
    )
    started_at = datetime.now(UTC)
    source_evidence = member_input_evidence(source)
    replay_evidence = materialize_replay(source, attempt, args.threads)
    limits = FlexpartRunLimits(
        timeout_seconds=args.timeout_seconds,
        maximum_output_bytes=args.maximum_output_bytes,
        maximum_releases=20_000,
        minimum_particles_per_release=50,
        threads=args.threads,
    )
    error = None
    result = None
    try:
        result = run_flexpart(
            attempt,
            args.executable.resolve(),
            limits,
            random_seed=args.random_seed,
        )
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
    outputs = sorted((attempt / "output").glob("grid_conc_*.nc"))
    output_evidence = (
        science_output_evidence(outputs[0], args.comparison_output.resolve())
        if outputs
        else None
    )
    payload = {
        "schema_version": 1,
        "artifact_type": "flexpart-thread-deposition-replay",
        "created_at": datetime.now(UTC).isoformat(),
        "started_at": started_at.isoformat(),
        "command": [str(item) for item in sys.argv],
        "source_member": str(source),
        "attempt_directory": str(attempt),
        "threads": args.threads,
        "replicate": args.replicate,
        "random_seed": args.random_seed,
        "runtime_environment": {
            "OMP_NUM_THREADS": str(args.threads),
            "OMP_PLACES": "cores",
            "OMP_PROC_BIND": "true",
            "FLEXPART_RANDOM_SEED": str(args.random_seed),
        },
        "system": system_evidence(args.executable.resolve()),
        "source_input_evidence": source_evidence,
        "replay_input_evidence_before_run": replay_evidence,
        "result": result,
        "error": error,
        "log_evidence": log_nan_counters(attempt / "run.log")
        if (attempt / "run.log").exists()
        else None,
        "output_evidence": output_evidence,
    }
    manifest_path = attempt / "attempt-manifest.json"
    digest = write_json(manifest_path, payload)
    print(
        json.dumps(
            {
                "attempt": str(attempt),
                "manifest": str(manifest_path),
                "manifest_sha256": digest,
                "error": error,
            },
            indent=2,
        )
    )
    return 1 if error else 0


def summarize(args: argparse.Namespace) -> int:
    attempt_root = args.attempt_root.resolve()
    records = []
    for manifest_path in sorted(attempt_root.glob("threads-*-replicate-*/attempt-manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        variables = manifest.get("output_evidence", {}).get("variables", {})
        records.append(
            {
                "threads": manifest["threads"],
                "replicate": manifest["replicate"],
                "random_seed": manifest["random_seed"],
                "attempt_directory": manifest["attempt_directory"],
                "attempt_manifest_sha256": sha256(manifest_path),
                "error": manifest["error"],
                "wall_time_seconds": (
                    manifest.get("result", {}).get("wall_time_seconds")
                    if manifest.get("result")
                    else None
                ),
                "executable_sha256": (
                    manifest.get("result", {}).get("executable_sha256")
                    if manifest.get("result")
                    else None
                ),
                "output_sha256": (
                    manifest.get("result", {}).get("output_sha256")
                    if manifest.get("result")
                    else None
                ),
                "science_variables": {
                    name: {
                        "nonfinite_count": item["nonfinite_count"],
                        "negative_finite_count": item["negative_finite_count"],
                        "finite_sum": item["finite_sum"],
                        "nonfinite_signature": [
                            {
                                "index": invalid["index"],
                                "decoded_time": invalid.get("decoded_time"),
                                "coordinates": invalid.get("coordinates"),
                                "value": invalid["value"],
                            }
                            for invalid in item["nonfinite_values"]
                        ],
                    }
                    for name, item in variables.items()
                },
                "first_internal_nan_counter": (
                    manifest.get("log_evidence", {}).get("first_nonzero_counter_line")
                    if manifest.get("log_evidence")
                    else None
                ),
            }
        )
    one_thread_records = [record for record in records if record["threads"] == 1]
    signatures = [
        json.dumps(record["science_variables"], sort_keys=True)
        for record in one_thread_records
    ]
    one_thread_deterministic = (
        len(one_thread_records) >= 3
        and all(record["error"] is None for record in one_thread_records)
        and len(set(signatures)) == 1
    )
    payload = {
        "schema_version": 1,
        "artifact_type": "flexpart-thread-deposition-reproduction-matrix",
        "created_at": datetime.now(UTC).isoformat(),
        "command": [str(item) for item in sys.argv],
        "attempt_root": str(attempt_root),
        "attempt_count": len(records),
        "one_thread_replicate_count": len(one_thread_records),
        "one_thread_deterministic_science_signature": one_thread_deterministic,
        "interpretation": (
            "The exact one-thread science-field signature reproduced in at least three attempts."
            if one_thread_deterministic
            else "The exact one-thread reproduction criterion is not yet satisfied."
        ),
        "attempts": records,
    }
    digest = write_json(args.output.resolve(), payload)
    print(json.dumps({"output": str(args.output.resolve()), "sha256": digest}, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    subparsers = result.add_subparsers(dest="command", required=True)

    baseline_parser = subparsers.add_parser("baseline")
    baseline_parser.add_argument("--failed-member", type=Path, required=True)
    baseline_parser.add_argument("--comparison-member", type=Path, required=True)
    baseline_parser.add_argument("--failed-manifest", type=Path, required=True)
    baseline_parser.add_argument("--comparison-manifest", type=Path, required=True)
    baseline_parser.add_argument("--executable", type=Path)
    baseline_parser.add_argument("--date", default="2026-05-25")
    baseline_parser.add_argument("--species", default="PM25")
    baseline_parser.add_argument("--output", type=Path, required=True)
    baseline_parser.set_defaults(handler=baseline)

    replay_parser = subparsers.add_parser("replay")
    replay_parser.add_argument("--source-member", type=Path, required=True)
    replay_parser.add_argument("--attempt-root", type=Path, required=True)
    replay_parser.add_argument("--executable", type=Path, required=True)
    replay_parser.add_argument("--comparison-output", type=Path, required=True)
    replay_parser.add_argument("--threads", type=int, choices=(1, 2, 4, 8), required=True)
    replay_parser.add_argument("--replicate", type=int, required=True)
    replay_parser.add_argument("--random-seed", type=int, required=True)
    replay_parser.add_argument("--timeout-seconds", type=int, default=10_800)
    replay_parser.add_argument(
        "--maximum-output-bytes",
        type=int,
        default=10 * 1024**3,
    )
    replay_parser.set_defaults(handler=replay)

    summary_parser = subparsers.add_parser("summarize")
    summary_parser.add_argument("--attempt-root", type=Path, required=True)
    summary_parser.add_argument("--output", type=Path, required=True)
    summary_parser.set_defaults(handler=summarize)
    return result


def main() -> int:
    args = parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
