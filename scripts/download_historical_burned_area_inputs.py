#!/usr/bin/env python3
"""Download a frozen CMR catalogue of MCD64A1 or VNP64A1 granules."""

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
HDF5_SIGNATURE = b"\x89HDF\r\n\x1a\n"
PRODUCT_NAME = re.compile(
    r"^(?P<product>MCD64A1|VNP64A1)\.A(?P<year>\d{4})(?P<day>\d{3})\."
    r".+\.hdf$"
)
PRODUCTS = {
    "MCD64A1": {"version": "061", "directory": "mcd64a1"},
    "VNP64A1": {"version": "002", "directory": "vnp64a1"},
}


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


def load_dotenv_key(path: Path, name: str) -> None:
    if name in os.environ or not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != name:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[name] = value
        return


def catalogue_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    feed = payload.get("feed")
    if not isinstance(feed, dict):
        feed = payload.get("response", {}).get("feed")
    entries = feed.get("entry", []) if isinstance(feed, dict) else []
    if not isinstance(entries, list) or not entries:
        raise ValueError("CMR catalogue contains no granules")
    return entries


def data_link(entry: dict[str, Any]) -> str:
    candidates = [
        link["href"]
        for link in entry.get("links", [])
        if isinstance(link, dict)
        and link.get("rel") == DATA_RELATION
        and not link.get("inherited")
        and isinstance(link.get("href"), str)
        and link["href"].endswith(".hdf")
    ]
    if len(candidates) != 1:
        raise ValueError(
            f"CMR entry has {len(candidates)} direct HDF links: {entry.get('title')}"
        )
    parsed = urlparse(candidates[0])
    if parsed.scheme != "https" or parsed.hostname != NASA_HOST:
        raise ValueError(f"CMR HDF link is outside the allowed NASA host: {candidates[0]}")
    return candidates[0]


def destination(root: Path, url: str) -> tuple[Path, re.Match[str]]:
    filename = Path(urlparse(url).path).name
    match = PRODUCT_NAME.fullmatch(filename)
    if match is None:
        raise ValueError(f"unexpected burned-area filename: {filename}")
    product = PRODUCTS[match.group("product")]
    observed = datetime(int(match.group("year")), 1, 1) + timedelta(
        days=int(match.group("day")) - 1
    )
    path = (
        root
        / "raw"
        / "nasa"
        / "lpdaac"
        / product["directory"]
        / f"v{product['version']}"
        / match.group("year")
        / f"{observed:%m}"
        / filename
    )
    return path, match


def valid_hdf(path: Path) -> bool:
    with path.open("rb") as source:
        signature = source.read(8)
    return signature.startswith(HDF4_SIGNATURE) or signature == HDF5_SIGNATURE


def download(url: str, path: Path, token: str) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.stat().st_size > 0:
        if valid_hdf(path):
            return {
                "size_bytes": path.stat().st_size,
                "sha256": sha256(path),
                "reused_existing": True,
            }
        path.unlink()
    temporary = path.with_name(path.name + ".part")
    temporary.unlink(missing_ok=True)
    size = 0
    digest = hashlib.sha256()
    try:
        with httpx.Client(timeout=httpx.Timeout(900, connect=30)) as client:
            authorization = client.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": "weather-platform-historical-burned-area/1.0",
                },
                follow_redirects=False,
            )
            if not authorization.is_redirect:
                authorization.raise_for_status()
                raise PermissionError("NASA did not return an authorized delivery redirect")
            delivery_url = authorization.headers.get("location", "")
            delivery = urlparse(delivery_url)
            if delivery.scheme != "https" or delivery.hostname != NASA_DELIVERY_HOST:
                raise PermissionError("NASA redirected outside its delivery host")
            with client.stream(
                "GET",
                delivery_url,
                headers={"User-Agent": "weather-platform-historical-burned-area/1.0"},
                follow_redirects=False,
            ) as response:
                response.raise_for_status()
                if response.url.host != NASA_DELIVERY_HOST:
                    raise PermissionError("NASA delivery left the allowed host")
                with temporary.open("xb") as output:
                    for block in response.iter_bytes(1024 * 1024):
                        size += len(block)
                        if size > 2 * 1024**3:
                            raise ValueError(f"granule exceeds the size bound: {url}")
                        digest.update(block)
                        output.write(block)
                    output.flush()
                    os.fsync(output.fileno())
        if size == 0 or not valid_hdf(temporary):
            raise ValueError("NASA response is not a non-empty HDF4/HDF5 granule")
        os.replace(temporary, path)
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
    arguments = parser.parse_args()
    if not 1 <= arguments.workers <= 10:
        parser.error("--workers must be between 1 and 10")

    load_dotenv_key(arguments.env_file, "EARTHDATA_TOKEN")
    token = os.environ.get("EARTHDATA_TOKEN")
    if not token:
        parser.error("set EARTHDATA_TOKEN in the environment or .env")

    root = arguments.data_root.expanduser().resolve()
    catalogue_path = arguments.catalogue.expanduser().resolve()
    entries = catalogue_entries(json.loads(catalogue_path.read_text(encoding="utf-8")))
    product_names = {
        match.group("product")
        for entry in entries
        for _path, match in [destination(root, data_link(entry))]
    }
    if len(product_names) != 1:
        raise ValueError(f"catalogue mixes products: {sorted(product_names)}")
    product_name = product_names.pop()
    product = PRODUCTS[product_name]

    def fetch(entry: dict[str, Any]) -> dict[str, Any]:
        url = data_link(entry)
        path, _match = destination(root, url)
        return {
            "cmr_id": entry["id"],
            "title": entry["title"],
            "time_start": entry.get("time_start"),
            "time_end": entry.get("time_end"),
            "source_url": url,
            "relative_path": path.relative_to(root).as_posix(),
            **download(url, path, token),
        }

    records: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=arguments.workers) as executor:
        for index, record in enumerate(executor.map(fetch, entries), start=1):
            records.append(record)
            if index <= arguments.workers or index % 10 == 0 or index == len(entries):
                print(f"{product_name} {index}/{len(entries)} granules", flush=True)

    years = sorted(
        {
            PRODUCT_NAME.fullmatch(Path(record["relative_path"]).name).group("year")
            for record in records
        }
    )
    manifest_directory = (
        root
        / "raw"
        / "nasa"
        / "lpdaac"
        / product["directory"]
        / f"v{product['version']}"
    )
    manifest_path = manifest_directory / (
        f"{years[0]}-{years[-1]}-historical-input-manifest.json"
    )
    payload = {
        "schema_version": 1,
        "provider": "NASA LP DAAC",
        "product": product_name,
        "version": product["version"],
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "catalogue": {
            "path": str(catalogue_path),
            "size_bytes": catalogue_path.stat().st_size,
            "sha256": sha256(catalogue_path),
        },
        "credentials_recorded": False,
        "file_count": len(records),
        "total_bytes": sum(int(record["size_bytes"]) for record in records),
        "files": records,
    }
    atomic_json(manifest_path, payload)
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "manifest_sha256": sha256(manifest_path),
                "file_count": len(records),
                "total_bytes": payload["total_bytes"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
