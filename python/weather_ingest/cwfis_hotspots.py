"""Daily NRCan CWFIS Fire M3 VIIRS hotspot ingestion and GeoJSON publication."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

from weather_ingest.downloader import StreamingDownloader, sha256_file
from weather_ingest.models import RemoteObject
from weather_ingest.storage import resolve_under

CWFIS_HOST = "cwfis.cfs.nrcan.gc.ca"
CWFIS_BASE_URL = f"https://{CWFIS_HOST}/downloads/hotspots"
CWFIS_LICENSE_URL = "https://open.canada.ca/en/open-government-licence-canada"
CWFIS_ATTRIBUTION = (
    "Canadian Forest Service, Natural Resources Canada, "
    "Canadian Wildland Fire Information System (CWFIS)"
)
VIIRS_SENSOR = "VIIRS-I"
REQUIRED_COLUMNS = frozenset(
    {
        "lat",
        "lon",
        "rep_date",
        "source",
        "sensor",
        "fwi",
        "fuel",
        "ros",
        "sfc",
        "tfc",
        "bfc",
        "hfi",
        "estarea",
    }
)
NUMERIC_PROPERTIES = ("fwi", "ros", "sfc", "tfc", "bfc", "hfi", "estarea")


def _integer(
    values: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int = 1,
) -> int:
    raw = values.get(name, str(default)).strip()
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return parsed


@dataclass(frozen=True, slots=True)
class CwfisHotspotSettings:
    """Bounded runtime settings for daily CWFIS collection."""

    lag_days: int = 1
    lookback_days: int = 7
    maximum_days_per_run: int = 3
    maximum_rows: int = 500_000
    minimum_free_bytes: int = 5 * 1024**3
    maximum_download_bytes: int = 100 * 1024**2
    timeout_seconds: int = 180

    def __post_init__(self) -> None:
        if self.lag_days < 1:
            raise ValueError("CWFIS lag must be at least one day")
        if self.lookback_days < 1:
            raise ValueError("CWFIS lookback must be positive")
        if self.maximum_days_per_run < 1:
            raise ValueError("CWFIS maximum days per run must be positive")
        if self.maximum_rows < 1:
            raise ValueError("CWFIS maximum rows must be positive")
        if self.minimum_free_bytes < 0:
            raise ValueError("CWFIS minimum free bytes must not be negative")
        if self.maximum_download_bytes < 1 or self.timeout_seconds < 1:
            raise ValueError("CWFIS download limits must be positive")

    @classmethod
    def from_environment(cls, values: Mapping[str, str] | None = None) -> CwfisHotspotSettings:
        environment = os.environ if values is None else values
        return cls(
            lag_days=_integer(environment, "CWFIS_LAG_DAYS", 1),
            lookback_days=_integer(environment, "CWFIS_LOOKBACK_DAYS", 7),
            maximum_days_per_run=_integer(environment, "CWFIS_MAXIMUM_DAYS_PER_RUN", 3),
            maximum_rows=_integer(environment, "CWFIS_MAXIMUM_ROWS", 500_000),
            minimum_free_bytes=_integer(
                environment,
                "CWFIS_MINIMUM_FREE_BYTES",
                5 * 1024**3,
                minimum=0,
            ),
            maximum_download_bytes=_integer(
                environment, "CWFIS_MAXIMUM_DOWNLOAD_BYTES", 100 * 1024**2
            ),
            timeout_seconds=_integer(environment, "CWFIS_TIMEOUT_SECONDS", 180),
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "lag_days": self.lag_days,
            "lookback_days": self.lookback_days,
            "maximum_days_per_run": self.maximum_days_per_run,
            "maximum_rows": self.maximum_rows,
            "minimum_free_bytes": self.minimum_free_bytes,
            "maximum_download_bytes": self.maximum_download_bytes,
            "timeout_seconds": self.timeout_seconds,
        }


def candidate_dates(now: datetime, *, lag_days: int, lookback_days: int) -> tuple[date, ...]:
    if now.tzinfo is None:
        raise ValueError("CWFIS discovery time must be timezone-aware")
    if lag_days < 1 or lookback_days < 1:
        raise ValueError("CWFIS lag and lookback must be positive")
    newest = now.astimezone(UTC).date() - timedelta(days=lag_days)
    return tuple(newest - timedelta(days=offset) for offset in range(lookback_days))


def cwfis_filename(data_date: date) -> str:
    return f"{data_date:%Y%m%d}.csv"


def cwfis_url(data_date: date) -> str:
    return f"{CWFIS_BASE_URL}/{cwfis_filename(data_date)}"


def raw_relative_path(data_date: date) -> Path:
    return Path(
        "raw",
        "nrcan",
        "cwfis",
        "firem3",
        f"{data_date:%Y}",
        f"{data_date:%m}",
        f"{data_date:%d}",
        cwfis_filename(data_date),
    )


def processed_relative_directory(data_date: date) -> Path:
    return Path(
        "processed",
        "nrcan",
        "cwfis",
        "firem3",
        f"{data_date:%Y}",
        f"{data_date:%m}",
        f"{data_date:%d}",
    )


def geojson_relative_path(data_date: date) -> Path:
    return processed_relative_directory(data_date) / "hotspots_viirs.geojson"


def manifest_relative_path(data_date: date) -> Path:
    return processed_relative_directory(data_date) / "manifest.json"


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_data_date(value: object, *, label: str = "data_date") -> date:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO date") from exc


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        with temporary.open("x") as output:
            json.dump(payload, output, separators=(",", ":"), sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        with source.open("rb") as input_file, temporary.open("xb") as output_file:
            shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
            output_file.flush()
            os.fsync(output_file.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _complete_manifest(data_root: Path, data_date: date) -> dict[str, object] | None:
    manifest_path = resolve_under(data_root, manifest_relative_path(data_date))
    if not manifest_path.is_file() or manifest_path.is_symlink():
        return None
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != 1
        or manifest.get("provider") != "nrcan"
        or manifest.get("product") != "cwfis_firem3_hotspots"
        or manifest.get("data_date") != data_date.isoformat()
        or manifest.get("sensor") != VIIRS_SENSOR
    ):
        return None
    for key, expected_path in (
        ("raw", raw_relative_path(data_date)),
        ("geojson", geojson_relative_path(data_date)),
    ):
        artifact = manifest.get(key)
        if not isinstance(artifact, dict):
            return None
        if artifact.get("relative_path") != expected_path.as_posix():
            return None
        size_bytes = artifact.get("size_bytes")
        if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes <= 0:
            return None
        path = resolve_under(data_root, expected_path)
        if not path.is_file() or path.is_symlink() or path.stat().st_size != size_bytes:
            return None
    return manifest


def _manifest_is_complete(data_root: Path, data_date: date) -> bool:
    return _complete_manifest(data_root, data_date) is not None


def _remote_matches_manifest(manifest: Mapping[str, object], remote: RemoteObject) -> bool:
    raw = manifest.get("raw")
    if not isinstance(raw, dict) or raw.get("size_bytes") != remote.size_bytes:
        return False
    if remote.etag is not None and manifest.get("source_etag") != remote.etag:
        return False
    return remote.last_modified is None or manifest.get("source_last_modified") == _utc_text(
        remote.last_modified
    )


def remote_object_from_head(client: httpx.Client, data_date: date) -> RemoteObject | None:
    url = cwfis_url(data_date)
    response = client.head(url)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    raw_size = response.headers.get("Content-Length")
    if raw_size is None:
        raise ValueError(f"CWFIS response has no Content-Length: {url}")
    try:
        size_bytes = int(raw_size)
    except ValueError as exc:
        raise ValueError(f"CWFIS returned an invalid Content-Length: {url}") from exc
    if size_bytes <= 0:
        raise ValueError(f"CWFIS returned an empty object: {url}")
    last_modified = None
    if response.headers.get("Last-Modified"):
        last_modified = parsedate_to_datetime(response.headers["Last-Modified"]).astimezone(UTC)
    return RemoteObject(
        url=url,
        filename=cwfis_filename(data_date),
        size_bytes=size_bytes,
        size_is_exact=True,
        last_modified=last_modified,
        etag=response.headers.get("ETag"),
    )


HeadObject = Callable[[date], RemoteObject | None]


def discover_download_plan(
    settings: CwfisHotspotSettings,
    data_root: Path | str,
    *,
    now: datetime,
    head_object: HeadObject,
) -> dict[str, object]:
    """Find recent, finalized daily CWFIS files missing from local storage."""

    root = Path(data_root).expanduser().resolve()
    requests: list[dict[str, object]] = []
    for data_date in candidate_dates(
        now, lag_days=settings.lag_days, lookback_days=settings.lookback_days
    ):
        local_manifest = _complete_manifest(root, data_date)
        remote = head_object(data_date)
        if remote is None:
            continue
        if remote.size_bytes is None or remote.size_bytes > settings.maximum_download_bytes:
            raise ValueError(f"CWFIS object is outside the configured download bound: {remote.url}")
        if local_manifest is not None and _remote_matches_manifest(local_manifest, remote):
            continue
        raw_path = resolve_under(root, raw_relative_path(data_date))
        requests.append(
            {
                "data_date": data_date.isoformat(),
                "url": remote.url,
                "filename": remote.filename,
                "size_bytes": remote.size_bytes,
                "last_modified": (
                    _utc_text(remote.last_modified) if remote.last_modified else None
                ),
                "etag": remote.etag,
                "relative_path": raw_relative_path(data_date).as_posix(),
                "replace_existing": raw_path.exists(),
            }
        )
        if len(requests) >= settings.maximum_days_per_run:
            break
    return {
        "status": "ready" if requests else "no_new_data",
        "settings": settings.as_dict(),
        "requests": requests,
    }


def plan_from_cwfis(
    settings: CwfisHotspotSettings,
    data_root: Path | str,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    with httpx.Client(
        timeout=httpx.Timeout(settings.timeout_seconds, connect=15.0),
        follow_redirects=True,
        headers={"User-Agent": "weather-platform-cwfis-ingest/0.1"},
    ) as client:
        return discover_download_plan(
            settings,
            data_root,
            now=now or datetime.now(UTC),
            head_object=lambda data_date: remote_object_from_head(client, data_date),
        )


def _observation_time(value: str, data_date: date) -> datetime:
    try:
        parsed = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValueError(f"invalid CWFIS rep_date: {value!r}") from exc
    if parsed.date() != data_date:
        raise ValueError(
            f"CWFIS observation {parsed.isoformat()} is outside {data_date.isoformat()}"
        )
    return parsed


def _coordinate(value: str, *, label: str, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"CWFIS {label} is not numeric") from exc
    if not math.isfinite(parsed) or not minimum <= parsed <= maximum:
        raise ValueError(f"CWFIS {label} is outside its valid range")
    return parsed


def _optional_number(value: str, *, label: str) -> float | None:
    value = value.strip()
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"CWFIS {label} is not numeric") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"CWFIS {label} is not finite")
    return parsed


def _detection_id(observed_at: datetime, latitude: float, longitude: float, sensor: str) -> str:
    identity = f"{_utc_text(observed_at)}|{latitude:.5f}|{longitude:.5f}|{sensor}"
    return hashlib.sha256(identity.encode()).hexdigest()[:24]


def normalize_cwfis_csv(
    source_path: Path | str,
    data_date: date,
    destination_path: Path | str,
    *,
    maximum_rows: int,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    """Validate CWFIS CSV and atomically publish deduplicated VIIRS GeoJSON."""

    source = Path(source_path)
    destination = Path(destination_path)
    features_by_id: dict[str, dict[str, object]] = {}
    raw_row_count = 0
    viirs_row_count = 0
    with source.open(newline="", encoding="utf-8-sig") as input_file:
        reader = csv.DictReader(input_file, skipinitialspace=True)
        fieldnames = set(reader.fieldnames or ())
        missing = REQUIRED_COLUMNS - fieldnames
        if missing:
            raise ValueError(f"CWFIS CSV lacks required columns: {sorted(missing)}")
        for row in reader:
            raw_row_count += 1
            if raw_row_count > maximum_rows:
                raise ValueError(f"CWFIS CSV exceeds the configured {maximum_rows} row bound")
            sensor = row["sensor"].strip()
            if sensor != VIIRS_SENSOR:
                continue
            viirs_row_count += 1
            latitude = _coordinate(row["lat"], label="latitude", minimum=-90, maximum=90)
            longitude = _coordinate(row["lon"], label="longitude", minimum=-180, maximum=180)
            observed_at = _observation_time(row["rep_date"], data_date)
            detection_id = _detection_id(observed_at, latitude, longitude, sensor)
            properties: dict[str, object] = {
                "detection_id": detection_id,
                "observed_at": _utc_text(observed_at),
                "source": row["source"].strip()[:64],
                "sensor": sensor,
                "fuel": row["fuel"].strip()[:64] or None,
            }
            properties.update(
                {name: _optional_number(row[name], label=name) for name in NUMERIC_PROPERTIES}
            )
            feature: dict[str, object] = {
                "type": "Feature",
                "id": detection_id,
                "geometry": {
                    "type": "Point",
                    "coordinates": [longitude, latitude],
                },
                "properties": properties,
            }
            existing = features_by_id.get(detection_id)
            if existing is None:
                features_by_id[detection_id] = feature
                continue
            existing_properties = existing["properties"]
            assert isinstance(existing_properties, dict)
            existing_score = sum(value is not None for value in existing_properties.values())
            new_score = sum(value is not None for value in properties.values())
            if new_score > existing_score:
                features_by_id[detection_id] = feature

    features = sorted(
        features_by_id.values(),
        key=lambda feature: (
            str(feature["properties"]["observed_at"]),  # type: ignore[index]
            str(feature["id"]),
        ),
    )
    observed_times = [
        str(feature["properties"]["observed_at"])  # type: ignore[index]
        for feature in features
    ]
    longitudes = [
        float(feature["geometry"]["coordinates"][0])  # type: ignore[index]
        for feature in features
    ]
    latitudes = [
        float(feature["geometry"]["coordinates"][1])  # type: ignore[index]
        for feature in features
    ]
    payload: dict[str, object] = {
        "type": "FeatureCollection",
        "name": "NRCan CWFIS Fire M3 VIIRS-I daily hotspots",
        "data_date": data_date.isoformat(),
        "generated_at": _utc_text(generated_at or datetime.now(UTC)),
        "source": cwfis_url(data_date),
        "attribution": CWFIS_ATTRIBUTION,
        "license": CWFIS_LICENSE_URL,
        "sensor": VIIRS_SENSOR,
        "nominal_resolution_metres": 375,
        "feature_count": len(features),
        "features": features,
    }
    if features:
        payload["bbox"] = [
            min(longitudes),
            min(latitudes),
            max(longitudes),
            max(latitudes),
        ]
    _atomic_json(destination, payload)
    return {
        "raw_row_count": raw_row_count,
        "viirs_row_count": viirs_row_count,
        "feature_count": len(features),
        "duplicate_count": viirs_row_count - len(features),
        "first_observation": observed_times[0] if observed_times else None,
        "last_observation": observed_times[-1] if observed_times else None,
        "bbox": payload.get("bbox"),
    }


def ingest_request(
    request: Mapping[str, object],
    data_root: Path | str,
    settings: CwfisHotspotSettings,
) -> dict[str, object]:
    data_date = _parse_data_date(request.get("data_date"))
    filename = str(request["filename"])
    if filename != cwfis_filename(data_date):
        raise ValueError("CWFIS request filename is not canonical")
    relative_path = Path(str(request["relative_path"]))
    if relative_path != raw_relative_path(data_date):
        raise ValueError("CWFIS raw storage path is not canonical")
    remote = RemoteObject(
        url=str(request["url"]),
        filename=filename,
        size_bytes=int(request["size_bytes"]),
        size_is_exact=True,
    )
    root = Path(data_root).expanduser().resolve()
    with StreamingDownloader(
        root,
        allowed_hosts=frozenset({CWFIS_HOST}),
        minimum_free_bytes=settings.minimum_free_bytes,
        maximum_download_bytes=settings.maximum_download_bytes,
        timeout_seconds=settings.timeout_seconds,
        user_agent="weather-platform-cwfis-ingest/0.1",
    ) as downloader:
        downloaded = downloader.download(
            remote,
            relative_path,
            replace_existing=bool(request.get("replace_existing", False)),
        )

    geojson_relative = geojson_relative_path(data_date)
    geojson_path = resolve_under(root, geojson_relative)
    normalized = normalize_cwfis_csv(
        downloaded.path,
        data_date,
        geojson_path,
        maximum_rows=settings.maximum_rows,
    )
    geojson_size = geojson_path.stat().st_size
    geojson_sha256 = sha256_file(geojson_path)
    manifest_relative = manifest_relative_path(data_date)
    _atomic_json(
        resolve_under(root, manifest_relative),
        {
            "schema_version": 1,
            "provider": "nrcan",
            "product": "cwfis_firem3_hotspots",
            "data_date": data_date.isoformat(),
            "sensor": VIIRS_SENSOR,
            "nominal_resolution_metres": 375,
            "source": cwfis_url(data_date),
            "source_last_modified": request.get("last_modified"),
            "source_etag": request.get("etag"),
            "attribution": CWFIS_ATTRIBUTION,
            "license": CWFIS_LICENSE_URL,
            "created_at": _utc_text(datetime.now(UTC)),
            "raw": {
                "relative_path": relative_path.as_posix(),
                "size_bytes": downloaded.size_bytes,
                "sha256": downloaded.sha256,
            },
            "geojson": {
                "relative_path": geojson_relative.as_posix(),
                "size_bytes": geojson_size,
                "sha256": geojson_sha256,
            },
            **normalized,
        },
    )
    return {
        "data_date": data_date.isoformat(),
        "manifest": manifest_relative.as_posix(),
        "raw_relative_path": relative_path.as_posix(),
        "raw_size_bytes": downloaded.size_bytes,
        "raw_sha256": downloaded.sha256,
        "reused_existing": downloaded.reused_existing,
        "geojson_relative_path": geojson_relative.as_posix(),
        "geojson_size_bytes": geojson_size,
        "geojson_sha256": geojson_sha256,
        **normalized,
    }


def _current_latest_date(path: Path) -> date | None:
    if not path.is_file() or path.is_symlink():
        return None
    try:
        payload = json.loads(path.read_text())
        return _parse_data_date(payload.get("data_date"), label="latest data_date")
    except (AttributeError, OSError, ValueError, json.JSONDecodeError):
        return None


def publish_latest(
    results: Iterable[Mapping[str, object]], data_root: Path | str
) -> dict[str, object]:
    """Publish a stable latest GeoJSON snapshot without regressing on recovery."""

    items = [dict(result) for result in results]
    if not items:
        return {
            "status": "no_new_data",
            "days": [],
            "feature_count": 0,
            "raw_bytes": 0,
        }
    root = Path(data_root).expanduser().resolve()
    newest = max(items, key=lambda item: _parse_data_date(item.get("data_date")))
    newest_date = _parse_data_date(newest.get("data_date"))
    latest_directory = Path("processed", "nrcan", "cwfis", "firem3")
    latest_pointer = resolve_under(root, latest_directory / "latest.json")
    current_date = _current_latest_date(latest_pointer)
    if current_date is None or newest_date >= current_date:
        source = resolve_under(root, Path(str(newest["geojson_relative_path"])))
        latest_geojson = resolve_under(root, latest_directory / "latest.geojson")
        if (
            not source.is_file()
            or source.is_symlink()
            or source.stat().st_size != int(newest["geojson_size_bytes"])
        ):
            raise ValueError("newest CWFIS GeoJSON artifact is missing")
        _atomic_copy(source, latest_geojson)
        _atomic_json(
            latest_pointer,
            {
                "schema_version": 1,
                "data_date": newest_date.isoformat(),
                "sensor": VIIRS_SENSOR,
                "feature_count": int(newest["feature_count"]),
                "manifest": str(newest["manifest"]),
                "geojson": (latest_directory / "latest.geojson").as_posix(),
                "source_geojson": str(newest["geojson_relative_path"]),
                "updated_at": _utc_text(datetime.now(UTC)),
            },
        )
    return {
        "status": "complete",
        "days": sorted(str(item["data_date"]) for item in items),
        "feature_count": sum(int(item["feature_count"]) for item in items),
        "raw_bytes": sum(int(item["raw_size_bytes"]) for item in items),
    }
