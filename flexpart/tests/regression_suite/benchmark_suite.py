#!/usr/bin/env python3
"""Run repeatable, interleaved FLEXPART CPU-scaling benchmarks."""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import statistics
from datetime import datetime, timezone
from pathlib import Path

from run_suite import CASES_FILE, run_case


def parse_variant(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("variant must be NAME=EXECUTABLE_DIRECTORY")
    name, path = value.split("=", 1)
    if not name or not path:
        raise argparse.ArgumentTypeError("variant must be NAME=EXECUTABLE_DIRECTORY")
    return name, Path(path).resolve()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant",
        action="append",
        type=parse_variant,
        required=True,
        help="Benchmark variant as NAME=directory containing FLEXPART",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--particles", type=int, default=1_000_000)
    parser.add_argument("--threads", nargs="+", type=int, default=[1, 2, 4, 8, 16])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    if args.particles < 1 or args.repeats < 1 or any(item < 1 for item in args.threads):
        raise SystemExit("particles, repeats, and thread counts must be positive")
    variant_names = [name for name, _ in args.variant]
    if len(set(variant_names)) != len(variant_names):
        raise SystemExit("variant names must be unique")

    root = args.output.resolve()
    if root.exists():
        if not args.replace:
            raise SystemExit(f"Output already exists: {root}; use --replace")
        shutil.rmtree(root)
    root.mkdir(parents=True)

    config = json.loads(CASES_FILE.read_text())
    template = next(
        item for item in config["cases"] if item["name"] == "22_parallel_stress"
    )
    benchmark_profile = copy.deepcopy(config["release_profiles"]["stress_multispecies"])
    benchmark_profile[0]["parts"] = args.particles
    config["release_profiles"]["benchmark_multispecies"] = benchmark_profile

    records: list[dict[str, object]] = []
    completed: dict[str, Path] = {}
    failed = 0
    for repeat in range(1, args.repeats + 1):
        variants = args.variant if repeat % 2 else list(reversed(args.variant))
        for threads in args.threads:
            for variant, executable_root in variants:
                case = copy.deepcopy(template)
                case["name"] = (
                    f"benchmark_{variant}_t{threads:02d}_r{repeat:02d}"
                )
                case["description"] = (
                    f"{args.particles:,}-particle all-physics benchmark; "
                    f"variant={variant}, threads={threads}, repeat={repeat}"
                )
                case["threads"] = threads
                case["releases"] = "benchmark_multispecies"
                case["command"]["MAXTHREADGRID"] = threads
                manifest = run_case(
                    case, config, root, executable_root, completed
                )
                record = {
                    "variant": variant,
                    "threads": threads,
                    "repeat": repeat,
                    "particles": args.particles,
                    "passed": manifest["passed"],
                    "runtime_seconds": manifest["runtime_seconds"],
                    "executable": manifest["executable"],
                    "executable_sha256": manifest["executable_sha256"],
                    "case": case["name"],
                }
                records.append(record)
                failed += not manifest["passed"]
                (root / "benchmark_manifest.json").write_text(
                    json.dumps({"runs": records}, indent=2, sort_keys=True) + "\n"
                )

    summary: dict[str, dict[str, dict[str, float]]] = {}
    for variant, _ in args.variant:
        summary[variant] = {}
        single_thread_median = statistics.median(
            float(item["runtime_seconds"])
            for item in records
            if item["variant"] == variant and item["threads"] == args.threads[0]
        )
        for threads in args.threads:
            samples = [
                float(item["runtime_seconds"])
                for item in records
                if item["variant"] == variant and item["threads"] == threads
            ]
            median = statistics.median(samples)
            summary[variant][str(threads)] = {
                "minimum_seconds": min(samples),
                "median_seconds": median,
                "maximum_seconds": max(samples),
                "speedup_from_first_thread_count": single_thread_median / median,
                "samples": len(samples),
            }

    result = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "particles": args.particles,
        "threads": args.threads,
        "repeats": args.repeats,
        "failed_count": failed,
        "runs": records,
        "summary": summary,
    }
    (root / "benchmark_manifest.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
