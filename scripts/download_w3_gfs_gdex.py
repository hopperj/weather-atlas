#!/usr/bin/env python3
"""Download and freeze historical 0.25-degree GFS inputs for frozen W3 overpasses."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from datetime import time as datetime_time
from pathlib import Path
from typing import Any

import httpx
from weather_ingest.downloader import StreamingDownloader
from weather_ingest.models import RemoteObject
from weather_ingest.noaa_gfs import (
    DEFAULT_FORECAST_HOURS,
    GfsIngestionSettings,
    validate_gfs_file,
)

GDEX_HOST = "data.gdex.ucar.edu"
GDEX_DATASET = "d084001"
GDEX_DOI = "10.5065/D65D8PWK"


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


def source_filename(cycle: datetime, forecast_hour: int) -> str:
    return f"gfs.0p25.{cycle:%Y%m%d%H}.f{forecast_hour:03d}.grib2"


def source_url(cycle: datetime, forecast_hour: int) -> str:
    filename = source_filename(cycle, forecast_hour)
    return f"https://{GDEX_HOST}/{GDEX_DATASET}/{cycle:%Y}/{cycle:%Y%m%d}/{filename}"


def relative_path(cycle: datetime, forecast_hour: int) -> Path:
    return Path(
        "raw",
        "noaa",
        "gfs",
        "gdex_d084001_global_0p25",
        f"{cycle:%Y}",
        f"{cycle:%m}",
        f"{cycle:%d}",
        f"{cycle:%H}",
        source_filename(cycle, forecast_hour),
    )


def remote_metadata(
    client: httpx.Client,
    cycle: datetime,
    forecast_hour: int,
) -> RemoteObject:
    url = source_url(cycle, forecast_hour)
    last_error: Exception | None = None
    for attempt in range(1, 6):
        try:
            response = client.head(url)
            response.raise_for_status()
            if response.url.host != GDEX_HOST:
                raise ValueError("GDEX metadata request left the frozen provider host")
            size = int(response.headers["Content-Length"])
            if not 1 <= size <= 1024**3:
                raise ValueError(f"unexpected GDEX object size: {size}")
            return RemoteObject(
                url=url,
                filename=source_filename(cycle, forecast_hour),
                size_bytes=size,
                size_is_exact=True,
                etag=response.headers.get("ETag"),
            )
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt == 5:
                raise
            time.sleep(min(2 ** (attempt - 1), 16))
    raise AssertionError(f"unreachable metadata failure: {last_error}")


def download_one(
    root: Path,
    cycle: datetime,
    forecast_hour: int,
    remote: RemoteObject,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, 6):
        try:
            with StreamingDownloader(
                root,
                allowed_hosts=frozenset({GDEX_HOST}),
                minimum_free_bytes=250 * 1024**3,
                maximum_download_bytes=1024**3,
                timeout_seconds=900,
                user_agent="weather-platform-w3-historical-gfs/1.0",
            ) as downloader:
                result = downloader.download(remote, relative_path(cycle, forecast_hour))
            return {
                "initialization_time": cycle.isoformat().replace("+00:00", "Z"),
                "valid_time": (cycle + timedelta(hours=forecast_hour))
                .isoformat()
                .replace("+00:00", "Z"),
                "forecast_hour": forecast_hour,
                "filename": source_filename(cycle, forecast_hour),
                "source_url": remote.url,
                "relative_path": relative_path(cycle, forecast_hour).as_posix(),
                "size_bytes": result.size_bytes,
                "sha256": result.sha256,
                "reused_existing": result.reused_existing,
            }
        except (httpx.HTTPError, OSError) as exc:
            last_error = exc
            if attempt == 5:
                raise
            time.sleep(min(2 ** (attempt - 1), 16))
    raise AssertionError(f"unreachable download failure: {last_error}")


def overpass_dates(vertical: dict[str, Any]) -> dict[str, date]:
    result = {}
    for overpass in vertical["overpasses"]:
        values = {
            datetime.fromisoformat(value.replace("Z", "+00:00")).date()
            for value in overpass["acquisition_times"]
        }
        if len(values) != 1:
            raise ValueError(f"overpass crosses UTC dates: {overpass['overpass_id']}")
        result[str(overpass["overpass_id"])] = values.pop()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vertical-ledger", type=Path, required=True)
    parser.add_argument("--assignment-ledger", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--spinup-days", type=int, default=1)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument(
        "--skip-content-validation",
        action="store_true",
        help="Only for acquisition recovery; such records remain incomplete.",
    )
    args = parser.parse_args()
    if args.spinup_days < 1 or not 1 <= args.workers <= 10:
        parser.error("spin-up must be positive and workers must be in 1..10")

    vertical_path = args.vertical_ledger.expanduser().resolve()
    assignment_path = args.assignment_ledger.expanduser().resolve()
    root = args.data_root.expanduser().resolve()
    vertical = json.loads(vertical_path.read_text(encoding="utf-8"))
    assignment = json.loads(assignment_path.read_text(encoding="utf-8"))
    selected = {
        str(item["overpass_id"])
        for item in assignment["assignments"]
        if item["status"] != "excluded_input_invalid"
    }
    dates = overpass_dates(vertical)
    if not selected.issubset(dates):
        raise ValueError("assignment ledger refers to unknown overpasses")
    required_cycles = sorted(
        {
            datetime.combine(
                dates[overpass_id] - timedelta(days=offset),
                datetime_time(),
                tzinfo=UTC,
            )
            for overpass_id in selected
            for offset in range(args.spinup_days + 1)
        }
    )
    requests = [
        (cycle, forecast_hour)
        for cycle in required_cycles
        for forecast_hour in DEFAULT_FORECAST_HOURS
    ]
    with (
        httpx.Client(
            timeout=httpx.Timeout(120, connect=20),
            follow_redirects=True,
            headers={"User-Agent": "weather-platform-w3-historical-gfs/1.0"},
        ) as client,
        ThreadPoolExecutor(max_workers=args.workers) as executor,
    ):
        metadata_futures = {
            request: executor.submit(remote_metadata, client, *request) for request in requests
        }
        remotes = {}
        for index, (request, future) in enumerate(metadata_futures.items(), start=1):
            remotes[request] = future.result()
            if index <= args.workers or index % 50 == 0 or index == len(requests):
                print(
                    f"GDEX GFS metadata {index}/{len(requests)} files",
                    flush=True,
                )
    estimated_bytes = sum(int(remote.size_bytes or 0) for remote in remotes.values())
    print(
        json.dumps(
            {
                "stage": "discovered",
                "cycle_count": len(required_cycles),
                "file_count": len(requests),
                "estimated_bytes": estimated_bytes,
            }
        ),
        flush=True,
    )
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(download_one, root, cycle, hour, remotes[(cycle, hour)])
            for cycle, hour in requests
        ]
        for index, future in enumerate(futures, start=1):
            results.append(future.result())
            if index <= args.workers or index % 10 == 0 or index == len(futures):
                print(f"GDEX GFS {index}/{len(futures)} files", flush=True)

    settings = GfsIngestionSettings(
        resolution="0p25",
        forecast_hours=DEFAULT_FORECAST_HOURS,
        minimum_free_bytes=250 * 1024**3,
        maximum_download_bytes=1024**3,
        timeout_seconds=900,
    )
    if not args.skip_content_validation:
        for index, record in enumerate(results, start=1):
            cycle = datetime.fromisoformat(
                str(record["initialization_time"]).replace("Z", "+00:00")
            )
            validation = validate_gfs_file(
                root / str(record["relative_path"]),
                cycle=cycle,
                forecast_hour=int(record["forecast_hour"]),
                settings=settings,
            )
            record["validation"] = validation
            if index <= 3 or index % 10 == 0 or index == len(results):
                print(f"GDEX GFS validated {index}/{len(results)} files", flush=True)

    by_cycle: dict[str, list[dict[str, Any]]] = {}
    for record in results:
        by_cycle.setdefault(str(record["initialization_time"]), []).append(record)
    cycle_records = []
    for cycle_text, files in sorted(by_cycle.items()):
        cycle = datetime.fromisoformat(cycle_text.replace("Z", "+00:00"))
        cycle_directory = root / relative_path(cycle, 0).parent
        manifest_path = cycle_directory / "manifest.json"
        payload = {
            "schema_version": 1,
            # Keep the normalized fields consumed by gfs_profiles and the
            # FLEXPART runner exact. Archive-specific provenance remains
            # explicit in a separate object.
            "provider": "noaa",
            "product": "gfs",
            "archive": {
                "name": "NSF NCAR GDEX",
                "dataset_id": GDEX_DATASET,
                "doi": GDEX_DOI,
                "base_url": f"https://{GDEX_HOST}/{GDEX_DATASET}",
            },
            "initialization_time": cycle_text,
            "forecast_hours": list(DEFAULT_FORECAST_HOURS),
            "resolution": "0p25",
            "grid_dimensions": [1440, 721],
            "status": (
                "complete_validated"
                if not args.skip_content_validation
                else "downloaded_not_content_validated"
            ),
            "files": sorted(files, key=lambda item: int(item["forecast_hour"])),
        }
        atomic_json(manifest_path, payload)
        cycle_records.append(
            {
                "initialization_time": cycle_text,
                "manifest_path": manifest_path.as_posix(),
                "manifest_sha256": sha256(manifest_path),
                "file_count": len(files),
                "total_bytes": sum(int(item["size_bytes"]) for item in files),
            }
        )

    cycle_by_day = {
        datetime.fromisoformat(item["initialization_time"].replace("Z", "+00:00")).date(): item
        for item in cycle_records
    }
    records = []
    for overpass_id in sorted(selected):
        day = dates[overpass_id]
        required = [
            cycle_by_day[day - timedelta(days=offset)]
            for offset in reversed(range(args.spinup_days + 1))
        ]
        records.append(
            {
                "overpass_id": overpass_id,
                "status": (
                    "complete"
                    if not args.skip_content_validation
                    else "downloaded_not_content_validated"
                ),
                "overpass_date_utc": day.isoformat(),
                "spinup_days": args.spinup_days,
                "cycles": required,
            }
        )
    payload = {
        "schema_version": 1,
        "artifact_type": "w3-historical-gfs-gdex-acquisition-ledger",
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": ("complete" if not args.skip_content_validation else "incomplete_validation"),
        "source": {
            "provider": "NOAA NCEP",
            "archive": "NSF NCAR GDEX",
            "dataset_id": GDEX_DATASET,
            "doi": GDEX_DOI,
            "base_url": f"https://{GDEX_HOST}/{GDEX_DATASET}",
        },
        "selection_firewall": {
            "plume_height_accessed": False,
            "candidate_output_accessed": False,
            "selection": "all input-valid frozen W3 overpasses plus fixed spin-up",
        },
        "policy": {
            "resolution": "0p25",
            "cycle": "00Z",
            "forecast_hours": list(DEFAULT_FORECAST_HOURS),
            "spinup_days": args.spinup_days,
        },
        "vertical_ledger": {
            "path": vertical_path.as_posix(),
            "sha256": sha256(vertical_path),
        },
        "assignment_ledger": {
            "path": assignment_path.as_posix(),
            "sha256": sha256(assignment_path),
        },
        "cycle_count": len(cycle_records),
        "file_count": len(results),
        "total_bytes": sum(int(item["size_bytes"]) for item in results),
        "cycles": cycle_records,
        "records": records,
    }
    atomic_json(args.output.expanduser().resolve(), payload)
    print(
        json.dumps(
            {
                "output": args.output.expanduser().resolve().as_posix(),
                "sha256": sha256(args.output.expanduser().resolve()),
                "cycle_count": payload["cycle_count"],
                "file_count": payload["file_count"],
                "total_bytes": payload["total_bytes"],
                "status": payload["status"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if payload["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
