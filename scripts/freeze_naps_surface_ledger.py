#!/usr/bin/env python3
"""Freeze an input-only final-NAPS surface observation availability ledger."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
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


def data_rows(path: Path) -> csv.DictReader:
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if line.startswith("Pollutant//Polluant,Method Code//Code Méthode")
        ),
        None,
    )
    if header_index is None:
        raise ValueError("NAPS data header not found")
    return csv.DictReader(io.StringIO("\n".join(lines[header_index:])))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--naps", type=Path, required=True)
    parser.add_argument("--naps-manifest", type=Path, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--minimum-valid-hours", type=int, default=200)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    if args.end < args.start:
        parser.error("--end must not precede --start")
    if args.minimum_valid_hours < 100:
        parser.error("--minimum-valid-hours must be at least 100")

    source_manifest = json.loads(args.naps_manifest.read_text(encoding="utf-8"))
    if source_manifest.get("scientific_contract", {}).get("archive_status") != (
        "final_provider_archive"
    ):
        raise ValueError("NAPS source manifest is not marked as final provider data")
    if source_manifest["file"]["sha256"] != sha256(args.naps):
        raise ValueError("NAPS source hash does not match its manifest")

    station_methods: dict[tuple[str, str], dict[str, Any]] = {}
    exclusion_counts: defaultdict[str, int] = defaultdict(int)
    for row in data_rows(args.naps):
        row_date = date.fromisoformat(row["Date//Date"].strip())
        if not args.start <= row_date <= args.end:
            exclusion_counts["outside_period_row"] += 1
            continue
        station_id = row["NAPS ID//Identifiant SNPA"].strip()
        method_code = row["Method Code//Code Méthode"].strip()
        key = (station_id, method_code)
        entry = station_methods.setdefault(
            key,
            {
                "station_id": station_id,
                "method_code": method_code,
                "city": row["City//Ville"].strip(),
                "province_or_territory": row[
                    "Province/Territory//Province/Territoire"
                ].strip(),
                "latitude": float(row["Latitude//Latitude"]),
                "longitude": float(row["Longitude//Longitude"]),
                "dates_with_data": set(),
                "valid_hour_count": 0,
                "missing_hour_count": 0,
            },
        )
        if (
            entry["latitude"] != float(row["Latitude//Latitude"])
            or entry["longitude"] != float(row["Longitude//Longitude"])
        ):
            raise ValueError(
                f"station {station_id} method {method_code} changes coordinates "
                "inside the candidate period"
            )
        valid_on_date = False
        for hour in range(1, 25):
            raw = row[f"H{hour:02d}//H{hour:02d}"].strip()
            if raw in {"", "-999"}:
                entry["missing_hour_count"] += 1
            else:
                # Deliberately validate syntax without storing or ranking on
                # the observed concentration magnitude.
                float(raw)
                entry["valid_hour_count"] += 1
                valid_on_date = True
        if valid_on_date:
            entry["dates_with_data"].add(row_date.isoformat())

    by_station: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in station_methods.values():
        entry["dates_with_data"] = sorted(entry["dates_with_data"])
        by_station[str(entry["station_id"])].append(entry)

    selected = []
    alternatives = []
    for station_id, methods in sorted(by_station.items()):
        # A deterministic completeness rule selects the primary instrument:
        # most valid hours, then lowest method code. Concentration magnitude
        # and all model quantities are absent from this ordering.
        ranked = sorted(
            methods,
            key=lambda item: (
                -int(item["valid_hour_count"]),
                str(item["method_code"]),
            ),
        )
        primary = ranked[0]
        primary["selection_rule"] = (
            "maximum valid-hour availability; method-code lexical tie-break"
        )
        if int(primary["valid_hour_count"]) >= args.minimum_valid_hours:
            selected.append(primary)
            alternatives.extend(
                {
                    **item,
                    "alternative_for_station": station_id,
                    "exclusion_reason": "non_primary_parallel_method",
                }
                for item in ranked[1:]
            )
        else:
            exclusion_counts["station_below_minimum_valid_hours"] += 1
            alternatives.extend(
                {
                    **item,
                    "alternative_for_station": station_id,
                    "exclusion_reason": "station_below_minimum_valid_hours",
                }
                for item in ranked
            )

    provinces = sorted(
        {str(item["province_or_territory"]) for item in selected}
    )
    total_candidate_hours = sum(int(item["valid_hour_count"]) for item in selected)
    if len(selected) < 10 or total_candidate_hours < 200:
        raise ValueError(
            "surface availability ledger does not meet prospective W4 capacity"
        )
    ledger = {
        "artifact_type": "w1-input-only-final-naps-surface-ledger",
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "frozen_prospective_observation_availability",
        "period": {
            "start": args.start.isoformat(),
            "end": args.end.isoformat(),
        },
        "source": {
            "naps_path": args.naps.resolve().as_posix(),
            "naps_sha256": sha256(args.naps),
            "naps_manifest_path": args.naps_manifest.resolve().as_posix(),
            "naps_manifest_sha256": sha256(args.naps_manifest),
            "provider_time_basis": "hour_ending_local_standard_time",
        },
        "selection_rules": {
            "minimum_valid_hours_per_station": args.minimum_valid_hours,
            "primary_method": (
                "maximum valid-hour availability; method-code lexical tie-break"
            ),
            "observed_concentration_magnitude_used_for_selection": False,
            "model_output_or_performance_used_for_selection": False,
            "w4_pairing_requirement": (
                "W4 must convert local standard time to UTC, apply station-history "
                "and QA screens, match frozen fire domains, and build backgrounds."
            ),
        },
        "station_count": len(selected),
        "province_or_territory_count": len(provinces),
        "provinces_or_territories": provinces,
        "candidate_valid_hour_count": total_candidate_hours,
        "stations": selected,
        "non_primary_or_ineligible_methods": alternatives,
        "exclusion_counts": dict(sorted(exclusion_counts.items())),
        "selection_firewall": {
            "flexpart_output_accessed": False,
            "observed_concentration_retained": False,
            "predicted_observed_residual_accessed": False,
            "availability_flags_only": True,
        },
    }
    output = args.output_directory.resolve() / "surface-ledger.json"
    atomic_json(output, ledger)
    freeze = {
        "ledger": {
            "path": output.as_posix(),
            "size_bytes": output.stat().st_size,
            "sha256": sha256(output),
        },
        "station_count": len(selected),
        "candidate_valid_hour_count": total_candidate_hours,
    }
    atomic_json(args.output_directory.resolve() / "surface-ledger.freeze.json", freeze)
    print(json.dumps(freeze, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
