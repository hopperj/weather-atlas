#!/usr/bin/env python3
"""Download and freeze GFAS v1.2 for an input-only validation cohort."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import cdsapi
from weather_ingest.gfas_ads import (
    ADS_API_URL,
    GFAS_DATASET_ID,
    atomic_json,
    build_archive_manifest,
    dates_inclusive,
    load_dotenv_value,
    parse_iso_dates,
    request_filename,
    request_payload,
    sha256,
    split_contiguous_ranges,
    validate_gfas_grib,
)


def _load_ledger_dates(path: Path) -> tuple[str, list]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get("required_acquisition_dates_retained_and_reserve")
    if not isinstance(values, list):
        raise ValueError("source ledger lacks required acquisition dates")
    cohort_id = path.parent.name
    return cohort_id, parse_iso_dates(values)


def _client(token: str) -> cdsapi.Client:
    return cdsapi.Client(
        url=ADS_API_URL,
        key=token,
        quiet=False,
        timeout=900,
    )


def _check_authentication(client: cdsapi.Client) -> None:
    datastore_client = getattr(client, "client", None)
    check = getattr(datastore_client, "check_authentication", None)
    if not callable(check):
        raise RuntimeError("installed cdsapi client cannot perform authenticated ADS checks")
    check()


def _retrieve(
    client: cdsapi.Client,
    *,
    request: dict[str, Any],
    destination: Path,
) -> None:
    temporary = destination.with_name(destination.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        client.retrieve(GFAS_DATASET_ID, request, temporary.as_posix())
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise ValueError("ADS retrieval returned no data")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--dotenv", type=Path, default=Path(".env"))
    parser.add_argument("--maximum-days-per-request", type=int, default=7)
    parser.add_argument("--limit-requests", type=int)
    args = parser.parse_args()
    if args.maximum_days_per_request < 1:
        parser.error("--maximum-days-per-request must be positive")
    if args.limit_requests is not None and args.limit_requests < 1:
        parser.error("--limit-requests must be positive")

    ledger = args.ledger.expanduser().resolve()
    output_directory = args.output_directory.expanduser().resolve()
    if not ledger.is_file() or ledger.is_symlink():
        raise FileNotFoundError(f"source ledger is not a regular file: {ledger}")
    output_directory.mkdir(parents=True, exist_ok=True)
    cohort_id, dates = _load_ledger_dates(ledger)
    ranges = split_contiguous_ranges(dates, maximum_days=args.maximum_days_per_request)
    if args.limit_requests is not None:
        ranges = ranges[: args.limit_requests]

    token = os.environ.get("ADS_PERSONAL_ACCESS_TOKEN") or load_dotenv_value(
        args.dotenv.expanduser().resolve(),
        "ADS_PERSONAL_ACCESS_TOKEN",
    )
    if not token:
        raise RuntimeError("ADS_PERSONAL_ACCESS_TOKEN is not configured")
    client = _client(token)
    _check_authentication(client)

    records = []
    for index, (start, end) in enumerate(ranges, start=1):
        request = request_payload(start, end)
        destination = output_directory / request_filename(start, end)
        expected_dates = dates_inclusive(start, end)
        status = "reused"
        if not destination.is_file():
            status = "downloaded"
            print(
                f"GFAS ADS request {index}/{len(ranges)}: "
                f"{start.isoformat()} through {end.isoformat()}",
                flush=True,
            )
            _retrieve(client, request=request, destination=destination)
        validation = validate_gfas_grib(destination, expected_dates)
        records.append(
            {
                "request_index": index,
                "status": status,
                "request": request,
                "file": {
                    "path": destination.as_posix(),
                    "size_bytes": destination.stat().st_size,
                    "sha256": sha256(destination),
                },
                "validation": validation,
            }
        )
        partial = {
            "artifact_type": "cams-gfas-v1.2-ads-partial-acquisition",
            "schema_version": 1,
            "cohort_id": cohort_id,
            "complete_request_count": len(records),
            "planned_request_count": len(ranges),
            "records": records,
        }
        atomic_json(output_directory / "partial-manifest.json", partial)

    if args.limit_requests is None:
        manifest = build_archive_manifest(
            cohort_id=cohort_id,
            ledger_path=ledger,
            dates=dates,
            records=records,
            request_maximum_days=args.maximum_days_per_request,
        )
        atomic_json(output_directory / "manifest.json", manifest)
        (output_directory / "partial-manifest.json").unlink(missing_ok=True)
        output_path = output_directory / "manifest.json"
    else:
        output_path = output_directory / "partial-manifest.json"
    print(
        json.dumps(
            {
                "status": "complete" if args.limit_requests is None else "partial",
                "request_count": len(records),
                "output": output_path.as_posix(),
                "token_recorded": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
