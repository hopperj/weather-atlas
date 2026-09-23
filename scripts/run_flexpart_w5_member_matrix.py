#!/usr/bin/env python3
"""Run the frozen 24-member W5 matrix at one and eight threads."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def completed_attempt(path: Path, executable_sha256: str, seed: int) -> bool:
    manifest = path / "attempt-manifest.json"
    if not manifest.is_file():
        return False
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    return (
        payload.get("error") is None
        and payload.get("result", {}).get("executable_sha256") == executable_sha256
        and payload.get("random_seed") == seed
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-attempt", type=Path, required=True)
    parser.add_argument("--central-attempt", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--one-thread-workers", type=int, default=4)
    arguments = parser.parse_args()
    if not 1 <= arguments.one_thread_workers <= 8:
        parser.error("--one-thread-workers must be from 1 through 8")

    source = arguments.source_attempt.resolve()
    central = arguments.central_attempt.resolve()
    executable = arguments.executable.resolve()
    output = arguments.output_root.resolve()
    executable_sha256 = sha256(executable)
    verification = json.loads(
        (source / "verification/candidate-output-verification.json").read_text(
            encoding="utf-8"
        )
    )
    members = verification["members"]
    if len(members) != 24:
        raise ValueError(f"frozen source matrix has {len(members)} members, expected 24")

    tasks: list[dict[str, Any]] = []
    for member in members:
        day = member["source_day"]
        species = str(member["species"]).lower()
        source_member = source / "transport" / day / species
        comparison = next(
            (central / "transport" / day / species / "output").glob("grid_conc_*.nc")
        )
        for threads in (1, 8):
            attempt_root = output / day / species / f"threads-{threads}"
            attempt = attempt_root / f"threads-{threads}-replicate-01"
            tasks.append(
                {
                    "day": day,
                    "species": species,
                    "threads": threads,
                    "seed": int(member["random_seed"]),
                    "source_member": source_member,
                    "comparison": comparison,
                    "attempt_root": attempt_root,
                    "attempt": attempt,
                }
            )

    runner = Path(__file__).with_name("investigate_flexpart_deposition_failure.py")

    def execute(task: dict[str, Any]) -> dict[str, Any]:
        if completed_attempt(task["attempt"], executable_sha256, task["seed"]):
            status = "reused"
        else:
            command = [
                "uv",
                "run",
                "--frozen",
                "python",
                str(runner),
                "replay",
                "--source-member",
                str(task["source_member"]),
                "--attempt-root",
                str(task["attempt_root"]),
                "--executable",
                str(executable),
                "--comparison-output",
                str(task["comparison"]),
                "--threads",
                str(task["threads"]),
                "--replicate",
                "1",
                "--random-seed",
                str(task["seed"]),
                "--timeout-seconds",
                "1200",
            ]
            process = subprocess.run(
                command,
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                timeout=1500,
                check=False,
            )
            if process.returncode != 0:
                raise RuntimeError(
                    f"W5 replay failed for {task['day']}/{task['species']}/"
                    f"{task['threads']}: {process.stderr[-1000:]}"
                )
            status = "completed"
        manifest = task["attempt"] / "attempt-manifest.json"
        return {
            "day": task["day"],
            "species": task["species"],
            "threads": task["threads"],
            "random_seed": task["seed"],
            "status": status,
            "attempt": str(task["attempt"]),
            "manifest_sha256": sha256(manifest),
        }

    one_thread = [task for task in tasks if task["threads"] == 1]
    eight_thread = [task for task in tasks if task["threads"] == 8]
    records = []
    with ThreadPoolExecutor(max_workers=arguments.one_thread_workers) as executor:
        for index, record in enumerate(executor.map(execute, one_thread), start=1):
            records.append(record)
            print(f"W5 1-thread {index}/{len(one_thread)} complete", flush=True)
    for index, task in enumerate(eight_thread, start=1):
        records.append(execute(task))
        print(f"W5 8-thread {index}/{len(eight_thread)} complete", flush=True)

    manifest_path = output / "member-matrix-run-manifest.json"
    payload = {
        "schema_version": 1,
        "artifact_type": "w5-frozen-24-member-1-and-8-thread-run-matrix",
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_attempt": str(source),
        "central_comparison_attempt": str(central),
        "executable": {
            "path": str(executable),
            "sha256": executable_sha256,
        },
        "expected_member_count": 24,
        "expected_attempt_count": 48,
        "attempt_count": len(records),
        "threads": [1, 8],
        "records": sorted(
            records, key=lambda item: (item["day"], item["species"], item["threads"])
        ),
    }
    atomic_json(manifest_path, payload)
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "manifest_sha256": sha256(manifest_path),
                "attempt_count": len(records),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
