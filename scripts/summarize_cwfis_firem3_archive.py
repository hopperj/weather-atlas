#!/usr/bin/env python3
"""Summarize a Fire M3 archive for input-only cohort feasibility."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import zipfile
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

CFFDRS_FIELDS = ("ffmc", "dmc", "dc")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.part")
    temporary.unlink(missing_ok=True)
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def ranked(counter: Counter[str]) -> list[dict[str, Any]]:
    return [
        {"value": value, "count": count}
        for value, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def finite_field(row: dict[str, str], field: str) -> bool:
    text = row.get(field, "").strip()
    if not text:
        return False
    try:
        return math.isfinite(float(text))
    except ValueError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--acquisition-manifest", type=Path, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.end < args.start:
        parser.error("--end must not precede --start")

    archive_path = args.archive.resolve()
    acquisition_manifest = args.acquisition_manifest.resolve()
    acquisition = json.loads(acquisition_manifest.read_text(encoding="utf-8"))
    archive_digest = sha256(archive_path)
    if acquisition["file"]["sha256"] != archive_digest:
        raise ValueError("Fire M3 archive does not match its acquisition manifest")

    counters = {
        name: Counter()
        for name in ("date", "agency", "ecozone", "fuel", "sensor", "satellite")
    }
    missing = Counter()
    zero = Counter()
    total_rows = 0
    period_rows = 0
    canadian_rows = 0
    complete_cffdrs_rows = 0
    invalid_coordinate_rows = 0
    fieldnames: list[str] | None = None
    with zipfile.ZipFile(archive_path) as archive:
        csv_members = [item for item in archive.namelist() if item.lower().endswith(".csv")]
        if len(csv_members) != 1:
            raise ValueError("expected exactly one CSV in the annual Fire M3 archive")
        with archive.open(csv_members[0]) as source:
            reader = csv.DictReader(io.TextIOWrapper(source, encoding="utf-8-sig", newline=""))
            if reader.fieldnames is None:
                raise ValueError("Fire M3 CSV has no header")
            fieldnames = reader.fieldnames
            required = {
                "rep_date",
                "country",
                "agency",
                "ecozone",
                "fuel",
                "sensor",
                "satellite",
                "lat",
                "lon",
                *CFFDRS_FIELDS,
            }
            absent = required - set(reader.fieldnames)
            if absent:
                raise ValueError(f"Fire M3 CSV lacks required fields: {sorted(absent)}")
            for row in reader:
                total_rows += 1
                observed = date.fromisoformat(row["rep_date"][:10])
                if not args.start <= observed <= args.end:
                    continue
                period_rows += 1
                if row["country"].strip().upper() != "C":
                    continue
                canadian_rows += 1
                counters["date"][observed.isoformat()] += 1
                for name in ("agency", "ecozone", "fuel", "sensor", "satellite"):
                    counters[name][row[name].strip() or "(blank)"] += 1
                coordinate_valid = True
                for field in ("lat", "lon"):
                    if not finite_field(row, field):
                        coordinate_valid = False
                if not coordinate_valid:
                    invalid_coordinate_rows += 1
                complete = True
                for field in CFFDRS_FIELDS:
                    if not finite_field(row, field):
                        missing[field] += 1
                        complete = False
                        continue
                    if float(row[field]) == 0:
                        zero[field] += 1
                if complete:
                    complete_cffdrs_rows += 1

    payload = {
        "schema_version": 1,
        "artifact_type": "cwfis-firem3-input-only-period-summary",
        "created_at": datetime.now(UTC).isoformat(),
        "selection_firewall": {
            "model_output_opened": False,
            "model_performance_used": False,
            "event_selection_performed": False,
        },
        "period": {"start": args.start.isoformat(), "end": args.end.isoformat()},
        "source": {
            "archive": str(archive_path),
            "archive_bytes": archive_path.stat().st_size,
            "archive_sha256": archive_digest,
            "acquisition_manifest": str(acquisition_manifest),
            "acquisition_manifest_sha256": sha256(acquisition_manifest),
            "source_url": acquisition["source_url"],
            "csv_member": csv_members[0],
            "csv_fieldnames": fieldnames,
        },
        "counts": {
            "annual_rows_scanned": total_rows,
            "all_country_period_rows": period_rows,
            "canadian_period_rows": canadian_rows,
            "canadian_unique_dates": len(counters["date"]),
            "canadian_first_date": min(counters["date"]) if counters["date"] else None,
            "canadian_last_date": max(counters["date"]) if counters["date"] else None,
            "invalid_coordinate_rows": invalid_coordinate_rows,
            "complete_ffmc_dmc_dc_rows": complete_cffdrs_rows,
            "complete_ffmc_dmc_dc_fraction": (
                complete_cffdrs_rows / canadian_rows if canadian_rows else None
            ),
        },
        "cffdrs_missing_counts": dict(sorted(missing.items())),
        "cffdrs_zero_counts": dict(sorted(zero.items())),
        "distributions": {name: ranked(counter) for name, counter in counters.items()},
        "interpretation": [
            "This is detection-level input availability, not an event ledger.",
            "Fire M3 estimated area and hotspot count are not independent burned area.",
            "Event clustering and MCD64A1 area strata remain to be completed before selection.",
        ],
    }
    atomic_json(args.output.resolve(), payload)
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "sha256": sha256(args.output.resolve()),
                "counts": payload["counts"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
