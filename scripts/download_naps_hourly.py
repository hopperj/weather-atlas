#!/usr/bin/env python3
"""Download and freeze one final ECCC NAPS hourly pollutant archive."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

CATALOGUE_API = "https://data-donnees.az.ec.gc.ca/api"
CATALOGUE_ROOT = (
    "/air/monitor/national-air-pollution-surveillance-naps-program/"
    "Data-Donnees"
)
POLLUTANTS = frozenset({"CO", "NO", "NO2", "NOX", "O3", "PM10", "PM25", "SO2"})


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


def provider_directory(year: int) -> str:
    return (
        f"{CATALOGUE_ROOT}/{year}/ContinuousData-DonneesContinu/"
        "HourlyData-DonneesHoraires"
    )


def discover(client: httpx.Client, year: int, pollutant: str) -> dict[str, Any]:
    directory = provider_directory(year)
    response = client.get(f"{CATALOGUE_API}/path_contents", params={"path": directory})
    response.raise_for_status()
    payload = response.json()
    expected = f"{pollutant}_{year}.csv"
    matches = [
        item
        for item in payload.get("path_contents", [])
        if item.get("name") == expected and not item.get("is_directory")
    ]
    if len(matches) != 1:
        raise FileNotFoundError(
            f"ECCC catalogue returned {len(matches)} matches for {expected}"
        )
    return matches[0]


def download(client: httpx.Client, provider_path: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        with client.stream(
            "GET",
            f"{CATALOGUE_API}/file",
            params={"path": f"/{provider_path.lstrip('/')}"},
        ) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" in content_type:
                raise ValueError("ECCC file endpoint returned HTML")
            with temporary.open("xb") as output:
                for block in response.iter_bytes(1024 * 1024):
                    output.write(block)
                output.flush()
                os.fsync(output.fileno())
        if temporary.stat().st_size == 0:
            raise ValueError("ECCC file endpoint returned an empty file")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def validate(path: Path, *, year: int, pollutant: str) -> dict[str, Any]:
    raw = path.read_bytes()
    if b"\x00" in raw:
        raise ValueError("NAPS CSV contains a NUL byte")
    text = raw.decode("utf-8-sig")
    lines = text.splitlines()
    if not lines or "File generated on" not in lines[0]:
        raise ValueError("NAPS CSV lacks its provider generation record")
    if f"Pollutant // Polluant:, {pollutant.replace('PM25', 'PM2.5')}" not in text[:1000]:
        raise ValueError("NAPS CSV pollutant metadata does not match the request")
    if "hour ending local standard time" not in text[:2000]:
        raise ValueError("NAPS CSV lacks its local-standard-time contract")
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if line.startswith("Pollutant//Polluant,Method Code//Code Méthode")
        ),
        None,
    )
    if header_index is None:
        raise ValueError("NAPS CSV data header was not found")
    reader = csv.DictReader(io.StringIO("\n".join(lines[header_index:])))
    required = {
        "Pollutant//Polluant",
        "Method Code//Code Méthode",
        "NAPS ID//Identifiant SNPA",
        "Latitude//Latitude",
        "Longitude//Longitude",
        "Date//Date",
        *(f"H{hour:02d}//H{hour:02d}" for hour in range(1, 25)),
    }
    missing = required.difference(reader.fieldnames or ())
    if missing:
        raise ValueError(f"NAPS CSV lacks required columns: {sorted(missing)}")
    stations: set[str] = set()
    methods: set[str] = set()
    dates: set[str] = set()
    rows = 0
    valid_hour_values = 0
    missing_hour_values = 0
    for row in reader:
        rows += 1
        station = row["NAPS ID//Identifiant SNPA"].strip()
        if not station:
            raise ValueError(f"NAPS row {rows} lacks station identity")
        stations.add(station)
        methods.add(row["Method Code//Code Méthode"].strip())
        date_value = row["Date//Date"].strip()
        dates.add(date_value)
        if not date_value.startswith(str(year)):
            raise ValueError(f"NAPS row {rows} is outside requested year {year}")
        for hour in range(1, 25):
            value = row[f"H{hour:02d}//H{hour:02d}"].strip()
            if value == "-999" or value == "":
                missing_hour_values += 1
            else:
                float(value)
                valid_hour_values += 1
    if rows == 0 or valid_hour_values == 0:
        raise ValueError("NAPS CSV contains no usable observation values")
    return {
        "provider_generated_record": lines[0].lstrip("\ufeff"),
        "time_basis": "hour_ending_local_standard_time",
        "missing_value": -999,
        "row_count": rows,
        "station_count": len(stations),
        "method_codes": sorted(methods),
        "date_count": len(dates),
        "first_date": min(dates),
        "last_date": max(dates),
        "valid_hour_value_count": valid_hour_values,
        "missing_hour_value_count": missing_hour_values,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--pollutant", choices=sorted(POLLUTANTS), default="PM25")
    args = parser.parse_args()

    destination = (
        args.data_root
        / "raw"
        / "eccc"
        / "naps"
        / str(args.year)
        / "continuous"
        / "hourly"
        / f"{args.pollutant}_{args.year}.csv"
    )
    with httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(300, connect=30),
        headers={"User-Agent": "weather-platform-naps-history/1.0"},
    ) as client:
        discovered = discover(client, args.year, args.pollutant)
        if not destination.is_file() or destination.stat().st_size == 0:
            download(client, str(discovered["path"]), destination)
    validation = validate(
        destination,
        year=args.year,
        pollutant=args.pollutant,
    )
    manifest = {
        "artifact_type": "eccc-naps-final-hourly-archive",
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source": {
            "catalogue_api": CATALOGUE_API,
            "catalogue_directory": provider_directory(args.year),
            "provider_path": discovered["path"],
            "provider_last_modified": discovered.get("last_modified"),
            "provider_display_size": discovered.get("content_length"),
        },
        "request": {"year": args.year, "pollutant": args.pollutant},
        "file": {
            "path": destination.as_posix(),
            "size_bytes": destination.stat().st_size,
            "sha256": sha256(destination),
        },
        "validation": validation,
        "scientific_contract": {
            "archive_status": "final_provider_archive",
            "provider_time_basis": "hour_ending_local_standard_time",
            "utc_conversion_requires_station_standard_timezone": True,
            "selection_use": "observation_availability_only_before_cohort_freeze",
            "performance_values_accessed": False,
        },
    }
    manifest_path = destination.with_suffix(".manifest.json")
    atomic_json(manifest_path, manifest)
    print(
        json.dumps(
            {
                "file": manifest["file"],
                "manifest": manifest_path.as_posix(),
                "validation": validation,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
