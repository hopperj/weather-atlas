#!/usr/bin/env python3
"""Freeze an input-only MISR/MINX vertical-observation availability ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

MERLIN_QUERY = "https://l0dup05.larc.nasa.gov/merlin/merlin/query/"
SELECTION_SEED = "cffeps-flexpart-w1-merlin-canada-interior-overpasses-v1"
PLUME_NAME = re.compile(r"^(?P<orbit>O[0-9]{6})-B[0-9]{3}-SPW[BR][0-9]{2}$")

# Deliberately conservative Canadian-interior screening boxes. They exclude
# coastal/border ambiguity at the cost of omitting valid Canadian plumes.
CANADIAN_INTERIOR_BOXES = (
    {"name": "british_columbia_interior", "west": -128, "south": 49, "east": -114, "north": 60},
    {"name": "prairies", "west": -114, "south": 49, "east": -95, "north": 60},
    {"name": "central_east", "west": -95, "south": 45, "east": -57, "north": 57},
    {"name": "territories_interior", "west": -136, "south": 60, "east": -102, "north": 70},
)


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


def query_string(start: date, end: date) -> str:
    # Empty biome and region sets intentionally retrieve the complete provider
    # population within the provider's full, documented physical ranges.
    return f"eb,er,9000,1,50000,1,3,0,1,0,{start.isoformat()},{end.isoformat()}"


def interior_box(record: dict[str, Any]) -> str | None:
    longitude = float(record["p_src_long"])
    latitude = float(record["p_src_lat"])
    for box in CANADIAN_INTERIOR_BOXES:
        if box["west"] <= longitude <= box["east"] and box["south"] <= latitude <= box["north"]:
            return str(box["name"])
    return None


def rank(overpass_id: str) -> str:
    return hashlib.sha256(f"{SELECTION_SEED}|{overpass_id}".encode()).hexdigest()


def fetch_catalogue(
    client: httpx.Client,
    *,
    start: date,
    end: date,
) -> tuple[list[dict[str, Any]], str]:
    query = query_string(start, end)
    response = client.get(MERLIN_QUERY, params={"q": query})
    response.raise_for_status()
    records = response.json()
    if not isinstance(records, list):
        raise ValueError("MERLIN query did not return a JSON list")
    return records, query


def build_overpasses(
    records: list[dict[str, Any]],
    *,
    year: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    excluded = defaultdict(int)
    for record in records:
        box_name = interior_box(record)
        if box_name is None:
            excluded["outside_conservative_canadian_interior"] += 1
            continue
        match = PLUME_NAME.fullmatch(str(record.get("p_name", "")))
        if match is None:
            excluded["unrecognized_plume_name"] += 1
            continue
        if not str(record.get("p_url", "")).startswith(
            "https://asdc.larc.nasa.gov/documents/misr/plume/"
        ):
            excluded["untrusted_or_missing_plume_url"] += 1
            continue
        if int(record.get("p_num_hts", 0)) <= 0:
            excluded["no_height_retrievals"] += 1
            continue
        copied = dict(record)
        copied["canadian_interior_box"] = box_name
        copied["provider_record_sha256"] = hashlib.sha256(
            json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        grouped[match.group("orbit")].append(copied)

    overpasses = []
    for orbit, plumes in grouped.items():
        timestamps = sorted({str(item["p_date"]) for item in plumes})
        overpass_id = f"{year}-{orbit}"
        overpasses.append(
            {
                "overpass_id": overpass_id,
                "year": year,
                "orbit": orbit,
                "acquisition_times": timestamps,
                "plume_count": len(plumes),
                "retrieval_point_count": sum(int(item["p_num_hts"]) for item in plumes),
                "biome_ids": sorted({int(item["p_biome_id"]) for item in plumes}),
                "interior_boxes": sorted({str(item["canadian_interior_box"]) for item in plumes}),
                "plumes": sorted(plumes, key=lambda item: str(item["p_name"])),
                "selection_rank": rank(overpass_id),
            }
        )
    return sorted(overpasses, key=lambda item: str(item["selection_rank"])), dict(excluded)


def download_plume(
    client: httpx.Client,
    *,
    url: str,
    destination: Path,
) -> dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "asdc.larc.nasa.gov":
        raise ValueError(f"plume URL is outside the frozen ASDC host: {url}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.is_file() or destination.stat().st_size == 0:
        temporary = destination.with_name(destination.name + ".part")
        temporary.unlink(missing_ok=True)
        try:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                if "text/html" in response.headers.get("content-type", "").lower():
                    raise ValueError(f"ASDC returned HTML for plume file: {url}")
                with temporary.open("xb") as output:
                    for block in response.iter_bytes(1024 * 1024):
                        output.write(block)
                    output.flush()
                    os.fsync(output.fileno())
            if temporary.stat().st_size < 100:
                raise ValueError(f"ASDC plume file is unexpectedly small: {url}")
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    text = destination.read_text(encoding="utf-8", errors="strict")
    if "Smoke" not in text and "Plume" not in text and "plume" not in text:
        raise ValueError(f"ASDC plume file lacks a recognizable MINX header: {url}")
    return {
        "path": destination.as_posix(),
        "size_bytes": destination.stat().st_size,
        "sha256": sha256(destination),
        "source_url": url,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--per-year", type=int, default=8)
    parser.add_argument(
        "--start-date",
        type=date.fromisoformat,
        help="First provider acquisition date (inclusive).",
    )
    parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        help="Last provider acquisition date (inclusive).",
    )
    parser.add_argument(
        "--all-overpasses",
        action="store_true",
        help="Retain every Canadian-interior overpass instead of a seeded per-year sample.",
    )
    parser.add_argument("--download-workers", type=int, default=8)
    parser.add_argument("--ledger-name", default="vertical-ledger.json")
    args = parser.parse_args()
    if args.per_year < 5:
        parser.error("--per-year must be at least 5")
    if (args.start_date is None) != (args.end_date is None):
        parser.error("--start-date and --end-date must be supplied together")
    if args.start_date is not None and args.start_date > args.end_date:
        parser.error("--start-date must not be later than --end-date")
    if args.download_workers < 1:
        parser.error("--download-workers must be at least 1")
    if Path(args.ledger_name).name != args.ledger_name:
        parser.error("--ledger-name must be a filename, not a path")

    output_directory = args.output_directory.resolve()
    raw_directory = (
        args.data_root.resolve()
        / "raw"
        / "nasa"
        / "asdc"
        / "misr"
        / "merlin"
        / "plume-height-project-2"
    )
    all_selected: list[dict[str, Any]] = []
    catalogue_files = []
    availability = []
    if args.start_date is None:
        query_periods = [(date(year, 6, 1), date(year, 8, 31)) for year in (2017, 2018)]
    else:
        query_periods = []
        for year in range(args.start_date.year, args.end_date.year + 1):
            query_periods.append(
                (
                    max(args.start_date, date(year, 1, 1)),
                    min(args.end_date, date(year, 12, 31)),
                )
            )
    with httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(180, connect=30),
        headers={"User-Agent": "weather-platform-misr-merlin-validation/1.0"},
    ) as client:
        for start, end in query_periods:
            year = start.year
            provider_records, query = fetch_catalogue(client, start=start, end=end)
            period_label = (
                "summer"
                if start == date(year, 6, 1) and end == date(year, 8, 31)
                else f"{start.isoformat()}_{end.isoformat()}"
            )
            catalogue_path = raw_directory / f"merlin-{year}-{period_label}-catalogue.json"
            atomic_json(
                catalogue_path,
                {
                    "artifact_type": "nasa-misr-merlin-provider-catalogue",
                    "schema_version": 1,
                    "retrieved_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    "endpoint": MERLIN_QUERY,
                    "query": query,
                    "record_count": len(provider_records),
                    "records": provider_records,
                },
            )
            overpasses, exclusions = build_overpasses(provider_records, year=year)
            selected = overpasses if args.all_overpasses else overpasses[: args.per_year]
            if not args.all_overpasses and len(selected) < args.per_year:
                raise ValueError(
                    f"only {len(selected)} eligible {year} overpasses; {args.per_year} required"
                )
            all_selected.extend(selected)
            catalogue_files.append(
                {
                    "year": year,
                    "path": catalogue_path.as_posix(),
                    "size_bytes": catalogue_path.stat().st_size,
                    "sha256": sha256(catalogue_path),
                }
            )
            availability.append(
                {
                    "year": year,
                    "query_start": start.isoformat(),
                    "query_end": end.isoformat(),
                    "provider_record_count": len(provider_records),
                    "eligible_overpass_count": len(overpasses),
                    "selected_overpass_count": len(selected),
                    "exclusion_counts": exclusions,
                }
            )

        for selected in all_selected:
            orbit_directory = raw_directory / str(selected["year"]) / str(selected["orbit"])

            def fetch(
                plume: dict[str, Any],
                directory: Path = orbit_directory,
            ) -> dict[str, Any]:
                filename = Path(urlparse(str(plume["p_url"])).path).name
                destination = directory / filename
                return download_plume(
                    client,
                    url=str(plume["p_url"]),
                    destination=destination,
                )

            with ThreadPoolExecutor(max_workers=args.download_workers) as pool:
                selected["files"] = list(pool.map(fetch, selected["plumes"]))

    ledger = {
        "artifact_type": "w1-input-only-misr-merlin-vertical-ledger",
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "frozen_prospective_observation_availability",
        "selection_seed": SELECTION_SEED,
        "selection_rules": {
            "query_periods": [
                {"start": start.isoformat(), "end": end.isoformat()} for start, end in query_periods
            ],
            "overpass_selection": (
                "all eligible Canadian-interior overpasses"
                if args.all_overpasses
                else f"first {args.per_year} by deterministic seeded rank per year"
            ),
            "overpasses_per_year": None if args.all_overpasses else args.per_year,
            "independence_unit": "unique MISR orbit",
            "height_magnitude_used_for_selection": False,
            "model_output_or_performance_used_for_selection": False,
            "minimum_provider_height_retrievals_per_plume": 1,
            "geography": {
                "method": "conservative_canadian_interior_rectangles",
                "boxes": CANADIAN_INTERIOR_BOXES,
                "limitation": (
                    "This is an availability screen, not a national boundary. "
                    "W3 must match each overpass to an input-qualified fire event."
                ),
            },
        },
        "catalogues": catalogue_files,
        "availability": availability,
        "overpass_count": len(all_selected),
        "overpasses": all_selected,
        "selection_firewall": {
            "flexpart_output_accessed": False,
            "predicted_observed_residual_accessed": False,
            "observed_height_used_for_ranking": False,
        },
    }
    ledger_path = output_directory / args.ledger_name
    atomic_json(ledger_path, ledger)
    freeze = {
        "ledger": {
            "path": ledger_path.as_posix(),
            "size_bytes": ledger_path.stat().st_size,
            "sha256": sha256(ledger_path),
        },
        "overpass_count": len(all_selected),
        "downloaded_plume_file_count": sum(len(item["files"]) for item in all_selected),
    }
    atomic_json(output_directory / f"{ledger_path.stem}.freeze.json", freeze)
    print(json.dumps(freeze, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
