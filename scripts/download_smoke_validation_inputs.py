#!/usr/bin/env python3
"""Backfill immutable GFS, CFFDRS, and CWFIS inputs for a smoke experiment."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import shutil
import subprocess
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx
from weather_ingest.cwfis_cffdrs import (
    CwfisCffdrsSettings,
    ingest_date,
    load_complete_manifest,
)
from weather_ingest.downloader import StreamingDownloader
from weather_ingest.gfs_profiles import resolve_complete_cycle
from weather_ingest.models import RemoteObject
from weather_ingest.noaa_gfs import (
    DEFAULT_FORECAST_HOURS,
    GFS_ARCHIVE_BASE_URL,
    GFS_ARCHIVE_HOST,
    GfsIngestionSettings,
    cycle_relative_directory,
    gfs_archive_object_url,
    gfs_filename,
    object_relative_path,
    validate_gfs_file,
    write_cycle_manifests,
)

HOTSPOT_ARCHIVE_URL = "https://cwfis.cfs.nrcan.gc.ca/downloads/hotspots/archive/2025_hotspots.zip"
PERIMETER_ARCHIVE_URL = (
    "https://cwfis.cfs.nrcan.gc.ca/downloads/hotspots/archive/2025_perimeters.zip"
)
GFAS_DATASET_URL = "https://ads.atmosphere.copernicus.eu/datasets/cams-global-fire-emissions-gfas"
GFAS_REQUIRED_PARAMETERS = frozenset(
    {
        "apb",
        "apt",
        "bcfire",
        "cofire",
        "crfire",
        "frpfire",
        "injh",
        "offire",
        "pm2p5fire",
    }
)


def _dates(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _complete_gfs_manifest(root: Path, cycle: datetime) -> bool:
    manifest = root / cycle_relative_directory(GfsIngestionSettings(), cycle) / "manifest.json"
    try:
        payload, files = resolve_complete_cycle(manifest)
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return False
    return (
        payload.get("initialization_time") == cycle.isoformat().replace("+00:00", "Z")
        and payload.get("forecast_hours") == list(DEFAULT_FORECAST_HOURS)
        and len(files) == len(DEFAULT_FORECAST_HOURS)
    )


def _head_archive_object(client: httpx.Client, cycle: datetime, forecast_hour: int) -> RemoteObject:
    url = gfs_archive_object_url(cycle, forecast_hour, "1p00")
    response = client.head(url)
    response.raise_for_status()
    size = int(response.headers["Content-Length"])
    if size <= 0:
        raise ValueError(f"NOAA returned an empty archive object: {url}")
    modified = response.headers.get("Last-Modified")
    return RemoteObject(
        url=url,
        filename=gfs_filename(cycle, forecast_hour, "1p00"),
        size_bytes=size,
        size_is_exact=True,
        last_modified=(parsedate_to_datetime(modified).astimezone(UTC) if modified else None),
        etag=response.headers.get("ETag"),
    )


def _download_gfs_object(
    root: Path,
    settings: GfsIngestionSettings,
    cycle: datetime,
    forecast_hour: int,
    remote: RemoteObject,
) -> dict[str, object]:
    relative = object_relative_path(settings, cycle, forecast_hour)
    with StreamingDownloader(
        root,
        allowed_hosts=frozenset({GFS_ARCHIVE_HOST}),
        minimum_free_bytes=settings.minimum_free_bytes,
        maximum_download_bytes=settings.maximum_download_bytes,
        timeout_seconds=settings.timeout_seconds,
        user_agent="weather-platform-gfs-history/1.0",
    ) as downloader:
        downloaded = downloader.download(remote, relative)
    validation = validate_gfs_file(
        downloaded.path,
        cycle=cycle,
        forecast_hour=forecast_hour,
        settings=settings,
    )
    return {
        "initialization_time": cycle.isoformat().replace("+00:00", "Z"),
        "valid_time": (cycle + timedelta(hours=forecast_hour)).isoformat().replace("+00:00", "Z"),
        "forecast_hour": forecast_hour,
        "filename": remote.filename,
        "relative_path": relative.as_posix(),
        "size_bytes": downloaded.size_bytes,
        "sha256": downloaded.sha256,
        "reused_existing": downloaded.reused_existing,
        "source_url": remote.url,
        **validation,
    }


def download_gfs(root: Path, start: date, end: date, workers: int) -> dict[str, Any]:
    settings = GfsIngestionSettings(
        forecast_hours=DEFAULT_FORECAST_HOURS,
        minimum_free_bytes=50 * 1024**3,
        maximum_download_bytes=2 * 1024**3,
        timeout_seconds=600,
    )
    completed = 0
    reused = 0
    downloaded_bytes = 0
    cycles = [datetime.combine(day, time(), tzinfo=UTC) for day in _dates(start, end)]
    with httpx.Client(
        timeout=httpx.Timeout(60, connect=15),
        follow_redirects=True,
        headers={"User-Agent": "weather-platform-gfs-history/1.0"},
    ) as client:
        for cycle in cycles:
            if _complete_gfs_manifest(root, cycle):
                completed += 1
                reused += len(DEFAULT_FORECAST_HOURS)
                print(f"GFS {cycle:%Y-%m-%d %HZ}: already complete", flush=True)
                continue
            remotes = {
                hour: _head_archive_object(client, cycle, hour) for hour in DEFAULT_FORECAST_HOURS
            }

            def download_hour(
                hour: int,
                *,
                current_cycle: datetime = cycle,
                current_remotes: dict[int, RemoteObject] = remotes,
            ) -> dict[str, object]:
                return _download_gfs_object(
                    root,
                    settings,
                    current_cycle,
                    hour,
                    current_remotes[hour],
                )

            with ThreadPoolExecutor(max_workers=workers) as executor:
                results = list(executor.map(download_hour, DEFAULT_FORECAST_HOURS))
            plan = {
                "status": "ready",
                "source": GFS_ARCHIVE_BASE_URL,
                "settings": settings.as_dict(),
                "cycles": [cycle.isoformat().replace("+00:00", "Z")],
                "requests": [],
            }
            write_cycle_manifests(plan, results, root)
            completed += 1
            reused += sum(bool(item["reused_existing"]) for item in results)
            downloaded_bytes += sum(
                int(item["size_bytes"]) for item in results if not item["reused_existing"]
            )
            print(
                f"GFS {cycle:%Y-%m-%d %HZ}: 9 files complete "
                f"({sum(int(item['size_bytes']) for item in results) / 1024**2:.1f} MiB)",
                flush=True,
            )
    return {
        "cycle_count": completed,
        "file_count": completed * len(DEFAULT_FORECAST_HOURS),
        "reused_file_count": reused,
        "downloaded_bytes": downloaded_bytes,
        "first_cycle": cycles[0].isoformat().replace("+00:00", "Z"),
        "last_cycle": cycles[-1].isoformat().replace("+00:00", "Z"),
        "forecast_hours": list(DEFAULT_FORECAST_HOURS),
        "source": GFS_ARCHIVE_BASE_URL,
    }


def download_cffdrs(root: Path, start: date, end: date) -> dict[str, Any]:
    settings = CwfisCffdrsSettings(
        minimum_free_bytes=10 * 1024**3,
        maximum_grid_bytes=128 * 1024**2,
        timeout_seconds=600,
    )
    statuses: Counter[str] = Counter()
    unavailable_dates: list[str] = []
    total_bytes = 0
    for day in _dates(start, end):
        try:
            result = ingest_date(root, day, settings)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in {404, 500}:
                raise
            statuses["source_unavailable"] += 1
            unavailable_dates.append(day.isoformat())
            print(
                f"CFFDRS {day}: source_unavailable (HTTP {exc.response.status_code})",
                flush=True,
            )
            continue
        statuses[str(result["status"])] += 1
        total_bytes += sum(int(grid["size_bytes"]) for grid in result["grids"].values())
        print(f"CFFDRS {day}: {result['status']}", flush=True)
    return {
        "date_count": (end - start).days + 1,
        "first_date": start.isoformat(),
        "last_date": end.isoformat(),
        "statuses": dict(sorted(statuses.items())),
        "unavailable_dates": unavailable_dates,
        "total_bytes": total_bytes,
    }


def select_hotspots(root: Path, start: date, end: date) -> dict[str, Any]:
    archive = root / "raw/nrcan/cwfis/firem3/archive/2025_hotspots.zip"
    if not archive.is_file():
        raise FileNotFoundError(f"missing CWFIS hotspot archive: {archive}")
    selection_dir = root / "raw/nrcan/cwfis/firem3/archive/selections"
    output = selection_dir / f"{start}_{end}.csv"
    temporary = output.with_name(output.name + ".part")
    selection_dir.mkdir(parents=True, exist_ok=True)
    temporary.unlink(missing_ok=True)
    rows = 0
    countries: Counter[str] = Counter()
    sensors: Counter[str] = Counter()
    dates: Counter[str] = Counter()
    with zipfile.ZipFile(archive) as zipped, zipped.open("2025_hotspots.csv") as raw:
        reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
        if reader.fieldnames is None:
            raise ValueError("CWFIS hotspot archive has no CSV header")
        with temporary.open("w", newline="", encoding="utf-8") as target:
            writer = csv.DictWriter(target, fieldnames=reader.fieldnames)
            writer.writeheader()
            for row in reader:
                observed = date.fromisoformat(row["rep_date"][:10])
                if not start <= observed <= end:
                    continue
                writer.writerow(row)
                rows += 1
                dates[observed.isoformat()] += 1
                countries[row["country"]] += 1
                sensors[row["sensor"]] += 1
            target.flush()
            os.fsync(target.fileno())
    os.replace(temporary, output)
    result = {
        "archive_relative_path": archive.relative_to(root).as_posix(),
        "archive_sha256": _sha256(archive),
        "selection_relative_path": output.relative_to(root).as_posix(),
        "selection_sha256": _sha256(output),
        "selection_size_bytes": output.stat().st_size,
        "row_count": rows,
        "date_counts": dict(sorted(dates.items())),
        "country_counts": dict(sorted(countries.items())),
        "sensor_counts": dict(sorted(sensors.items())),
        "source": HOTSPOT_ARCHIVE_URL,
    }
    _atomic_json(output.with_suffix(".manifest.json"), result)
    return result


def ingest_gfas(root: Path, source: Path, start: date, end: date) -> dict[str, Any]:
    source = source.expanduser().resolve()
    if not source.is_file() or source.is_symlink():
        raise FileNotFoundError(f"GFAS source is not a regular file: {source}")
    output = subprocess.run(
        [
            "grib_get",
            "-p",
            (
                "edition,centre,gridType,Ni,Nj,typeOfLevel,level,dataDate,dataTime,"
                "stepRange,shortName,paramId,units"
            ),
            source.as_posix(),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
    ).stdout
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(output.splitlines(), start=1):
        fields = line.split(maxsplit=12)
        if len(fields) != 13:
            raise ValueError(f"invalid GFAS GRIB metadata on message {number}")
        rows.append(
            {
                "edition": int(fields[0]),
                "centre": fields[1],
                "grid_type": fields[2],
                "ni": int(fields[3]),
                "nj": int(fields[4]),
                "level_type": fields[5],
                "level": int(fields[6]),
                "date": datetime.strptime(fields[7], "%Y%m%d").date(),
                "time": int(fields[8]),
                "step": fields[9],
                "short_name": fields[10],
                "parameter_id": int(fields[11]),
                "units": fields[12],
            }
        )
    expected_dates = _dates(start, end)
    messages_by_date: dict[date, list[dict[str, Any]]] = {day: [] for day in expected_dates}
    for row in rows:
        if row["date"] not in messages_by_date:
            raise ValueError(f"GFAS message lies outside experiment dates: {row['date']}")
        messages_by_date[row["date"]].append(row)
        identity = (
            row["edition"],
            row["centre"],
            row["grid_type"],
            row["ni"],
            row["nj"],
            row["level_type"],
            row["level"],
            row["time"],
            row["step"],
        )
        if identity != (1, "ecmf", "regular_ll", 3600, 1800, "surface", 0, 0, "0-24"):
            raise ValueError(f"unexpected GFAS message identity: {identity}")
    parameter_sets = [
        {str(row["short_name"]) for row in messages_by_date[day]} for day in expected_dates
    ]
    if any(not values for values in parameter_sets) or any(
        values != parameter_sets[0] for values in parameter_sets[1:]
    ):
        raise ValueError("GFAS dates do not contain an identical parameter inventory")
    missing = sorted(GFAS_REQUIRED_PARAMETERS - parameter_sets[0])
    if missing:
        raise ValueError(f"GFAS file lacks required parameters: {missing}")
    variables: dict[str, dict[str, Any]] = {}
    for row in rows:
        short_name = str(row["short_name"])
        definition = {
            "parameter_id": int(row["parameter_id"]),
            "units": str(row["units"]),
        }
        if short_name in variables and variables[short_name] != definition:
            raise ValueError(f"inconsistent GFAS definition for {short_name}")
        variables[short_name] = definition

    statistics_output = subprocess.run(
        [
            "grib_get",
            "-p",
            "shortName,numberOfDataPoints,numberOfMissing,minimum,maximum,average",
            source.as_posix(),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=900,
    ).stdout
    value_statistics: dict[str, dict[str, float | int]] = {}
    for line in statistics_output.splitlines():
        fields = line.split()
        if len(fields) != 6 or fields[0] not in GFAS_REQUIRED_PARAMETERS:
            continue
        short_name = fields[0]
        points, missing_values = int(fields[1]), int(fields[2])
        minimum, maximum, average = map(float, fields[3:])
        if not all(math.isfinite(value) for value in (minimum, maximum, average)):
            raise ValueError(f"non-finite GFAS statistics for {short_name}")
        if minimum < 0 or maximum < minimum:
            raise ValueError(f"invalid GFAS range for {short_name}")
        aggregate = value_statistics.setdefault(
            short_name,
            {
                "message_count": 0,
                "point_count": 0,
                "missing_value_count": 0,
                "minimum": minimum,
                "maximum": maximum,
                "sum_of_message_means": 0.0,
            },
        )
        aggregate["message_count"] += 1
        aggregate["point_count"] += points
        aggregate["missing_value_count"] += missing_values
        aggregate["minimum"] = min(float(aggregate["minimum"]), minimum)
        aggregate["maximum"] = max(float(aggregate["maximum"]), maximum)
        aggregate["sum_of_message_means"] += average
    for short_name in GFAS_REQUIRED_PARAMETERS:
        aggregate = value_statistics.get(short_name)
        if aggregate is None or aggregate["message_count"] != len(expected_dates):
            raise ValueError(f"incomplete GFAS value statistics for {short_name}")
        if aggregate["missing_value_count"] != 0:
            raise ValueError(f"GFAS contains missing values for {short_name}")
        aggregate["mean_of_daily_means"] = float(aggregate.pop("sum_of_message_means")) / int(
            aggregate["message_count"]
        )

    archive_directory = root / "raw/ecmwf/cams/gfas/v1.2/2025" / f"{start}_{end}"
    destination = archive_directory / f"cams-gfas-v1.2-daily-{start}_{end}.grib"
    archive_directory.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    temporary.unlink(missing_ok=True)
    if destination.exists():
        source_sha256 = _sha256(source)
        if _sha256(destination) != source_sha256:
            raise FileExistsError(f"different GFAS archive already exists: {destination}")
        reused = True
    else:
        digest = hashlib.sha256()
        with source.open("rb") as input_file, temporary.open("xb") as output_file:
            for block in iter(lambda: input_file.read(8 * 1024 * 1024), b""):
                digest.update(block)
                output_file.write(block)
            output_file.flush()
            os.fsync(output_file.fileno())
        source_sha256 = digest.hexdigest()
        os.replace(temporary, destination)
        reused = False
    if destination.stat().st_size != source.stat().st_size:
        raise ValueError("archived GFAS size differs from the downloaded source")
    if _sha256(destination) != source_sha256:
        raise ValueError("archived GFAS checksum differs from the downloaded source")

    payload = {
        "schema_version": 1,
        "provider": "ecmwf",
        "product": "cams_gfas",
        "version": "1.2",
        "data_type": "analysis",
        "temporal_resolution": "daily_24_hour_average",
        "data_start": start.isoformat(),
        "data_end_inclusive": end.isoformat(),
        "message_count": len(rows),
        "messages_per_date": len(messages_by_date[expected_dates[0]]),
        "grid": {
            "type": "regular_ll",
            "dimensions": [3600, 1800],
            "resolution_degrees": 0.1,
            "level_type": "surface",
        },
        "variables": dict(sorted(variables.items())),
        "value_statistics": dict(sorted(value_statistics.items())),
        "required_parameters": sorted(GFAS_REQUIRED_PARAMETERS),
        "source": GFAS_DATASET_URL,
        "source_download_filename": source.name,
        "collected_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "file": {
            "relative_path": destination.relative_to(root).as_posix(),
            "size_bytes": destination.stat().st_size,
            "sha256": source_sha256,
        },
    }
    manifest_path = archive_directory / "manifest.json"
    _atomic_json(manifest_path, payload)
    return {
        "status": "already_complete" if reused else "complete",
        "manifest": manifest_path.relative_to(root).as_posix(),
        **payload,
    }


def build_experiment_manifest(root: Path, start: date, end: date, spinup_start: date) -> Path:
    identifier = f"gfas-v1.2-{start}_{end}"
    destination = root / "derived/smoke/validation/input-archives" / identifier / "manifest.json"
    hotspot_manifest = (
        root / "raw/nrcan/cwfis/firem3/archive/selections" / f"{spinup_start}_{end}.manifest.json"
    )
    if not hotspot_manifest.is_file():
        raise FileNotFoundError("hotspot selection manifest has not been created")
    gfs_manifests = [
        root
        / cycle_relative_directory(
            GfsIngestionSettings(), datetime.combine(day, time(), tzinfo=UTC)
        )
        / "manifest.json"
        for day in _dates(spinup_start, end)
    ]
    cffdrs_manifests = [
        root / f"raw/nrcan/cwfis/cffdrs/{day:%Y/%m/%d}/manifest.json"
        for day in _dates(spinup_start, end)
    ]
    missing = [path.as_posix() for path in gfs_manifests + cffdrs_manifests if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"experiment inputs remain incomplete: {missing[:5]}")
    perimeter = root / "raw/nrcan/cwfis/perimeters/archive/2025_perimeters.zip"
    gfas_manifest_path = root / "raw/ecmwf/cams/gfas/v1.2/2025" / f"{start}_{end}" / "manifest.json"
    naps_files = [
        root / "raw/eccc/naps/program-information/StationsNAPS-StationsSNPA.csv",
        root / "raw/eccc/naps/program-information/NAPS-SNPA_Modification.txt",
        root
        / ("raw/eccc/naps/2025/integrated/2025_NAPSReferenceMethodePM2_5MethodeReferenceSNPA.zip"),
    ]
    payload = {
        "schema_version": 1,
        "experiment_id": identifier,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "experiment_start": start.isoformat(),
        "experiment_end_inclusive": end.isoformat(),
        "meteorology_start": spinup_start.isoformat(),
        "meteorology_policy": "daily 00Z GFS cycle, f000..f024 every three hours",
        "gfs": {
            "manifest_count": len(gfs_manifests),
            "manifests": [
                {"relative_path": path.relative_to(root).as_posix(), "sha256": _sha256(path)}
                for path in gfs_manifests
            ],
        },
        "cffdrs": {
            "manifest_count": len(cffdrs_manifests),
            "manifests": [
                {"relative_path": path.relative_to(root).as_posix(), "sha256": _sha256(path)}
                for path in cffdrs_manifests
            ],
        },
        "hotspots": json.loads(hotspot_manifest.read_text(encoding="utf-8")),
        "perimeters": (
            {
                "relative_path": perimeter.relative_to(root).as_posix(),
                "sha256": _sha256(perimeter),
                "source": PERIMETER_ARCHIVE_URL,
            }
            if perimeter.is_file()
            else None
        ),
        "naps": {
            "verified_hourly_2025_status": "not_yet_published_by_eccc",
            "integrated_reference_method_use": (
                "supplementary 24-hour PM2.5 diagnostic; not a substitute for hourly NAPS"
            ),
            "files": [
                {
                    "relative_path": path.relative_to(root).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
                for path in naps_files
                if path.is_file()
            ],
        },
        "gfas": (
            {
                "manifest_relative_path": gfas_manifest_path.relative_to(root).as_posix(),
                "manifest_sha256": _sha256(gfas_manifest_path),
                **json.loads(gfas_manifest_path.read_text(encoding="utf-8")),
            }
            if gfas_manifest_path.is_file()
            else None
        ),
        "external_inputs": (
            {}
            if gfas_manifest_path.is_file()
            else {
                "gfas_v1_2": (
                    "download in progress outside this script; add its files and hashes "
                    "before evaluation"
                )
            }
        ),
        "limitations": [
            "The annual CWFIS hotspot archive has no estarea field; do not infer one silently.",
            (
                "Use observed perimeters or a preregistered area method before calculating "
                "CFFEPS mass."
            ),
            "GFAS v1.2 is daily, so aggregate model emissions to the identical daily interval.",
        ],
    }
    _atomic_json(destination, payload)
    return destination


def verify_experiment_manifest(root: Path, start: date, end: date) -> Path:
    identifier = f"gfas-v1.2-{start}_{end}"
    directory = root / "derived/smoke/validation/input-archives" / identifier
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    gfs_files = 0
    gfs_bytes = 0
    for record in manifest["gfs"]["manifests"]:
        path = root / record["relative_path"]
        if _sha256(path) != record["sha256"]:
            raise ValueError(f"GFS manifest checksum mismatch: {path}")
        payload, files = resolve_complete_cycle(path)
        if payload["source"] != GFS_ARCHIVE_BASE_URL:
            raise ValueError(f"unexpected historical GFS source: {path}")
        gfs_files += len(files)
        gfs_bytes += sum(file.stat().st_size for file in files)

    cffdrs_files = 0
    cffdrs_bytes = 0
    for record in manifest["cffdrs"]["manifests"]:
        path = root / record["relative_path"]
        if _sha256(path) != record["sha256"]:
            raise ValueError(f"CFFDRS manifest checksum mismatch: {path}")
        day = date.fromisoformat(json.loads(path.read_text(encoding="utf-8"))["data_date"])
        payload = load_complete_manifest(root, day)
        if payload is None:
            raise ValueError(f"incomplete CFFDRS archive: {day}")
        cffdrs_files += len(payload["grids"])
        cffdrs_bytes += sum(int(grid["size_bytes"]) for grid in payload["grids"].values())

    ancillary_files = 0
    ancillary_bytes = 0
    records = [
        {
            "relative_path": manifest["hotspots"]["archive_relative_path"],
            "sha256": manifest["hotspots"]["archive_sha256"],
        },
        {
            "relative_path": manifest["hotspots"]["selection_relative_path"],
            "sha256": manifest["hotspots"]["selection_sha256"],
        },
        manifest.get("perimeters"),
        *manifest["naps"]["files"],
    ]
    for record in records:
        if record is None:
            continue
        path = root / record["relative_path"]
        if _sha256(path) != record["sha256"]:
            raise ValueError(f"ancillary checksum mismatch: {path}")
        ancillary_files += 1
        ancillary_bytes += path.stat().st_size

    gfas = manifest.get("gfas")
    if not isinstance(gfas, dict):
        gfas_report = None
        remaining_input = "GFAS v1.2 file"
    else:
        gfas_manifest = root / gfas["manifest_relative_path"]
        if _sha256(gfas_manifest) != gfas["manifest_sha256"]:
            raise ValueError("GFAS manifest checksum mismatch")
        gfas_file = root / gfas["file"]["relative_path"]
        if (
            not gfas_file.is_file()
            or gfas_file.stat().st_size != gfas["file"]["size_bytes"]
            or _sha256(gfas_file) != gfas["file"]["sha256"]
        ):
            raise ValueError("GFAS archive checksum or size mismatch")
        gfas_report = {
            "message_count": gfas["message_count"],
            "variable_count": len(gfas["variables"]),
            "bytes": gfas_file.stat().st_size,
            "sha256": gfas["file"]["sha256"],
        }
        remaining_input = None

    report = {
        "schema_version": 1,
        "status": "complete",
        "verified_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "experiment_manifest_relative_path": manifest_path.relative_to(root).as_posix(),
        "experiment_manifest_sha256": _sha256(manifest_path),
        "coverage": {
            "experiment_start": manifest["experiment_start"],
            "experiment_end_inclusive": manifest["experiment_end_inclusive"],
            "meteorology_start": manifest["meteorology_start"],
        },
        "gfs": {
            "manifest_count": len(manifest["gfs"]["manifests"]),
            "file_count": gfs_files,
            "bytes": gfs_bytes,
        },
        "cffdrs": {
            "manifest_count": len(manifest["cffdrs"]["manifests"]),
            "file_count": cffdrs_files,
            "bytes": cffdrs_bytes,
        },
        "ancillary": {"file_count": ancillary_files, "bytes": ancillary_bytes},
        "gfas": gfas_report,
        "hotspot_rows": manifest["hotspots"]["row_count"],
        "hotspot_viirs_rows": manifest["hotspots"]["sensor_counts"]["VIIRS-I"],
        "remaining_required_input": remaining_input,
    }
    output = directory / "verification.json"
    _atomic_json(output, report)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--spinup-days", type=int, default=1)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--component",
        choices=("all", "gfs", "cffdrs", "hotspots", "gfas", "manifest", "verify"),
        default="all",
    )
    parser.add_argument("--gfas-source", type=Path)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(
            os.environ.get("WEATHER_DATA_ROOT", "/Volumes/BigMrStorage/weatherapp_data/weather")
        ),
    )
    args = parser.parse_args()
    if args.end < args.start or args.spinup_days < 0 or not 1 <= args.workers <= 8:
        parser.error("invalid date, spin-up, or worker bounds")
    root = args.data_root.expanduser().resolve()
    if shutil.disk_usage(root).free < 75 * 1024**3:
        raise OSError("at least 75 GiB of free space is required before backfill")
    spinup_start = args.start - timedelta(days=args.spinup_days)
    result: dict[str, Any] = {}
    if args.component in {"all", "gfs"}:
        result["gfs"] = download_gfs(root, spinup_start, args.end, args.workers)
    if args.component in {"all", "cffdrs"}:
        result["cffdrs"] = download_cffdrs(root, spinup_start, args.end)
    if args.component in {"all", "hotspots"}:
        result["hotspots"] = select_hotspots(root, spinup_start, args.end)
    if args.component == "gfas":
        if args.gfas_source is None:
            parser.error("--gfas-source is required for the GFAS component")
        result["gfas"] = ingest_gfas(root, args.gfas_source, args.start, args.end)
        result["manifest"] = build_experiment_manifest(
            root, args.start, args.end, spinup_start
        ).as_posix()
        result["verification"] = verify_experiment_manifest(root, args.start, args.end).as_posix()
    if args.component in {"all", "manifest"}:
        result["manifest"] = build_experiment_manifest(
            root, args.start, args.end, spinup_start
        ).as_posix()
    if args.component in {"all", "verify"}:
        result["verification"] = verify_experiment_manifest(root, args.start, args.end).as_posix()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
