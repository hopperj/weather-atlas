#!/usr/bin/env python3
"""Download the preregistered GFAS v1.4.2 fields from the ECMWF data portal."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

PORTAL_HOST = "aux.ecmwf.int"
PORTAL_URL = f"https://{PORTAL_HOST}"
REMOTE_ROOT = "/DATA/CAMS_GFAS"
HOURLY_PARAMETERS = (
    "pm2p5fire",
    "cofire",
    "bcfire",
    "apt",
    "apb",
    "injh",
    "frpfire",
    "crfire",
    "offire",
)
DAILY_PARAMETERS = ("pm2p5fire", "cofire", "bcfire", "crfire")
MANIFEST_LINE = re.compile(r"^(?P<size>[1-9][0-9]*)\t(?P<filename>[^/\s]+)$")


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


def _load_dotenv_keys(path: Path, names: tuple[str, ...]) -> None:
    """Load only named simple KEY=VALUE records without printing secret values."""
    if not path.is_file():
        return
    wanted = set(names)
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in wanted or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[key] = value


def _local_hour_directory(root: Path, day: date, hour: int) -> Path:
    return (
        root
        / "raw"
        / "ecmwf"
        / "cams"
        / "gfas"
        / "v1.4.2"
        / f"{day:%Y}"
        / f"{day:%m}"
        / f"{day:%d}"
        / f"{hour:02d}"
    )


def _provider_manifest_name(day: date, hour: int, period: str) -> str:
    return f"z_cams_c_ecmf_{day:%Y%m%d}{hour:02d}00_gfas_{period}.manifest"


def _remote_path(day: date, hour: int, filename: str) -> str:
    return f"{REMOTE_ROOT}/{day:%Y%m%d}/{hour:02d}/{filename}"


def _transfer(operations: list[tuple[str, Path]], *, portal_ip: str | None = None) -> None:
    if not operations:
        return

    base_url = f"https://{portal_ip}" if portal_ip else PORTAL_URL
    request_extensions = {"sni_hostname": PORTAL_HOST} if portal_ip else None
    request_headers = {
        "User-Agent": "weather-platform-gfas-validation/1.0",
        **({"Host": PORTAL_HOST} if portal_ip else {}),
    }
    with httpx.Client(
        base_url=base_url,
        timeout=httpx.Timeout(900, connect=30),
        follow_redirects=False,
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=10),
        headers=request_headers,
    ) as client:
        login = None
        for attempt in range(1, 6):
            try:
                login = client.post(
                    "/ecpds/login",
                    data={
                        "username": os.environ["ECMWF_DATA_PORTAL_USERNAME"],
                        "password": os.environ["ECMWF_DATA_PORTAL_PASSWORD"],
                    },
                    extensions=request_extensions,
                )
                break
            except httpx.HTTPError:
                if attempt == 5:
                    raise
                time.sleep(min(2 ** (attempt - 1), 16))
        if login is None:
            raise AssertionError("unreachable GFAS login retry state")
        if login.is_redirect:
            login_location = login.headers.get("location", "")
            if "/ecpds/data/list" not in login_location:
                raise PermissionError("ECMWF HTTPS portal authentication failed")
        else:
            login.raise_for_status()
            raise PermissionError("ECMWF HTTPS portal authentication failed")

        def fetch_once(remote: str, destination: Path) -> int:
            prefix = "/DATA/"
            if not remote.startswith(prefix):
                raise ValueError(f"GFAS remote path is outside /DATA: {remote}")
            portal_path = f"/ecpds/data/file/{remote.removeprefix(prefix)}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + ".part")
            temporary.unlink(missing_ok=True)
            size = 0
            try:
                with client.stream(
                    "GET",
                    portal_path,
                    extensions=request_extensions,
                ) as response:
                    response.raise_for_status()
                    if response.is_redirect:
                        raise PermissionError("ECMWF portal session expired during transfer")
                    content_type = response.headers.get("content-type", "").lower()
                    if content_type.startswith("text/html"):
                        raise ValueError(f"ECMWF portal returned HTML for {remote}")
                    with temporary.open("xb") as output:
                        for block in response.iter_bytes(1024 * 1024):
                            size += len(block)
                            if size > 512 * 1024**2:
                                raise ValueError(f"GFAS portal file exceeds size bound: {remote}")
                            output.write(block)
                        output.flush()
                        os.fsync(output.fileno())
                if size == 0:
                    raise ValueError(f"GFAS portal returned an empty file: {remote}")
                os.replace(temporary, destination)
                return size
            finally:
                temporary.unlink(missing_ok=True)

        def fetch(operation: tuple[str, Path]) -> int:
            remote, destination = operation
            for attempt in range(1, 6):
                try:
                    return fetch_once(remote, destination)
                except (httpx.HTTPError, OSError) as error:
                    if attempt == 5:
                        raise RuntimeError(
                            f"GFAS transfer failed after five attempts: {remote}"
                        ) from error
                    time.sleep(min(2 ** (attempt - 1), 16))
            raise AssertionError("unreachable GFAS retry state")

        total_bytes = 0
        with ThreadPoolExecutor(max_workers=9) as executor:
            for index, size in enumerate(executor.map(fetch, operations), start=1):
                total_bytes += size
                if index <= 8 or index % 100 == 0 or index == len(operations):
                    print(
                        f"GFAS HTTPS {index}/{len(operations)} files "
                        f"({total_bytes / 1024**2:.1f} MiB)",
                        flush=True,
                    )


def _manifest_operations(root: Path, start: date, end: date) -> list[tuple[str, Path]]:
    operations: list[tuple[str, Path]] = []
    for day in _dates(start, end):
        for hour in range(24):
            periods = ("001", "024") if hour == 0 else ("001",)
            for period in periods:
                filename = _provider_manifest_name(day, hour, period)
                destination = _local_hour_directory(root, day, hour) / filename
                if not destination.is_file() or destination.stat().st_size == 0:
                    operations.append((_remote_path(day, hour, filename), destination))
    return operations


def _parse_provider_manifest(path: Path) -> dict[str, int]:
    files: dict[str, int] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        match = MANIFEST_LINE.fullmatch(raw_line)
        if match is None:
            raise ValueError(f"invalid provider manifest row {path}:{line_number}")
        filename = match.group("filename")
        if filename in files:
            raise ValueError(f"duplicate provider manifest file: {filename}")
        files[filename] = int(match.group("size"))
    if not files:
        raise ValueError(f"empty provider manifest: {path}")
    return files


def _select_files(
    root: Path,
    start: date,
    end: date,
) -> tuple[list[tuple[str, Path]], list[dict[str, Any]]]:
    operations: list[tuple[str, Path]] = []
    records: list[dict[str, Any]] = []
    for day in _dates(start, end):
        for hour in range(24):
            periods = {"001": HOURLY_PARAMETERS}
            if hour == 0:
                periods["024"] = DAILY_PARAMETERS
            for period, parameters in periods.items():
                directory = _local_hour_directory(root, day, hour)
                manifest_name = _provider_manifest_name(day, hour, period)
                manifest_path = directory / manifest_name
                available = _parse_provider_manifest(manifest_path)
                for parameter in parameters:
                    suffix = f"_{period}_{parameter}.grib"
                    matches = [
                        (filename, size)
                        for filename, size in available.items()
                        if filename.endswith(suffix)
                    ]
                    if len(matches) != 1:
                        raise ValueError(
                            f"{manifest_path} has {len(matches)} matches for {parameter}"
                        )
                    filename, expected_size = matches[0]
                    destination = directory / filename
                    if not destination.is_file() or destination.stat().st_size != expected_size:
                        destination.unlink(missing_ok=True)
                        operations.append((_remote_path(day, hour, filename), destination))
                    records.append(
                        {
                            "data_date": day.isoformat(),
                            "hour_utc": hour,
                            "period_hours": int(period),
                            "parameter": parameter,
                            "relative_path": destination.relative_to(root).as_posix(),
                            "expected_size_bytes": expected_size,
                            "source_path": _remote_path(day, hour, filename),
                            "provider_manifest_relative_path": (
                                manifest_path.relative_to(root).as_posix()
                            ),
                        }
                    )
    return operations, records


def _finalize(
    root: Path,
    start: date,
    end: date,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    total_bytes = 0
    for record in records:
        path = root / str(record["relative_path"])
        expected = int(record["expected_size_bytes"])
        if not path.is_file() or path.stat().st_size != expected:
            raise ValueError(f"GFAS file is absent or has the wrong size: {path}")
        record["size_bytes"] = expected
        record["sha256"] = _sha256(path)
        total_bytes += expected

    provider_manifest_records = []
    for day in _dates(start, end):
        for hour in range(24):
            periods = ("001", "024") if hour == 0 else ("001",)
            for period in periods:
                path = _local_hour_directory(root, day, hour) / _provider_manifest_name(
                    day, hour, period
                )
                provider_manifest_records.append(
                    {
                        "relative_path": path.relative_to(root).as_posix(),
                        "size_bytes": path.stat().st_size,
                        "sha256": _sha256(path),
                    }
                )

    identifier = f"gfas-v1.4.2-{start}_{end}"
    manifest_path = (
        root / "derived" / "smoke" / "validation" / "input-archives" / identifier / "manifest.json"
    )
    payload = {
        "schema_version": 1,
        "identifier": identifier,
        "provider": "ECMWF/Copernicus CAMS",
        "product": "GFAS",
        "version": "1.4.2",
        "product_type": "analysis",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_host": PORTAL_HOST,
        "source_root": REMOTE_ROOT,
        "credentials_recorded": False,
        "hourly_parameters": list(HOURLY_PARAMETERS),
        "daily_24_hour_parameters": list(DAILY_PARAMETERS),
        "file_count": len(records),
        "provider_manifest_count": len(provider_manifest_records),
        "total_bytes": total_bytes,
        "files": records,
        "provider_manifests": provider_manifest_records,
    }
    _atomic_json(manifest_path, payload)
    return {
        "manifest": str(manifest_path),
        "file_count": len(records),
        "provider_manifest_count": len(provider_manifest_records),
        "total_bytes": total_bytes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--portal-ip",
        help=(
            "Connect to this ECMWF portal IP while preserving aux.ecmwf.int "
            "TLS SNI/Host verification; useful during a local DNS outage"
        ),
    )
    parser.add_argument(
        "--phase",
        choices=("all", "manifests", "data", "verify"),
        default="all",
    )
    args = parser.parse_args()

    root = args.data_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    _load_dotenv_keys(
        args.env_file,
        ("ECMWF_DATA_PORTAL_USERNAME", "ECMWF_DATA_PORTAL_PASSWORD"),
    )
    missing = [
        name
        for name in ("ECMWF_DATA_PORTAL_USERNAME", "ECMWF_DATA_PORTAL_PASSWORD")
        if not os.environ.get(name)
    ]
    if missing:
        parser.error(f"missing credential environment variable(s): {', '.join(missing)}")

    if args.phase in {"all", "manifests"}:
        operations = _manifest_operations(root, args.start, args.end)
        print(f"GFAS provider manifests requiring transfer: {len(operations)}", flush=True)
        _transfer(operations, portal_ip=args.portal_ip)
        if args.phase == "manifests":
            return 0

    operations, records = _select_files(root, args.start, args.end)
    if args.phase in {"all", "data"}:
        print(f"GFAS data files requiring transfer: {len(operations)}", flush=True)
        _transfer(operations, portal_ip=args.portal_ip)
    result = _finalize(root, args.start, args.end, records)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
