#!/usr/bin/env python3
"""Freeze fire-event eligibility before running an external smoke comparison."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml
from weather_ingest.fbp_fuels import resolve_fbp_fuel
from weather_ingest.fire_events import Detection, EventMatchingConfig, reconcile_events


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _number(value: str, *, field: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"invalid {field}: {value!r}") from exc


def _detection_id(observed: datetime, latitude: float, longitude: float, sensor: str) -> str:
    utc = observed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    identity = f"{utc}|{latitude:.5f}|{longitude:.5f}|{sensor}"
    return hashlib.sha256(identity.encode()).hexdigest()[:24]


def _load_candidate_detections(
    path: Path,
    *,
    start: date,
    end: date,
    crosswalk_path: Path,
) -> tuple[list[Detection], dict[str, Any]]:
    crosswalk_payload = yaml.safe_load(crosswalk_path.read_text(encoding="utf-8"))
    crosswalk = {str(key).upper(): str(value) for key, value in crosswalk_payload["rules"].items()}
    detections: dict[str, Detection] = {}
    raw_rows = 0
    interval_rows = 0
    canadian_rows = 0
    viirs_rows = 0
    exclusion_reasons: Counter[str] = Counter()
    date_counts: Counter[str] = Counter()
    fuel_counts: Counter[str] = Counter()
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source, skipinitialspace=True)
        required = {"rep_date", "sensor", "lat", "lon", "country", "fuel", "ffmc", "dmc", "dc"}
        missing = required.difference(reader.fieldnames or ())
        if missing:
            raise ValueError(f"hotspot archive is missing columns: {sorted(missing)}")
        has_estarea = "estarea" in (reader.fieldnames or ())
        for row in reader:
            raw_rows += 1
            observed = datetime.strptime(row["rep_date"], "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=UTC
            )
            if not start <= observed.date() <= end:
                exclusion_reasons["outside_interval"] += 1
                continue
            interval_rows += 1
            if row["country"].strip().upper() != "C":
                exclusion_reasons["outside_canada"] += 1
                continue
            canadian_rows += 1
            if row["sensor"].strip() != "VIIRS-I":
                exclusion_reasons["not_viirs_i"] += 1
                continue
            viirs_rows += 1
            fuel = row["fuel"].strip()
            resolved = resolve_fbp_fuel(fuel, crosswalk)
            if resolved is None:
                exclusion_reasons[f"unsupported_fuel:{fuel or 'blank'}"] += 1
                continue
            latitude = _number(row["lat"], field="latitude")
            longitude = _number(row["lon"], field="longitude")
            sensor = row["sensor"].strip()
            detection_id = _detection_id(observed, latitude, longitude, sensor)
            properties = {
                "detection_id": detection_id,
                "observed_at": observed.isoformat().replace("+00:00", "Z"),
                "source": row.get("source", "").strip(),
                "sensor": sensor,
                "fuel": fuel,
                "model_fuel": resolved.model_code,
                "ffmc": _number(row["ffmc"], field="ffmc"),
                "dmc": _number(row["dmc"], field="dmc"),
                "dc": _number(row["dc"], field="dc"),
                "frp": _number(row.get("frp", "0") or "0", field="frp"),
            }
            if has_estarea and row.get("estarea", "").strip():
                properties["estarea"] = _number(row["estarea"], field="estarea")
            candidate = Detection(
                detection_id=detection_id,
                observed_at=observed,
                latitude=latitude,
                longitude=longitude,
                fuel=resolved.model_code,
                properties=properties,
            )
            existing = detections.get(detection_id)
            if existing is not None and existing != candidate:
                raise ValueError(f"conflicting duplicate detection {detection_id}")
            if existing is not None:
                exclusion_reasons["exact_duplicate_detection"] += 1
                continue
            detections[detection_id] = candidate
            date_counts[observed.date().isoformat()] += 1
            fuel_counts[resolved.model_code] += 1
    return sorted(detections.values(), key=lambda item: item.detection_id), {
        "source": {
            "path": path.as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "columns": reader.fieldnames,
        },
        "raw_row_count": raw_rows,
        "interval_row_count": interval_rows,
        "canadian_row_count": canadian_rows,
        "canadian_viirs_i_row_count": viirs_rows,
        "candidate_detection_count": len(detections),
        "has_estarea_column": has_estarea,
        "date_counts": dict(sorted(date_counts.items())),
        "fuel_counts": dict(sorted(fuel_counts.items())),
        "exclusion_reasons": dict(sorted(exclusion_reasons.items())),
        "fuel_crosswalk": {
            "path": crosswalk_path.as_posix(),
            "sha256": _sha256(crosswalk_path),
            "version": crosswalk_payload["crosswalk_version"],
        },
    }


def _perimeter_summary(path: Path, *, start: date, end: date) -> dict[str, Any]:
    ogr2ogr = shutil.which("ogr2ogr")
    if ogr2ogr is None:
        raise FileNotFoundError("ogr2ogr is required to audit the perimeter archive")
    with tempfile.TemporaryDirectory(prefix="smoke-perimeter-audit-") as temporary:
        csv_path = Path(temporary) / "perimeters.csv"
        process = subprocess.run(
            [
                ogr2ogr,
                "-f",
                "CSV",
                csv_path.as_posix(),
                f"/vsizip/{path.resolve()}",
                "cc_apt_buf",
                "-select",
                "UID,HCOUNT,AREA,FIRSTDATE,LASTDATE,CONSIS_ID",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if process.returncode != 0:
            raise RuntimeError(f"ogr2ogr perimeter extraction failed: {process.stderr[-1000:]}")
        rows = list(csv.DictReader(csv_path.open(newline="", encoding="utf-8")))
    first_dates = [datetime.strptime(row["FIRSTDATE"], "%Y-%m-%d %H:%M:%S") for row in rows]
    last_dates = [datetime.strptime(row["LASTDATE"], "%Y-%m-%d %H:%M:%S") for row in rows]
    in_window = [
        row
        for row, first, last in zip(rows, first_dates, last_dates, strict=True)
        if first.date() <= end and last.date() >= start
    ]
    version = subprocess.run(
        [ogr2ogr, "--version"], capture_output=True, text=True, timeout=15, check=True
    ).stdout.strip()
    return {
        "source": {
            "path": path.as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        },
        "feature_count": len(rows),
        "first_detection": min(first_dates).isoformat(),
        "last_detection": max(last_dates).isoformat(),
        "overlapping_interval_feature_count": len(in_window),
        "ogr2ogr_version": version,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hotspots", type=Path, required=True)
    parser.add_argument("--perimeters", type=Path, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--event-config", type=Path, default=Path("config/smoke/event_matching.yaml")
    )
    parser.add_argument(
        "--fuel-crosswalk", type=Path, default=Path("config/smoke/fuel_crosswalk.yaml")
    )
    parser.add_argument("--mcd64-cmr", type=Path)
    parser.add_argument("--protocol", type=Path, default=Path("docs/smoke-validation-protocol.md"))
    parser.add_argument("--thresholds", type=Path, default=Path("config/smoke/validation.yaml"))
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()

    detections, hotspot_summary = _load_candidate_detections(
        args.hotspots,
        start=args.start,
        end=args.end,
        crosswalk_path=args.fuel_crosswalk,
    )
    config = EventMatchingConfig.from_yaml(args.event_config)
    event_snapshot = reconcile_events(detections, config)
    event_snapshot["source_hotspots_sha256"] = hotspot_summary["source"]["sha256"]
    args.output_directory.mkdir(parents=True, exist_ok=True)
    events_path = args.output_directory / "candidate-events.json"
    _atomic_json(events_path, event_snapshot)

    perimeter_summary = _perimeter_summary(
        args.perimeters, start=args.start, end=args.end
    )
    mcd64 = None
    if args.mcd64_cmr:
        payload = json.loads(args.mcd64_cmr.read_text(encoding="utf-8"))
        entries = payload.get("feed", {}).get("entry", [])
        mcd64 = {
            "catalogue_path": args.mcd64_cmr.as_posix(),
            "catalogue_sha256": _sha256(args.mcd64_cmr),
            "catalogue_entry_count": len(entries),
            "data_access_status": "requires_nasa_earthdata_authorization",
            "downloaded_granule_count": 0,
        }

    # The annual hotspot file has no area. Even if a final buffered perimeter
    # overlaps an interval, it does not provide daily growth. This audit has no
    # independently observed area progression until MCD64A1 pixels are acquired
    # and associated with the frozen events.
    independent_area_available = False
    software_paths = {
        "eligibility_audit": Path(__file__).resolve(),
        "event_reconciliation": Path("python/weather_ingest/fire_events.py"),
        "fuel_resolution": Path("python/weather_ingest/fbp_fuels.py"),
        "gfas_pair_builder": Path("python/weather_ingest/gfas_intercomparison.py"),
        "evaluation_metrics": Path("python/weather_ingest/smoke_evaluation.py"),
        "protocol": args.protocol,
        "thresholds": args.thresholds,
    }
    report = {
        "schema_version": 1,
        "experiment_interval": {
            "start": args.start.isoformat(),
            "end_inclusive": args.end.isoformat(),
        },
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": (
            "eligible_area_source_present"
            if independent_area_available
            else "blocked_missing_independent_daily_burned_area"
        ),
        "scientific_candidate_run_started": False,
        "software_provenance": {
            "python": sys.version,
            "platform": platform.platform(),
            "files": {
                name: {"path": path.as_posix(), "sha256": _sha256(path)}
                for name, path in software_paths.items()
            },
        },
        "hotspots": hotspot_summary,
        "event_reconciliation": {
            "config_path": args.event_config.as_posix(),
            "config_sha256": _sha256(args.event_config),
            "event_count": event_snapshot["event_count"],
            "detection_count": event_snapshot["detection_count"],
            "candidate_events_path": events_path.as_posix(),
            "candidate_events_sha256": _sha256(events_path),
        },
        "perimeters": perimeter_summary,
        "mcd64a1_v61": mcd64,
        "independent_daily_burned_area_available": independent_area_available,
        "independently_area_constrained_event_count": 0,
        "prohibited_shortcuts": [
            "do_not_infer_area_from_detection_count",
            "do_not_seed_cffeps_from_gfas_for_a_gfas_intercomparison",
            "do_not_treat_final_perimeter_area_as_daily_growth_without_dates",
        ],
        "next_action": (
            "download and QA MCD64A1 v6.1 Burn_Date/QA granules with NASA Earthdata "
            "authorization, then spatially join burn pixels to frozen candidate events"
        ),
    }
    report_path = args.output_directory / "eligibility-report.json"
    _atomic_json(report_path, report)
    print(json.dumps(report | {"report_sha256": _sha256(report_path)}, indent=2, sort_keys=True))
    return 0 if independent_area_available else 2


if __name__ == "__main__":
    raise SystemExit(main())
