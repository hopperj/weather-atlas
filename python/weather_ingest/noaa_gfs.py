"""Operational NOAA GFS discovery, storage, and FLEXPART-oriented validation."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

from weather_ingest.downloader import StreamingDownloader
from weather_ingest.grib import (
    EcCodesCliInspector,
    validate_grib2_envelopes,
    validate_grib_content,
)
from weather_ingest.models import ParsedSourceObject, RemoteObject
from weather_ingest.storage import resolve_under

GFS_HOST = "nomads.ncep.noaa.gov"
GFS_BASE_URL = f"https://{GFS_HOST}/pub/data/nccf/com/gfs/prod"
GFS_ARCHIVE_HOST = "noaa-gfs-bdp-pds.s3.amazonaws.com"
GFS_ARCHIVE_BASE_URL = f"https://{GFS_ARCHIVE_HOST}"
GFS_RUN_HOURS = (0, 6, 12, 18)
DEFAULT_FORECAST_HOURS = tuple(range(0, 25, 3))
SUPPORTED_RESOLUTIONS = {
    "1p00": (360, 181),
    "0p25": (1440, 721),
}


def _positive_integer(
    values: Mapping[str, str], name: str, default: int, *, allow_zero: bool = False
) -> int:
    raw = values.get(name, str(default)).strip()
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    minimum = 0 if allow_zero else 1
    if parsed < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return parsed


def _forecast_hours(value: str) -> tuple[int, ...]:
    try:
        hours = tuple(sorted({int(item.strip()) for item in value.split(",") if item.strip()}))
    except ValueError as exc:
        raise ValueError("GFS_FORECAST_HOURS must be a comma-separated integer list") from exc
    if not hours:
        raise ValueError("GFS_FORECAST_HOURS must not be empty")
    if any(hour < 0 or hour > 384 or hour % 3 for hour in hours):
        raise ValueError("GFS forecast hours must be three-hourly values in the range 0..384")
    return hours


@dataclass(frozen=True, slots=True)
class GfsIngestionSettings:
    """Bounded runtime settings shared by Airflow tasks and local tests."""

    resolution: str = "1p00"
    forecast_hours: tuple[int, ...] = DEFAULT_FORECAST_HOURS
    lookback_hours: int = 18
    maximum_cycles_per_run: int = 2
    minimum_free_bytes: int = 50 * 1024**3
    maximum_download_bytes: int = 2 * 1024**3
    timeout_seconds: int = 240

    def __post_init__(self) -> None:
        if self.resolution not in SUPPORTED_RESOLUTIONS:
            raise ValueError(f"GFS resolution must be one of {sorted(SUPPORTED_RESOLUTIONS)}")
        if not self.forecast_hours:
            raise ValueError("at least one GFS forecast hour is required")
        if tuple(sorted(set(self.forecast_hours))) != self.forecast_hours:
            raise ValueError("GFS forecast hours must be sorted and unique")
        if any(hour < 0 or hour > 384 or hour % 3 for hour in self.forecast_hours):
            raise ValueError("GFS forecast hours must be three-hourly values in 0..384")
        if self.lookback_hours < 6:
            raise ValueError("GFS lookback must be at least six hours")
        if self.maximum_cycles_per_run < 1:
            raise ValueError("GFS maximum cycles per run must be positive")
        if self.minimum_free_bytes < 0:
            raise ValueError("GFS minimum free bytes must not be negative")
        if self.maximum_download_bytes < 1 or self.timeout_seconds < 1:
            raise ValueError("GFS download limits must be positive")

    @classmethod
    def from_environment(cls, values: Mapping[str, str] | None = None) -> GfsIngestionSettings:
        environment = os.environ if values is None else values
        return cls(
            resolution=environment.get("GFS_RESOLUTION", "1p00").strip(),
            forecast_hours=_forecast_hours(
                environment.get(
                    "GFS_FORECAST_HOURS",
                    ",".join(str(hour) for hour in DEFAULT_FORECAST_HOURS),
                )
            ),
            lookback_hours=_positive_integer(environment, "GFS_LOOKBACK_HOURS", 18),
            maximum_cycles_per_run=_positive_integer(environment, "GFS_MAXIMUM_CYCLES_PER_RUN", 2),
            minimum_free_bytes=_positive_integer(
                environment,
                "GFS_MINIMUM_FREE_BYTES",
                50 * 1024**3,
                allow_zero=True,
            ),
            maximum_download_bytes=_positive_integer(
                environment, "GFS_MAXIMUM_DOWNLOAD_BYTES", 2 * 1024**3
            ),
            timeout_seconds=_positive_integer(environment, "GFS_TIMEOUT_SECONDS", 240),
        )

    @property
    def dimensions(self) -> tuple[int, int]:
        return SUPPORTED_RESOLUTIONS[self.resolution]

    @property
    def domain_code(self) -> str:
        return f"global_{self.resolution}"

    def as_dict(self) -> dict[str, object]:
        return {
            "resolution": self.resolution,
            "forecast_hours": list(self.forecast_hours),
            "lookback_hours": self.lookback_hours,
            "maximum_cycles_per_run": self.maximum_cycles_per_run,
            "minimum_free_bytes": self.minimum_free_bytes,
            "maximum_download_bytes": self.maximum_download_bytes,
            "timeout_seconds": self.timeout_seconds,
        }


def candidate_cycles(now: datetime, *, lookback_hours: int) -> tuple[datetime, ...]:
    """Return recent nominal GFS cycles, newest first."""

    if now.tzinfo is None:
        raise ValueError("GFS discovery time must be timezone-aware")
    if lookback_hours < 6:
        raise ValueError("GFS lookback must be at least six hours")
    now = now.astimezone(UTC)
    cutoff = now - timedelta(hours=lookback_hours)
    cycle = now.replace(minute=0, second=0, microsecond=0)
    cycle -= timedelta(hours=cycle.hour % 6)
    cycles: list[datetime] = []
    while cycle >= cutoff:
        cycles.append(cycle)
        cycle -= timedelta(hours=6)
    return tuple(cycles)


def gfs_filename(cycle: datetime, forecast_hour: int, resolution: str) -> str:
    if cycle.tzinfo is None:
        raise ValueError("GFS cycle must be timezone-aware")
    return f"gfs.t{cycle.astimezone(UTC):%H}z.pgrb2.{resolution}.f{forecast_hour:03d}"


def gfs_object_url(cycle: datetime, forecast_hour: int, resolution: str) -> str:
    cycle = cycle.astimezone(UTC)
    filename = gfs_filename(cycle, forecast_hour, resolution)
    return f"{GFS_BASE_URL}/gfs.{cycle:%Y%m%d}/{cycle:%H}/atmos/{filename}"


def gfs_archive_object_url(cycle: datetime, forecast_hour: int, resolution: str) -> str:
    """Return the stable NOAA Open Data archive URL for one GFS object."""

    cycle = cycle.astimezone(UTC)
    filename = gfs_filename(cycle, forecast_hour, resolution)
    return f"{GFS_ARCHIVE_BASE_URL}/gfs.{cycle:%Y%m%d}/{cycle:%H}/atmos/{filename}"


def cycle_relative_directory(settings: GfsIngestionSettings, cycle: datetime) -> Path:
    cycle = cycle.astimezone(UTC)
    return Path(
        "raw",
        "noaa",
        "gfs",
        settings.domain_code,
        f"{cycle:%Y}",
        f"{cycle:%m}",
        f"{cycle:%d}",
        f"{cycle:%H}",
    )


def object_relative_path(
    settings: GfsIngestionSettings, cycle: datetime, forecast_hour: int
) -> Path:
    return cycle_relative_directory(settings, cycle) / gfs_filename(
        cycle, forecast_hour, settings.resolution
    )


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_utc(value: object, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a UTC offset")
    return parsed.astimezone(UTC)


def _manifest_is_complete(data_root: Path, settings: GfsIngestionSettings, cycle: datetime) -> bool:
    cycle_directory = cycle_relative_directory(settings, cycle)
    manifest_path = resolve_under(data_root, cycle_directory / "manifest.json")
    if not manifest_path.is_file() or manifest_path.is_symlink():
        return False
    try:
        payload = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or payload.get("provider") != "noaa"
        or payload.get("product") != "gfs"
        or payload.get("resolution") != settings.resolution
        or payload.get("initialization_time") != _utc_text(cycle)
        or payload.get("forecast_hours") != list(settings.forecast_hours)
    ):
        return False
    files = payload.get("files")
    if not isinstance(files, list) or len(files) != len(settings.forecast_hours):
        return False
    expected_names = {
        gfs_filename(cycle, hour, settings.resolution) for hour in settings.forecast_hours
    }
    observed_names: set[str] = set()
    for value in files:
        if not isinstance(value, dict):
            return False
        filename = value.get("filename")
        size_bytes = value.get("size_bytes")
        if (
            not isinstance(filename, str)
            or filename not in expected_names
            or isinstance(size_bytes, bool)
            or not isinstance(size_bytes, int)
            or size_bytes <= 0
        ):
            return False
        source_path = resolve_under(data_root, cycle_directory / filename)
        if (
            not source_path.is_file()
            or source_path.is_symlink()
            or source_path.stat().st_size != size_bytes
        ):
            return False
        observed_names.add(filename)
    return observed_names == expected_names


def remote_object_from_head(
    client: httpx.Client, cycle: datetime, forecast_hour: int, resolution: str
) -> RemoteObject | None:
    filename = gfs_filename(cycle, forecast_hour, resolution)
    url = gfs_object_url(cycle, forecast_hour, resolution)
    response = client.head(url)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    content_length = response.headers.get("Content-Length")
    if content_length is None:
        raise ValueError(f"NOAA response has no Content-Length: {url}")
    try:
        size_bytes = int(content_length)
    except ValueError as exc:
        raise ValueError(f"NOAA returned an invalid Content-Length: {url}") from exc
    if size_bytes <= 0:
        raise ValueError(f"NOAA returned an empty GFS object: {url}")
    last_modified: datetime | None = None
    if response.headers.get("Last-Modified"):
        last_modified = parsedate_to_datetime(response.headers["Last-Modified"]).astimezone(UTC)
    return RemoteObject(
        url=url,
        filename=filename,
        size_bytes=size_bytes,
        size_is_exact=True,
        last_modified=last_modified,
        etag=response.headers.get("ETag"),
    )


HeadObject = Callable[[datetime, int, str], RemoteObject | None]


def discover_download_plan(
    settings: GfsIngestionSettings,
    data_root: Path | str,
    *,
    now: datetime,
    head_object: HeadObject,
) -> dict[str, object]:
    """Find complete recent provider cycles that do not have a valid local manifest."""

    root = Path(data_root).expanduser().resolve()
    selected_cycles: list[datetime] = []
    requests: list[dict[str, object]] = []
    for cycle in candidate_cycles(now, lookback_hours=settings.lookback_hours):
        if _manifest_is_complete(root, settings, cycle):
            continue
        remotes: list[tuple[int, RemoteObject]] = []
        for forecast_hour in settings.forecast_hours:
            remote = head_object(cycle, forecast_hour, settings.resolution)
            if remote is None:
                remotes = []
                break
            if remote.size_bytes is None or remote.size_bytes > settings.maximum_download_bytes:
                raise ValueError(
                    f"GFS object is outside the configured download bound: {remote.url}"
                )
            remotes.append((forecast_hour, remote))
        if not remotes:
            continue
        selected_cycles.append(cycle)
        for forecast_hour, remote in remotes:
            requests.append(
                {
                    "initialization_time": _utc_text(cycle),
                    "valid_time": _utc_text(cycle + timedelta(hours=forecast_hour)),
                    "forecast_hour": forecast_hour,
                    "url": remote.url,
                    "filename": remote.filename,
                    "size_bytes": remote.size_bytes,
                    "relative_path": object_relative_path(
                        settings, cycle, forecast_hour
                    ).as_posix(),
                }
            )
        if len(selected_cycles) >= settings.maximum_cycles_per_run:
            break
    return {
        "status": "ready" if requests else "no_new_data",
        "settings": settings.as_dict(),
        "cycles": [_utc_text(cycle) for cycle in selected_cycles],
        "requests": requests,
    }


def plan_from_noaa(
    settings: GfsIngestionSettings,
    data_root: Path | str,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    with httpx.Client(
        timeout=httpx.Timeout(settings.timeout_seconds, connect=15.0),
        follow_redirects=True,
        headers={"User-Agent": "weather-platform-gfs-ingest/0.1"},
    ) as client:
        return discover_download_plan(
            settings,
            data_root,
            now=now or datetime.now(UTC),
            head_object=lambda cycle, hour, resolution: remote_object_from_head(
                client, cycle, hour, resolution
            ),
        )


def _settings_from_plan(plan: Mapping[str, object]) -> GfsIngestionSettings:
    value = plan.get("settings")
    if not isinstance(value, Mapping):
        raise ValueError("GFS plan settings are missing")
    forecast_hours = value.get("forecast_hours")
    if not isinstance(forecast_hours, list):
        raise ValueError("GFS plan forecast hours are invalid")
    return GfsIngestionSettings(
        resolution=str(value["resolution"]),
        forecast_hours=tuple(int(hour) for hour in forecast_hours),
        lookback_hours=int(value["lookback_hours"]),
        maximum_cycles_per_run=int(value["maximum_cycles_per_run"]),
        minimum_free_bytes=int(value["minimum_free_bytes"]),
        maximum_download_bytes=int(value["maximum_download_bytes"]),
        timeout_seconds=int(value["timeout_seconds"]),
    )


def validate_gfs_file(
    path: Path | str,
    *,
    cycle: datetime,
    forecast_hour: int,
    settings: GfsIngestionSettings,
) -> dict[str, object]:
    """Validate envelope, time/grid identity, and the core FLEXPART 3-D fields."""

    source = Path(path)
    envelope = validate_grib2_envelopes(source)
    metadata = EcCodesCliInspector(timeout_seconds=settings.timeout_seconds).inspect(source)
    if envelope.message_count != len(metadata.messages):
        raise ValueError("GFS GRIB envelope and ecCodes message counts disagree")
    parsed = ParsedSourceObject(
        remote=RemoteObject(
            url=gfs_object_url(cycle, forecast_hour, settings.resolution),
            filename=gfs_filename(cycle, forecast_hour, settings.resolution),
            size_bytes=envelope.size_bytes,
        ),
        product_code="gfs",
        producer="NCEP",
        domain_code=settings.domain_code,
        initialization_time=cycle,
        valid_time=cycle + timedelta(hours=forecast_hour),
        forecast_hour=forecast_hour,
        parameter="complete_pressure_grid",
        source_level="all",
        grid=f"LatLon{settings.resolution}",
        data_format="grib2",
    )
    content = validate_grib_content(
        metadata,
        parsed,
        expected_grid=parsed.grid,
        expected_dimensions=settings.dimensions,
    )

    required_3d = ("u", "v", "w", "t", "r")
    levels_by_field: dict[str, set[str]] = {name: set() for name in required_3d}
    for message in metadata.messages:
        if (
            message.short_name in levels_by_field
            and message.type_of_level == "isobaricInhPa"
            and message.level is not None
        ):
            levels_by_field[message.short_name].add(message.level)
    common_levels = set.intersection(*(levels_by_field[name] for name in required_3d))
    if len(common_levels) < 20:
        counts = {name: len(levels) for name, levels in levels_by_field.items()}
        raise ValueError(
            "GFS file lacks a complete FLEXPART pressure-level core "
            f"(common={len(common_levels)}, fields={counts})"
        )

    available = {
        (message.short_name, message.type_of_level, message.level) for message in metadata.messages
    }
    required_surface = {
        ("10u", "heightAboveGround", "10"),
        ("10v", "heightAboveGround", "10"),
        ("2t", "heightAboveGround", "2"),
        ("sp", "surface", "0"),
    }
    missing_surface = required_surface - available
    if missing_surface:
        raise ValueError(
            f"GFS file lacks required FLEXPART surface fields: {sorted(missing_surface)}"
        )
    return {
        "message_count": content.message_count,
        "grid_type": content.grid_type,
        "grid_width": content.grid_width,
        "grid_height": content.grid_height,
        "common_pressure_level_count": len(common_levels),
    }


def download_and_validate_request(
    request: Mapping[str, object],
    data_root: Path | str,
    settings: GfsIngestionSettings,
) -> dict[str, object]:
    cycle = _parse_utc(request.get("initialization_time"), label="initialization_time")
    forecast_hour = int(request["forecast_hour"])
    filename = str(request["filename"])
    expected_filename = gfs_filename(cycle, forecast_hour, settings.resolution)
    if filename != expected_filename:
        raise ValueError("GFS request filename does not match its cycle and forecast hour")
    remote = RemoteObject(
        url=str(request["url"]),
        filename=filename,
        size_bytes=int(request["size_bytes"]),
        size_is_exact=True,
    )
    relative_path = Path(str(request["relative_path"]))
    if relative_path != object_relative_path(settings, cycle, forecast_hour):
        raise ValueError("GFS request storage path is not canonical")
    with StreamingDownloader(
        data_root,
        allowed_hosts=frozenset({GFS_HOST}),
        minimum_free_bytes=settings.minimum_free_bytes,
        maximum_download_bytes=settings.maximum_download_bytes,
        timeout_seconds=settings.timeout_seconds,
        user_agent="weather-platform-gfs-ingest/0.1",
    ) as downloader:
        result = downloader.download(remote, relative_path)
    validation = validate_gfs_file(
        result.path,
        cycle=cycle,
        forecast_hour=forecast_hour,
        settings=settings,
    )
    return {
        "initialization_time": _utc_text(cycle),
        "valid_time": _utc_text(cycle + timedelta(hours=forecast_hour)),
        "forecast_hour": forecast_hour,
        "filename": filename,
        "relative_path": relative_path.as_posix(),
        "size_bytes": result.size_bytes,
        "sha256": result.sha256,
        "reused_existing": result.reused_existing,
        **validation,
    }


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        with temporary.open("x") as output:
            json.dump(payload, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_cycle_manifests(
    plan: Mapping[str, object],
    results: Iterable[Mapping[str, object]],
    data_root: Path | str,
) -> dict[str, object]:
    """Publish per-cycle manifests only after every configured file validates."""

    settings = _settings_from_plan(plan)
    source = plan.get("source", GFS_BASE_URL)
    if source not in {GFS_BASE_URL, GFS_ARCHIVE_BASE_URL}:
        raise ValueError("GFS plan source is invalid")
    root = Path(data_root).expanduser().resolve()
    expected_cycles_value = plan.get("cycles")
    if not isinstance(expected_cycles_value, list):
        raise ValueError("GFS plan cycles are invalid")
    expected_cycles = {_parse_utc(value, label="cycle") for value in expected_cycles_value}
    grouped: dict[datetime, list[dict[str, object]]] = {}
    for value in results:
        result = dict(value)
        cycle = _parse_utc(result.get("initialization_time"), label="result initialization_time")
        grouped.setdefault(cycle, []).append(result)
    if set(grouped) != expected_cycles:
        raise ValueError("validated GFS results do not cover every planned cycle")

    manifests: list[str] = []
    for cycle in sorted(grouped):
        cycle_results = sorted(grouped[cycle], key=lambda item: int(item["forecast_hour"]))
        if [int(item["forecast_hour"]) for item in cycle_results] != list(settings.forecast_hours):
            raise ValueError("validated GFS results do not cover every forecast hour")
        files: list[dict[str, object]] = []
        for result in cycle_results:
            relative_path = Path(str(result["relative_path"]))
            source_path = resolve_under(root, relative_path)
            if (
                not source_path.is_file()
                or source_path.is_symlink()
                or source_path.stat().st_size != int(result["size_bytes"])
            ):
                raise ValueError(f"validated GFS file is missing: {relative_path}")
            files.append(
                {
                    "forecast_hour": int(result["forecast_hour"]),
                    "valid_time": str(result["valid_time"]),
                    "filename": str(result["filename"]),
                    "size_bytes": int(result["size_bytes"]),
                    "sha256": str(result["sha256"]),
                    "message_count": int(result["message_count"]),
                    "common_pressure_level_count": int(result["common_pressure_level_count"]),
                }
            )
        manifest_relative = cycle_relative_directory(settings, cycle) / "manifest.json"
        manifest_path = resolve_under(root, manifest_relative)
        _atomic_json(
            manifest_path,
            {
                "schema_version": 1,
                "provider": "noaa",
                "product": "gfs",
                "source": source,
                "resolution": settings.resolution,
                "grid_dimensions": list(settings.dimensions),
                "initialization_time": _utc_text(cycle),
                "forecast_hours": list(settings.forecast_hours),
                "created_at": _utc_text(datetime.now(UTC)),
                "files": files,
            },
        )
        manifests.append(manifest_relative.as_posix())

    if manifests:
        latest_cycle = max(expected_cycles)
        latest_manifest = cycle_relative_directory(settings, latest_cycle) / "manifest.json"
        latest_path = resolve_under(
            root, Path("raw", "noaa", "gfs", settings.domain_code, "latest.json")
        )
        current_latest_cycle: datetime | None = None
        if latest_path.is_file() and not latest_path.is_symlink():
            try:
                current_latest = json.loads(latest_path.read_text())
                current_latest_cycle = _parse_utc(
                    current_latest.get("initialization_time"),
                    label="latest initialization_time",
                )
            except (AttributeError, OSError, ValueError, json.JSONDecodeError):
                current_latest_cycle = None
        if current_latest_cycle is None or latest_cycle >= current_latest_cycle:
            _atomic_json(
                latest_path,
                {
                    "schema_version": 1,
                    "initialization_time": _utc_text(latest_cycle),
                    "manifest": latest_manifest.as_posix(),
                    "updated_at": _utc_text(datetime.now(UTC)),
                },
            )
    return {
        "status": "complete" if manifests else "no_new_data",
        "cycles": [_utc_text(cycle) for cycle in sorted(expected_cycles)],
        "manifests": manifests,
        "file_count": sum(len(items) for items in grouped.values()),
        "bytes": sum(int(item["size_bytes"]) for items in grouped.values() for item in items),
    }
