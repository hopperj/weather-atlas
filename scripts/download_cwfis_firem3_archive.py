#!/usr/bin/env python3
"""Download and inventory an annual public CWFIS Fire M3 archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import httpx

ARCHIVE_URL = (
    "https://cwfis.cfs.nrcan.gc.ca/downloads/hotspots/archive/"
    "{year}_{product}.zip"
)
PRODUCTS = {
    "hotspots": "Fire M3 annual hotspot archive",
    "perimeters": "Fire M3 annual buffered-perimeter archive",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    temporary = path.with_name(f"{path.name}.part")
    temporary.unlink(missing_ok=True)
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_archive(path: Path) -> list[dict[str, object]]:
    if not zipfile.is_zipfile(path):
        raise ValueError("CWFIS response is not a ZIP archive")
    records = []
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            member = PurePosixPath(item.filename)
            if member.is_absolute() or ".." in member.parts:
                raise ValueError(f"unsafe CWFIS ZIP member: {item.filename}")
            records.append(
                {
                    "name": item.filename,
                    "uncompressed_bytes": item.file_size,
                    "compressed_bytes": item.compress_size,
                    "crc32": f"{item.CRC:08x}",
                }
            )
        bad_member = archive.testzip()
        if bad_member is not None:
            raise ValueError(f"corrupt CWFIS ZIP member: {bad_member}")
    return records


def download(url: str, destination: Path, maximum_bytes: int) -> dict[str, object]:
    if destination.is_file():
        members = validate_archive(destination)
        return {
            "reused_existing": True,
            "size_bytes": destination.stat().st_size,
            "sha256": sha256(destination),
            "members": members,
            "response_headers": None,
        }
    temporary = destination.with_name(f"{destination.name}.part")
    size = 0
    digest = hashlib.sha256()
    response_headers = None
    for attempt in range(1, 6):
        temporary.unlink(missing_ok=True)
        size = 0
        digest = hashlib.sha256()
        try:
            with httpx.stream(
                "GET",
                url,
                follow_redirects=True,
                timeout=httpx.Timeout(900, connect=30),
                headers={"User-Agent": "weather-platform-smoke-research/1.0"},
            ) as response:
                response.raise_for_status()
                if response.url.host != "cwfis.cfs.nrcan.gc.ca":
                    raise ValueError("CWFIS archive redirected outside the provider host")
                response_headers = {
                    key: response.headers.get(key)
                    for key in ("content-length", "content-type", "etag", "last-modified")
                }
                with temporary.open("xb") as output:
                    for block in response.iter_bytes(1024 * 1024):
                        size += len(block)
                        if size > maximum_bytes:
                            raise ValueError("CWFIS archive exceeds configured size bound")
                        digest.update(block)
                        output.write(block)
                    output.flush()
                    os.fsync(output.fileno())
            if size == 0:
                raise ValueError("CWFIS archive is empty")
            members = validate_archive(temporary)
            os.replace(temporary, destination)
            return {
                "reused_existing": False,
                "size_bytes": size,
                "sha256": digest.hexdigest(),
                "members": members,
                "response_headers": response_headers,
            }
        except (httpx.HTTPError, OSError):
            temporary.unlink(missing_ok=True)
            if attempt == 5:
                raise
            time.sleep(min(2 ** (attempt - 1), 16))
    raise AssertionError("unreachable download retry state")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--product", choices=sorted(PRODUCTS), default="hotspots")
    parser.add_argument("--maximum-bytes", type=int, default=1024**3)
    args = parser.parse_args()
    if not 1994 <= args.year <= datetime.now(UTC).year:
        parser.error("--year is outside the published Fire M3 archive era")

    root = args.data_root.expanduser().resolve()
    directory = root / "raw/nrcan/cwfis/firem3/archive"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{args.year}_{args.product}.zip"
    url = ARCHIVE_URL.format(year=args.year, product=args.product)
    result = download(url, destination, args.maximum_bytes)
    manifest_path = directory / f"{args.year}_{args.product}.manifest.json"
    payload = {
        "schema_version": 1,
        "provider": "Natural Resources Canada, Canadian Wildland Fire Information System",
        "product": PRODUCTS[args.product],
        "year": args.year,
        "source_url": url,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "credentials_recorded": False,
        "file": {
            "relative_path": destination.relative_to(root).as_posix(),
            "size_bytes": result["size_bytes"],
            "sha256": result["sha256"],
        },
        "reused_existing": result["reused_existing"],
        "response_headers": result["response_headers"],
        "member_count": len(result["members"]),
        "members": result["members"],
    }
    atomic_json(manifest_path, payload)
    print(
        json.dumps(
            {
                "archive": str(destination),
                "manifest": str(manifest_path),
                "size_bytes": result["size_bytes"],
                "sha256": result["sha256"],
                "member_count": len(result["members"]),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
