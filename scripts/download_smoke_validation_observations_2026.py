#!/usr/bin/env python3
"""Download public observation inputs for the 2026 FLEXPART smoke validation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from weather_ingest.cwfis_hotspots import (
    CwfisHotspotSettings,
    ingest_request,
    publish_latest,
    raw_relative_path,
    remote_object_from_head,
)

AIRNOW_BASE = "https://files.airnowtech.org/airnow"
AQS_BASE = "https://aqs.epa.gov/aqsweb/airdata"
CMR_GRANULES = "https://cmr.earthdata.nasa.gov/search/granules.json"
CDSE_PRODUCTS = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
EARTHCARE_STAC = (
    "https://catalog.maap.eo.esa.int/catalogue/collections/EarthCAREL2Validated_MAAP/items"
)
MPLNET_SITES = "https://mplnet.gsfc.nasa.gov/operations/sites"
TROPOMI_OPEN_DATA_BASE = "https://meeo-s5p.s3.eu-central-1.amazonaws.com"
CANADA_BBOX = (-141.0, 41.0, -52.0, 84.0)
AIRNOW_COLUMNS = frozenset(
    {
        "AQSID",
        "Latitude",
        "Longitude",
        "CountryCode",
        "ValidDate",
        "ValidTime",
        "PM25_Measured",
        "PM25",
        "PM25_Unit",
    }
)


def _dates(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("end date must not precede start date")
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
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _local_artifact(root: Path, path: Path) -> dict[str, Any]:
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _get_json(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, str | int] | None = None,
) -> dict[str, Any] | list[Any]:
    response = client.get(url, params=params)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, (dict, list)):
        raise ValueError(f"expected a JSON object or array from {response.url}")
    return payload


def _download_once(
    url: str,
    destination: Path,
    *,
    maximum_bytes: int,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.stat().st_size > 0:
        return {
            "size_bytes": destination.stat().st_size,
            "sha256": _sha256(destination),
            "reused_existing": True,
        }
    temporary = destination.with_name(destination.name + ".part")
    temporary.unlink(missing_ok=True)
    size = 0
    digest = hashlib.sha256()
    try:
        with httpx.stream(
            "GET",
            url,
            timeout=httpx.Timeout(timeout_seconds, connect=30),
            follow_redirects=True,
            headers={"User-Agent": "weather-platform-smoke-validation/1.0"},
        ) as response:
            response.raise_for_status()
            with temporary.open("xb") as output:
                for block in response.iter_bytes(1024 * 1024):
                    size += len(block)
                    if size > maximum_bytes:
                        raise ValueError(f"download exceeds size bound: {url}")
                    digest.update(block)
                    output.write(block)
                output.flush()
                os.fsync(output.fileno())
        if size == 0:
            raise ValueError(f"download is empty: {url}")
        os.replace(temporary, destination)
        return {
            "size_bytes": size,
            "sha256": digest.hexdigest(),
            "reused_existing": False,
        }
    finally:
        temporary.unlink(missing_ok=True)


def _download(
    url: str,
    destination: Path,
    *,
    maximum_bytes: int,
    timeout_seconds: int = 300,
    attempts: int = 5,
) -> dict[str, Any]:
    for attempt in range(1, attempts + 1):
        try:
            return _download_once(
                url,
                destination,
                maximum_bytes=maximum_bytes,
                timeout_seconds=timeout_seconds,
            )
        except (httpx.HTTPError, OSError):
            if attempt == attempts:
                raise
            time.sleep(min(2 ** (attempt - 1), 16))
    raise AssertionError("unreachable download retry state")


def download_hotspots(root: Path, start: date, end: date) -> dict[str, Any]:
    settings = CwfisHotspotSettings(
        minimum_free_bytes=10 * 1024**3,
        maximum_download_bytes=100 * 1024**2,
        timeout_seconds=300,
    )
    results = []
    unavailable_dates = []
    days = _dates(start, end)
    with httpx.Client(
        timeout=httpx.Timeout(300, connect=30),
        follow_redirects=True,
        headers={"User-Agent": "weather-platform-smoke-validation/1.0"},
    ) as client:
        for index, day in enumerate(days, start=1):
            remote = remote_object_from_head(client, day)
            if remote is None:
                unavailable_dates.append(day.isoformat())
                print(f"CWFIS hotspots unavailable from source: {day}", flush=True)
                continue
            request = {
                "data_date": day.isoformat(),
                "url": remote.url,
                "filename": remote.filename,
                "size_bytes": remote.size_bytes,
                "last_modified": (
                    remote.last_modified.isoformat().replace("+00:00", "Z")
                    if remote.last_modified
                    else None
                ),
                "etag": remote.etag,
                "relative_path": raw_relative_path(day).as_posix(),
                "replace_existing": False,
            }
            results.append(ingest_request(request, root, settings))
            if index <= 5 or index % 10 == 0 or day == end:
                print(f"CWFIS hotspots {index}/{len(days)}: {day}", flush=True)
    publish_latest(results, root)
    return {
        "status": "complete" if not unavailable_dates else "complete_with_source_gaps",
        "source": "NRCan CWFIS Fire M3",
        "first_date": start.isoformat(),
        "last_date": end.isoformat(),
        "date_count": len(results),
        "requested_date_count": len(days),
        "unavailable_date_count": len(unavailable_dates),
        "unavailable_dates": unavailable_dates,
        "raw_bytes": sum(int(item["raw_size_bytes"]) for item in results),
        "feature_count": sum(int(item["feature_count"]) for item in results),
        "manifests": [str(item["manifest"]) for item in results],
    }


def _airnow_path(root: Path, timestamp: datetime) -> Path:
    return (
        root
        / "raw"
        / "epa"
        / "airnow"
        / "hourly_observations"
        / f"{timestamp:%Y}"
        / f"{timestamp:%m}"
        / f"{timestamp:%d}"
        / f"HourlyAQObs_{timestamp:%Y%m%d%H}.dat"
    )


def _validate_airnow(path: Path) -> dict[str, int]:
    rows = 0
    canadian_rows = 0
    canadian_pm25_rows = 0
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        missing = AIRNOW_COLUMNS - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"AirNow file lacks columns {sorted(missing)}: {path}")
        for row in reader:
            rows += 1
            if row["CountryCode"].strip() != "CA":
                continue
            canadian_rows += 1
            if row["PM25_Measured"].strip() == "1" and row["PM25"].strip():
                canadian_pm25_rows += 1
    if rows == 0:
        raise ValueError(f"AirNow file has no observation rows: {path}")
    return {
        "row_count": rows,
        "canadian_row_count": canadian_rows,
        "canadian_pm25_row_count": canadian_pm25_rows,
    }


def download_airnow(
    root: Path,
    start: date,
    end: date,
    workers: int,
) -> dict[str, Any]:
    timestamps = [
        datetime(day.year, day.month, day.day, hour, tzinfo=UTC)
        for day in _dates(start, end)
        for hour in range(24)
    ]

    def fetch(timestamp: datetime) -> dict[str, Any]:
        filename = f"HourlyAQObs_{timestamp:%Y%m%d%H}.dat"
        url = f"{AIRNOW_BASE}/{timestamp:%Y}/{timestamp:%Y%m%d}/{filename}"
        path = _airnow_path(root, timestamp)
        artifact = _download(url, path, maximum_bytes=20 * 1024**2)
        return {
            "valid_time": timestamp.isoformat().replace("+00:00", "Z"),
            "relative_path": path.relative_to(root).as_posix(),
            "source_url": url,
            **artifact,
            **_validate_airnow(path),
        }

    records = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for index, record in enumerate(executor.map(fetch, timestamps), start=1):
            records.append(record)
            if index <= 10 or index % 100 == 0 or index == len(timestamps):
                print(f"AirNow {index}/{len(timestamps)} hours", flush=True)

    manifest_path = (
        root / "raw" / "epa" / "airnow" / "hourly_observations" / f"{start}_{end}-manifest.json"
    )
    payload = {
        "schema_version": 1,
        "provider": "AirNow",
        "product": "HourlyAQObs",
        "data_status": "preliminary/near-real-time",
        "first_date": start.isoformat(),
        "last_date": end.isoformat(),
        "file_count": len(records),
        "total_bytes": sum(int(item["size_bytes"]) for item in records),
        "canadian_pm25_row_count": sum(int(item["canadian_pm25_row_count"]) for item in records),
        "files": records,
    }
    _atomic_json(manifest_path, payload)
    return {
        "status": "complete",
        "manifest": str(manifest_path),
        **{key: payload[key] for key in ("file_count", "total_bytes", "canadian_pm25_row_count")},
    }


def download_aqs(root: Path) -> dict[str, Any]:
    filenames = (
        "hourly_88101_2026.zip",
        "hourly_88502_2026.zip",
        "aqs_sites.zip",
    )
    records = []
    for filename in filenames:
        path = root / "raw" / "epa" / "aqs" / "2026" / filename
        artifact = _download(f"{AQS_BASE}/{filename}", path, maximum_bytes=2 * 1024**3)
        if not zipfile.is_zipfile(path):
            raise ValueError(f"EPA AQS artifact is not a valid ZIP: {path}")
        with zipfile.ZipFile(path) as archive:
            bad_member = archive.testzip()
            if bad_member is not None:
                raise ValueError(f"EPA AQS ZIP has a corrupt member: {bad_member}")
            members = archive.namelist()
        records.append(
            {
                "relative_path": path.relative_to(root).as_posix(),
                "source_url": f"{AQS_BASE}/{filename}",
                "member_count": len(members),
                **artifact,
            }
        )
        print(f"EPA AQS: {filename}", flush=True)
    manifest_path = root / "raw" / "epa" / "aqs" / "2026" / "manifest.json"
    payload = {
        "schema_version": 1,
        "provider": "US EPA AQS",
        "year": 2026,
        "parameters": {
            "88101": "PM2.5 FRM/FEM mass",
            "88502": "Acceptable PM2.5 AQI/speciation mass",
        },
        "files": records,
    }
    _atomic_json(manifest_path, payload)
    return {
        "status": "complete",
        "manifest": str(manifest_path),
        "file_count": len(records),
        "total_bytes": sum(int(item["size_bytes"]) for item in records),
    }


def download_catalogues(root: Path, start: date, end: date) -> dict[str, Any]:
    catalogue_root = root / "raw" / "catalogues" / "smoke_validation_2026"
    catalogue_root.mkdir(parents=True, exist_ok=True)
    time_start = f"{start.isoformat()}T00:00:00Z"
    time_end = f"{end.isoformat()}T23:59:59Z"
    bbox_text = ",".join(str(value) for value in CANADA_BBOX)
    records = []
    with httpx.Client(
        timeout=httpx.Timeout(300, connect=30),
        follow_redirects=True,
        headers={"User-Agent": "weather-platform-smoke-validation/1.0"},
    ) as client:
        cmr = _get_json(
            client,
            CMR_GRANULES,
            params={
                "short_name": "MCD64A1",
                "version": "061",
                "temporal": f"{time_start},{time_end}",
                "bounding_box": bbox_text,
                "page_size": 2000,
            },
        )
        assert isinstance(cmr, dict)
        cmr_path = catalogue_root / f"mcd64a1-v061-{start}_{end}.json"
        _atomic_json(cmr_path, cmr)
        cmr_count = len(cmr.get("feed", {}).get("entry", []))
        records.append(
            {
                "dataset": "NASA MCD64A1 v061",
                "catalogue": _local_artifact(root, cmr_path),
                "item_count": cmr_count,
                "data_download_status": "requires NASA Earthdata authorization",
            }
        )
        print(f"NASA CMR MCD64A1 catalogue: {cmr_count} granules", flush=True)

        polygon = "POLYGON((-141 41,-52 41,-52 84,-141 84,-141 41))"
        filter_text = (
            "Collection/Name eq 'SENTINEL-5P' "
            "and contains(Name,'L2__AER_LH') "
            f"and ContentDate/Start ge {time_start} "
            f"and ContentDate/Start le {time_end} "
            f"and OData.CSC.Intersects(area=geography'SRID=4326;{polygon}')"
        )
        tropomi_pages = []
        next_url: str | None = CDSE_PRODUCTS
        params: dict[str, str | int] | None = {
            "$filter": filter_text,
            "$top": 1000,
            "$orderby": "ContentDate/Start asc",
        }
        while next_url:
            page = _get_json(client, next_url, params=params)
            assert isinstance(page, dict)
            tropomi_pages.append(page)
            next_link = page.get("@odata.nextLink")
            next_url = str(next_link) if next_link else None
            params = None
        tropomi_path = catalogue_root / f"tropomi-aer-lh-{start}_{end}.json"
        _atomic_json(tropomi_path, {"pages": tropomi_pages})
        tropomi_count = sum(len(page.get("value", [])) for page in tropomi_pages)
        records.append(
            {
                "dataset": "Sentinel-5P TROPOMI OFFL L2 AER_LH",
                "catalogue": _local_artifact(root, tropomi_path),
                "item_count": tropomi_count,
                "data_download_status": (
                    "catalogued; download event-matched overpasses from the public "
                    "meeo-s5p AWS bucket after fire event selection"
                ),
            }
        )
        print(f"TROPOMI AER_LH catalogue: {tropomi_count} granules", flush=True)

        for product_type in ("ATL_FM__2A", "ATL_EBD_2A"):
            pages = []
            next_url = EARTHCARE_STAC
            params = {
                "bbox": bbox_text,
                "datetime": f"{time_start}/{time_end}",
                "limit": 1000,
                "filter": f"productType = '{product_type}'",
                "filter-lang": "cql2-text",
            }
            while next_url:
                page = _get_json(client, next_url, params=params)
                assert isinstance(page, dict)
                pages.append(page)
                link = next(
                    (
                        item.get("href")
                        for item in page.get("links", [])
                        if item.get("rel") == "next"
                    ),
                    None,
                )
                next_url = str(link) if link else None
                params = None
            path = catalogue_root / f"earthcare-{product_type}-{start}_{end}.json"
            _atomic_json(path, {"pages": pages})
            count = sum(len(page.get("features", [])) for page in pages)
            records.append(
                {
                    "dataset": f"EarthCARE {product_type}",
                    "catalogue": _local_artifact(root, path),
                    "item_count": count,
                    "data_download_status": "requires ESA EO Sign-In authorization",
                }
            )
            print(f"EarthCARE {product_type} catalogue: {count} products", flush=True)

        mplnet_records = []
        for month in range(start.month, end.month + 1):
            payload = _get_json(
                client,
                MPLNET_SITES,
                params={
                    "api": "",
                    "format": "json",
                    "sites": "collection;MPLCAN",
                    "year": start.year,
                    "month": month,
                },
            )
            path = catalogue_root / f"mplnet-mplcan-{start.year}-{month:02d}.json"
            _atomic_json(path, payload)
            assert isinstance(payload, list)
            mplnet_records.append(
                {
                    **_local_artifact(root, path),
                    "site_count": len(payload),
                }
            )
        records.append(
            {
                "dataset": "NASA MPLNET V3 MPLCAN site availability",
                "catalogues": mplnet_records,
                "data_download_status": (
                    "no 2026 aerosol profile files returned for the Canadian collection"
                ),
            }
        )

    manifest_path = catalogue_root / f"{start}_{end}-manifest.json"
    payload = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "spatial_extent": {"bbox_wgs84": list(CANADA_BBOX)},
        "temporal_extent": {"start": start.isoformat(), "end": end.isoformat()},
        "records": records,
    }
    _atomic_json(manifest_path, payload)
    return {
        "status": "complete_with_access_gaps",
        "manifest": str(manifest_path),
        "records": records,
    }


def download_tropomi(
    root: Path,
    start: date,
    end: date,
    workers: int,
) -> dict[str, Any]:
    catalogue_path = (
        root / "raw" / "catalogues" / "smoke_validation_2026" / f"tropomi-aer-lh-{start}_{end}.json"
    )
    if not catalogue_path.is_file():
        raise FileNotFoundError(
            f"TROPOMI catalogue is absent; run the catalogues component first: {catalogue_path}"
        )
    catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
    items = [item for page in catalogue["pages"] for item in page["value"]]
    if len({item["Name"] for item in items}) != len(items):
        raise ValueError("TROPOMI catalogue contains duplicate product names")

    def fetch(item: dict[str, Any]) -> dict[str, Any]:
        filename = str(item["Name"])
        start_time = str(item["ContentDate"]["Start"])
        sensing_match = re.search(r"L2__AER_LH_(\d{8})T", filename)
        if sensing_match is None:
            raise ValueError(f"unrecognized TROPOMI product name: {filename}")
        observed = datetime.strptime(sensing_match.group(1), "%Y%m%d").date()
        expected_size = int(item["ContentLength"])
        url = f"{TROPOMI_OPEN_DATA_BASE}/OFFL/L2__AER_LH/{observed:%Y/%m/%d}/{filename}"
        path = (
            root
            / "raw"
            / "copernicus"
            / "sentinel-5p"
            / "tropomi"
            / "offl"
            / "l2_aer_lh"
            / f"{observed:%Y}"
            / f"{observed:%m}"
            / f"{observed:%d}"
            / filename
        )
        if path.is_file() and path.stat().st_size != expected_size:
            path.unlink()
        artifact = _download(url, path, maximum_bytes=512 * 1024**2, timeout_seconds=900)
        if int(artifact["size_bytes"]) != expected_size:
            path.unlink(missing_ok=True)
            raise ValueError(
                f"TROPOMI size mismatch for {filename}: {artifact['size_bytes']} != {expected_size}"
            )
        with path.open("rb") as source:
            if source.read(8) != b"\x89HDF\r\n\x1a\n":
                raise ValueError(f"TROPOMI product is not NetCDF4/HDF5: {path}")
        return {
            "product_id": item["Id"],
            "name": filename,
            "content_start": start_time,
            "content_end": item["ContentDate"]["End"],
            "relative_path": path.relative_to(root).as_posix(),
            "source_url": url,
            **artifact,
        }

    records = []
    worker_count = min(workers, 8)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        for index, record in enumerate(executor.map(fetch, items), start=1):
            records.append(record)
            if index <= 8 or index % 25 == 0 or index == len(items):
                print(f"TROPOMI AER_LH {index}/{len(items)} products", flush=True)

    manifest_path = (
        root
        / "raw"
        / "copernicus"
        / "sentinel-5p"
        / "tropomi"
        / "offl"
        / "l2_aer_lh"
        / f"{start}_{end}-manifest.json"
    )
    payload = {
        "schema_version": 1,
        "provider": "Copernicus Sentinel-5P",
        "product": "TROPOMI OFFL L2 AER_LH",
        "source_mirror": TROPOMI_OPEN_DATA_BASE,
        "spatial_selection": {
            "method": "CDSE catalogue footprint intersects Canada validation bbox",
            "bbox_wgs84": list(CANADA_BBOX),
        },
        "first_date": start.isoformat(),
        "last_date": end.isoformat(),
        "file_count": len(records),
        "total_bytes": sum(int(item["size_bytes"]) for item in records),
        "files": records,
    }
    _atomic_json(manifest_path, payload)
    return {
        "status": "complete",
        "manifest": str(manifest_path),
        "file_count": payload["file_count"],
        "total_bytes": payload["total_bytes"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--spinup-days", type=int, default=1)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument(
        "--component",
        choices=("all", "hotspots", "airnow", "aqs", "catalogues", "tropomi"),
        default="all",
    )
    args = parser.parse_args()
    if args.spinup_days < 0:
        parser.error("--spinup-days must not be negative")
    if not 1 <= args.workers <= 32:
        parser.error("--workers must be between 1 and 32")

    root = args.data_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    input_start = args.start - timedelta(days=args.spinup_days)
    results: dict[str, Any] = {}
    if args.component in {"all", "hotspots"}:
        results["hotspots"] = download_hotspots(root, input_start, args.end)
    if args.component in {"all", "airnow"}:
        results["airnow"] = download_airnow(root, input_start, args.end, args.workers)
    if args.component in {"all", "aqs"}:
        results["aqs"] = download_aqs(root)
    if args.component in {"all", "catalogues"}:
        results["catalogues"] = download_catalogues(root, args.start, args.end)
    if args.component in {"all", "tropomi"}:
        results["tropomi"] = download_tropomi(root, args.start, args.end, args.workers)

    output_directory = (
        root
        / "derived"
        / "smoke"
        / "validation"
        / "input-archives"
        / f"observations-2026-{args.start}_{args.end}"
    )
    manifest_path = output_directory / f"{args.component}-download-manifest.json"
    payload = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "experiment_start": args.start.isoformat(),
        "experiment_end": args.end.isoformat(),
        "input_start": input_start.isoformat(),
        "component": args.component,
        "results": results,
    }
    _atomic_json(manifest_path, payload)
    print(json.dumps({"manifest": str(manifest_path), "results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
