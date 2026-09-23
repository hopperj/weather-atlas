#!/usr/bin/env python3
"""Download catalogued MCD64A1 v061 granules using a NASA Earthdata token."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

DATA_RELATION = "http://esipfed.org/ns/fedsearch/1.1/data#"
NASA_HOST = "data.lpdaac.earthdatacloud.nasa.gov"
NASA_DELIVERY_HOST = "d1nklfio7vscoe.cloudfront.net"
HDF4_SIGNATURE = b"\x0e\x03\x13\x01"
PRODUCT_NAME = re.compile(r"^MCD64A1\.A(?P<year>\d{4})(?P<day>\d{3})\..+\.hdf$")


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


def _data_link(entry: dict[str, Any]) -> str:
    candidates = [
        link["href"]
        for link in entry.get("links", [])
        if link.get("rel") == DATA_RELATION
        and not link.get("inherited")
        and isinstance(link.get("href"), str)
        and link["href"].endswith(".hdf")
    ]
    if len(candidates) != 1:
        raise ValueError(f"CMR entry has {len(candidates)} direct HDF links: {entry.get('title')}")
    parsed = urlparse(candidates[0])
    if parsed.scheme != "https" or parsed.hostname != NASA_HOST:
        raise ValueError(f"CMR HDF link is outside the allowed NASA host: {candidates[0]}")
    return candidates[0]


def _destination(root: Path, url: str) -> Path:
    filename = Path(urlparse(url).path).name
    match = PRODUCT_NAME.fullmatch(filename)
    if match is None:
        raise ValueError(f"unexpected MCD64A1 filename: {filename}")
    observed = datetime(int(match.group("year")), 1, 1) + timedelta(
        days=int(match.group("day")) - 1
    )
    return (
        root
        / "raw"
        / "nasa"
        / "lpdaac"
        / "mcd64a1"
        / "v061"
        / match.group("year")
        / f"{observed:%m}"
        / filename
    )


def _legacy_destination(root: Path, url: str) -> Path:
    filename = Path(urlparse(url).path).name
    match = PRODUCT_NAME.fullmatch(filename)
    if match is None:
        raise ValueError(f"unexpected MCD64A1 filename: {filename}")
    return (
        root
        / "raw"
        / "nasa"
        / "lpdaac"
        / "mcd64a1"
        / "v061"
        / match.group("year")
        / match.group("day")
        / filename
    )


def _download(url: str, destination: Path, token: str) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.stat().st_size > 0:
        with destination.open("rb") as source:
            if source.read(4) != HDF4_SIGNATURE:
                destination.unlink()
            else:
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
        with httpx.Client(timeout=httpx.Timeout(900, connect=30)) as client:
            authorization = client.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": "weather-platform-mcd64a1-validation/1.0",
                },
                follow_redirects=False,
            )
            if not authorization.is_redirect:
                authorization.raise_for_status()
                raise PermissionError("NASA did not return an authorized delivery redirect")
            delivery_url = authorization.headers.get("location", "")
            delivery = urlparse(delivery_url)
            if delivery.scheme != "https" or delivery.hostname != NASA_DELIVERY_HOST:
                raise PermissionError("NASA redirected the download outside its delivery host")

            # The signed delivery URL is already authorized. Do not forward the
            # Earthdata bearer token to the separate object-delivery host.
            with client.stream(
                "GET",
                delivery_url,
                headers={"User-Agent": "weather-platform-mcd64a1-validation/1.0"},
                follow_redirects=False,
            ) as response:
                response.raise_for_status()
                if response.url.host != NASA_DELIVERY_HOST:
                    raise PermissionError("NASA delivery left the allowed host")
                with temporary.open("xb") as output:
                    for block in response.iter_bytes(1024 * 1024):
                        size += len(block)
                        if size > 2 * 1024**3:
                            raise ValueError(f"MCD64A1 granule exceeds the size bound: {url}")
                        digest.update(block)
                        output.write(block)
                    output.flush()
                    os.fsync(output.fileno())
        if size == 0:
            raise ValueError(f"NASA returned an empty granule: {url}")
        with temporary.open("rb") as source:
            if source.read(4) != HDF4_SIGNATURE:
                raise ValueError("NASA response is not an HDF4 granule; check token authorization")
        os.replace(temporary, destination)
        return {
            "size_bytes": size,
            "sha256": digest.hexdigest(),
            "reused_existing": False,
        }
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogue", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    if not 1 <= args.workers <= 10:
        parser.error("--workers must be between 1 and 10")

    _load_dotenv_keys(args.env_file, ("NASA_EARTHDATA_TOKEN", "EARTHDATA_TOKEN"))
    token = os.environ.get("NASA_EARTHDATA_TOKEN") or os.environ.get("EARTHDATA_TOKEN")
    if not token:
        parser.error(
            "set NASA_EARTHDATA_TOKEN (preferred) or EARTHDATA_TOKEN in the environment/.env"
        )

    root = args.data_root.expanduser().resolve()
    catalogue_path = args.catalogue.expanduser().resolve()
    catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
    entries = catalogue["feed"]["entry"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("CMR catalogue contains no granules")

    def fetch(entry: dict[str, Any]) -> dict[str, Any]:
        url = _data_link(entry)
        destination = _destination(root, url)
        legacy = _legacy_destination(root, url)
        if not destination.exists() and legacy.is_file():
            with legacy.open("rb") as source:
                if source.read(4) == HDF4_SIGNATURE:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(legacy, destination)
        return {
            "cmr_id": entry["id"],
            "title": entry["title"],
            "time_start": entry["time_start"],
            "time_end": entry["time_end"],
            "source_url": url,
            "relative_path": destination.relative_to(root).as_posix(),
            **_download(url, destination, token),
        }

    records = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for index, record in enumerate(executor.map(fetch, entries), start=1):
            records.append(record)
            if index <= args.workers or index % 10 == 0 or index == len(entries):
                print(f"MCD64A1 {index}/{len(entries)} granules", flush=True)

    manifest_path = root / "raw" / "nasa" / "lpdaac" / "mcd64a1" / "v061" / "2026-manifest.json"
    payload = {
        "schema_version": 1,
        "provider": "NASA LP DAAC",
        "product": "MCD64A1",
        "version": "061",
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "catalogue": {
            "path": str(catalogue_path),
            "size_bytes": catalogue_path.stat().st_size,
            "sha256": _sha256(catalogue_path),
        },
        "credentials_recorded": False,
        "file_count": len(records),
        "total_bytes": sum(int(record["size_bytes"]) for record in records),
        "files": records,
    }
    _atomic_json(manifest_path, payload)
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "file_count": payload["file_count"],
                "total_bytes": payload["total_bytes"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
