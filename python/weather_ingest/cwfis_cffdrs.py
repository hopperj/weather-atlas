"""Archived NRCan CWFIS CFFDRS grids and deterministic per-fire sampling."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
import numpy as np
import rasterio
from rasterio.warp import transform

from weather_ingest.storage import resolve_under

CWFIS_HOST = "cwfis.cfs.nrcan.gc.ca"
CWFIS_WCS_URL = f"https://{CWFIS_HOST}/geoserver/public/wcs"
CWFIS_CFFDRS_METADATA_URL = (
    "https://cwfis.cfs.nrcan.gc.ca/downloads/cffdrs/"
    "fwi_grids_metadata_NAP_ISO_19115_2003_EN.pdf"
)
FIELDS = ("ffmc", "dmc", "dc")
VALUE_RANGES = {"ffmc": (0.0, 101.0), "dmc": (0.0, 1000.0), "dc": (0.0, 2000.0)}


def _integer(
    values: Mapping[str, str], name: str, default: int, *, minimum: int = 0
) -> int:
    raw = values.get(name, str(default)).strip()
    try:
        result = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if result < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return result


@dataclass(frozen=True, slots=True)
class CwfisCffdrsSettings:
    """Bounded collection settings for the daily national CFFDRS mosaics."""

    lag_days: int = 1
    lookback_days: int = 4
    maximum_days_per_run: int = 3
    minimum_free_bytes: int = 5 * 1024**3
    maximum_grid_bytes: int = 128 * 1024**2
    timeout_seconds: int = 300

    def __post_init__(self) -> None:
        if self.lag_days < 0 or self.lookback_days < 1 or self.maximum_days_per_run < 1:
            raise ValueError("invalid CWFIS CFFDRS date limits")
        if self.minimum_free_bytes < 0 or self.maximum_grid_bytes < 1:
            raise ValueError("invalid CWFIS CFFDRS storage limits")
        if self.timeout_seconds < 1:
            raise ValueError("invalid CWFIS CFFDRS timeout")

    @classmethod
    def from_environment(
        cls, values: Mapping[str, str] | None = None
    ) -> CwfisCffdrsSettings:
        environment = os.environ if values is None else values
        return cls(
            lag_days=_integer(environment, "CWFIS_CFFDRS_LAG_DAYS", 1),
            lookback_days=_integer(environment, "CWFIS_CFFDRS_LOOKBACK_DAYS", 4, minimum=1),
            maximum_days_per_run=_integer(
                environment, "CWFIS_CFFDRS_MAXIMUM_DAYS_PER_RUN", 3, minimum=1
            ),
            minimum_free_bytes=_integer(
                environment, "CWFIS_CFFDRS_MINIMUM_FREE_BYTES", 5 * 1024**3
            ),
            maximum_grid_bytes=_integer(
                environment, "CWFIS_CFFDRS_MAXIMUM_GRID_BYTES", 128 * 1024**2, minimum=1
            ),
            timeout_seconds=_integer(
                environment, "CWFIS_CFFDRS_TIMEOUT_SECONDS", 300, minimum=1
            ),
        )


def candidate_dates(now: datetime, settings: CwfisCffdrsSettings) -> tuple[date, ...]:
    if now.tzinfo is None:
        raise ValueError("CWFIS discovery time must be timezone-aware")
    newest = now.astimezone(UTC).date() - timedelta(days=settings.lag_days)
    return tuple(newest - timedelta(days=offset) for offset in range(settings.lookback_days))


def coverage_url(field: str, data_date: date) -> str:
    if field not in FIELDS:
        raise ValueError(f"unsupported CFFDRS field: {field}")
    parameters = {
        "service": "WCS",
        "version": "2.0.1",
        "request": "GetCoverage",
        "coverageId": f"public__{field}",
        "format": "image/tiff",
        "subset": f'time("{data_date.isoformat()}T00:00:00.000Z")',
    }
    return f"{CWFIS_WCS_URL}?{urlencode(parameters)}"


def grid_relative_path(data_date: date, field: str) -> Path:
    return Path(
        "raw",
        "nrcan",
        "cwfis",
        "cffdrs",
        f"{data_date:%Y}",
        f"{data_date:%m}",
        f"{data_date:%d}",
        f"{field}.tif",
    )


def manifest_relative_path(data_date: date) -> Path:
    return grid_relative_path(data_date, "ffmc").parent / "manifest.json"


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
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_grid(path: Path, field: str) -> dict[str, Any]:
    try:
        with rasterio.open(path) as dataset:
            if dataset.count != 1 or dataset.crs is None:
                raise ValueError(f"CWFIS {field} grid must be a georeferenced single-band raster")
            band = dataset.read(1, masked=True)
            finite = np.asarray(band.compressed(), dtype=np.float64)
            if finite.size == 0:
                raise ValueError(f"CWFIS {field} grid contains no valid cells")
            lower, upper = VALUE_RANGES[field]
            if float(finite.min()) < lower or float(finite.max()) > upper:
                raise ValueError(f"CWFIS {field} grid contains out-of-range values")
            return {
                "crs": dataset.crs.to_string(),
                "width": dataset.width,
                "height": dataset.height,
                "minimum": float(finite.min()),
                "maximum": float(finite.max()),
                "nodata": dataset.nodata,
            }
    except rasterio.errors.RasterioIOError as exc:
        raise ValueError(f"CWFIS {field} response is not a readable GeoTIFF") from exc


def _download_grid(
    client: httpx.Client,
    destination: Path,
    field: str,
    data_date: date,
    settings: CwfisCffdrsSettings,
) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    temporary.unlink(missing_ok=True)
    byte_count = 0
    digest = hashlib.sha256()
    try:
        with client.stream("GET", coverage_url(field, data_date)) as response:
            response.raise_for_status()
            if response.url.scheme != "https" or response.url.host != CWFIS_HOST:
                raise ValueError("CWFIS grid redirected outside the allowed HTTPS host")
            content_type = response.headers.get("content-type", "").split(";", 1)[0]
            if content_type not in {"image/tiff", "image/geotiff", "application/octet-stream"}:
                raise ValueError(f"unexpected CWFIS response type: {content_type}")
            with temporary.open("xb") as output:
                for block in response.iter_bytes(chunk_size=1024 * 1024):
                    byte_count += len(block)
                    if byte_count > settings.maximum_grid_bytes:
                        raise ValueError("CWFIS grid exceeds configured size limit")
                    digest.update(block)
                    output.write(block)
                output.flush()
                os.fsync(output.fileno())
        if byte_count == 0:
            raise ValueError("CWFIS returned an empty grid")
        validation = _validate_grid(temporary, field)
        os.replace(temporary, destination)
        return {
            "relative_path": grid_relative_path(data_date, field).as_posix(),
            "size_bytes": byte_count,
            "sha256": digest.hexdigest(),
            "source_url": coverage_url(field, data_date),
            **validation,
        }
    finally:
        temporary.unlink(missing_ok=True)


def load_complete_manifest(data_root: Path, data_date: date) -> dict[str, Any] | None:
    path = resolve_under(data_root, manifest_relative_path(data_date))
    if not path.is_file() or path.is_symlink():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            payload.get("schema_version") != 1
            or payload.get("product") != "cwfis_cffdrs_codes"
            or payload.get("data_date") != data_date.isoformat()
        ):
            return None
        for field in FIELDS:
            record = payload["grids"][field]
            grid = resolve_under(data_root, record["relative_path"])
            if (
                not grid.is_file()
                or grid.is_symlink()
                or grid.stat().st_size != record["size_bytes"]
                or _sha256(grid) != record["sha256"]
            ):
                return None
        return payload
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def ingest_date(
    data_root: Path,
    data_date: date,
    settings: CwfisCffdrsSettings,
    *,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """Download, validate, checksum, and atomically publish one dated triplet."""

    root = data_root.expanduser().resolve()
    existing = load_complete_manifest(root, data_date)
    if existing is not None:
        return existing | {"status": "already_complete"}
    root.mkdir(parents=True, exist_ok=True)
    expected_bytes = len(FIELDS) * settings.maximum_grid_bytes
    if shutil.disk_usage(root).free - expected_bytes < settings.minimum_free_bytes:
        raise OSError("insufficient storage reserve for CWFIS CFFDRS grids")
    grids: dict[str, Any] = {}
    with httpx.Client(
        timeout=httpx.Timeout(settings.timeout_seconds, connect=15.0),
        follow_redirects=True,
        headers={"User-Agent": "weather-platform-cwfis-cffdrs/1.0"},
        transport=transport,
    ) as client:
        for field in FIELDS:
            destination = resolve_under(root, grid_relative_path(data_date, field))
            grids[field] = _download_grid(client, destination, field, data_date, settings)
    payload = {
        "schema_version": 1,
        "provider": "nrcan",
        "product": "cwfis_cffdrs_codes",
        "data_date": data_date.isoformat(),
        "collected_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "metadata_url": CWFIS_CFFDRS_METADATA_URL,
        "grids": grids,
    }
    _atomic_json(resolve_under(root, manifest_relative_path(data_date)), payload)
    return payload | {"status": "complete"}


def ingest_recent(
    data_root: Path,
    now: datetime,
    settings: CwfisCffdrsSettings,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for data_date in candidate_dates(now, settings):
        if len(results) >= settings.maximum_days_per_run:
            break
        results.append(ingest_date(data_root, data_date, settings))
    return {"status": "complete", "dates": results}


def sample_fire_weather(
    data_root: Path, data_date: date, latitude: float, longitude: float
) -> dict[str, Any]:
    """Nearest-cell sample of a checksum-verified, dated CFFDRS triplet."""

    manifest = load_complete_manifest(data_root, data_date)
    if manifest is None:
        raise FileNotFoundError(f"no complete CWFIS CFFDRS grids for {data_date}")
    values: dict[str, float] = {}
    cells: dict[str, dict[str, int]] = {}
    for field in FIELDS:
        record = manifest["grids"][field]
        path = resolve_under(data_root, record["relative_path"])
        with rasterio.open(path) as dataset:
            xs, ys = transform("EPSG:4326", dataset.crs, [longitude], [latitude])
            row, column = dataset.index(xs[0], ys[0])
            if row < 0 or column < 0 or row >= dataset.height or column >= dataset.width:
                raise ValueError(f"fire lies outside the CWFIS {field} grid")
            sample = dataset.read(1, window=((row, row + 1), (column, column + 1)), masked=True)
            if bool(np.ma.getmaskarray(sample)[0, 0]):
                raise ValueError(f"CWFIS {field} has no value at the fire location")
            value = float(sample[0, 0])
            lower, upper = VALUE_RANGES[field]
            if not lower < value <= upper:
                raise ValueError(f"CWFIS {field} sample is outside the model input range")
            values[field] = value
            cells[field] = {"row": row, "column": column}
    manifest_path = resolve_under(data_root, manifest_relative_path(data_date))
    return {
        **values,
        "source": "NRCan CWFIS national CFFDRS analysis",
        "source_date": data_date.isoformat(),
        "sampling": "nearest_grid_cell_v1",
        "manifest_relative_path": manifest_relative_path(data_date).as_posix(),
        "manifest_sha256": _sha256(manifest_path),
        "cells": cells,
    }


def enrich_event_snapshot(snapshot_path: Path, data_root: Path) -> dict[str, Any]:
    """Freeze per-event CFFDRS values and exact grid provenance into a snapshot."""

    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    enriched = 0
    missing = 0
    for event in payload["events"]:
        observed = datetime.fromisoformat(event["last_observed_at"].replace("Z", "+00:00"))
        try:
            event["fire_weather"] = sample_fire_weather(
                data_root, observed.date(), event["latitude"], event["longitude"]
            )
            event["warnings"] = [
                warning
                for warning in event.get("warnings", [])
                if warning != "missing_cffeps_fire_weather_codes"
            ]
            enriched += 1
        except (FileNotFoundError, ValueError):
            event.pop("fire_weather", None)
            event.setdefault("warnings", []).append("missing_cffeps_fire_weather_codes")
            event["warnings"] = sorted(set(event["warnings"]))
            missing += 1
    payload["schema_version"] = 2
    payload["cffdrs_enrichment"] = {
        "algorithm": "cwfis_nearest_grid_cell_v1",
        "enriched_event_count": enriched,
        "missing_event_count": missing,
    }
    _atomic_json(snapshot_path, payload)
    content = snapshot_path.read_bytes()
    return {
        "path": snapshot_path.as_posix(),
        "sha256": hashlib.sha256(content).hexdigest(),
        "event_count": payload["event_count"],
        "detection_count": payload["detection_count"],
        "enriched_event_count": enriched,
        "missing_event_count": missing,
    }
