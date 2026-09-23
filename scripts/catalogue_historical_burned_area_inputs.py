#!/usr/bin/env python3
"""Freeze input-only CMR catalogues for historical burned-area products."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

CMR_GRANULES = "https://cmr.earthdata.nasa.gov/search/granules.json"
CANADA_BBOX = (-141.0, 41.0, -52.0, 84.0)
PRODUCTS = (
    {
        "short_name": "MCD64A1",
        "version": "061",
        "role": "primary independent burned area",
    },
    {
        "short_name": "VNP64A1",
        "version": "002",
        "role": "prospective burned-area sensitivity",
    },
)
DENIED_PARTS = {"candidates", "transport", "evaluation", "verification"}


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


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def assert_input_only_destination(data_root: Path, output_root: Path) -> None:
    raw_root = (data_root / "raw").resolve()
    resolved = output_root.resolve()
    if resolved != raw_root and raw_root not in resolved.parents:
        raise ValueError(f"catalogue destination escapes raw input root: {resolved}")
    if DENIED_PARTS.intersection(resolved.parts):
        raise ValueError(f"catalogue destination crosses model-output tree: {resolved}")


def entry_links(entry: dict[str, Any]) -> list[str]:
    return sorted(
        {
            str(link["href"])
            for link in entry.get("links", [])
            if isinstance(link, dict)
            and link.get("href")
            and not link.get("inherited", False)
        }
    )


def catalogue_product(
    client: httpx.Client,
    *,
    product: dict[str, str],
    start: date,
    end: date,
    output_root: Path,
) -> dict[str, Any]:
    temporal = f"{start.isoformat()}T00:00:00Z,{end.isoformat()}T23:59:59Z"
    bbox = ",".join(str(item) for item in CANADA_BBOX)
    params: dict[str, str | int] = {
        "short_name": product["short_name"],
        "version": product["version"],
        "temporal": temporal,
        "bounding_box": bbox,
        "page_size": 2000,
    }
    response = client.get(CMR_GRANULES, params=params)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"CMR returned a non-object for {product['short_name']}")
    feed = payload.get("feed")
    if not isinstance(feed, dict):
        raise ValueError(f"CMR response has no feed for {product['short_name']}")
    entries = feed.get("entry", [])
    if not isinstance(entries, list):
        raise ValueError(f"CMR feed has no entry list for {product['short_name']}")
    if len(entries) >= 2000:
        raise ValueError(
            f"{product['short_name']} reached the page bound; pagination is required"
        )

    filename = (
        f"{product['short_name'].lower()}-v{product['version']}-"
        f"{start.isoformat()}_{end.isoformat()}.json"
    )
    path = output_root / filename
    frozen_payload = {
        "artifact_type": "input-only-cmr-granule-catalogue",
        "schema_version": 1,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "selection_firewall": {
            "model_output_accessed": False,
            "selection_uses_only_provider_metadata": True,
        },
        "request": {
            "url": CMR_GRANULES,
            "params": params,
            "resolved_url": str(response.url),
        },
        "response": payload,
    }
    atomic_json(path, frozen_payload)

    temporal_starts = sorted(
        str(entry["time_start"])
        for entry in entries
        if isinstance(entry, dict) and entry.get("time_start")
    )
    temporal_ends = sorted(
        str(entry["time_end"])
        for entry in entries
        if isinstance(entry, dict) and entry.get("time_end")
    )
    links = {
        link
        for entry in entries
        if isinstance(entry, dict)
        for link in entry_links(entry)
    }
    return {
        **product,
        "catalogue_path": str(path),
        "catalogue_sha256": sha256(path),
        "catalogue_bytes": path.stat().st_size,
        "granule_count": len(entries),
        "first_time_start": temporal_starts[0] if temporal_starts else None,
        "last_time_end": temporal_ends[-1] if temporal_ends else None,
        "unique_provider_link_count": len(links),
        "data_download_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--start", type=parse_date, required=True)
    parser.add_argument("--end", type=parse_date, required=True)
    parser.add_argument(
        "--output-relative-root",
        type=Path,
        default=Path("catalogues/smoke_validation_historical"),
    )
    arguments = parser.parse_args()
    if arguments.end < arguments.start:
        raise ValueError("end date must not precede start date")

    output_root = arguments.data_root / "raw" / arguments.output_relative_root
    assert_input_only_destination(arguments.data_root, output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    with httpx.Client(
        timeout=httpx.Timeout(300, connect=30),
        follow_redirects=True,
        headers={"User-Agent": "weather-platform-smoke-validation-research/1.0"},
    ) as client:
        products = [
            catalogue_product(
                client,
                product=product,
                start=arguments.start,
                end=arguments.end,
                output_root=output_root,
            )
            for product in PRODUCTS
        ]

    manifest_path = output_root / (
        f"burned-area-catalogue-manifest-"
        f"{arguments.start.isoformat()}_{arguments.end.isoformat()}.json"
    )
    manifest = {
        "artifact_type": "input-only-historical-burned-area-catalogue-manifest",
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "period": {
            "start": arguments.start.isoformat(),
            "end": arguments.end.isoformat(),
            "bounding_box_wgs84": list(CANADA_BBOX),
        },
        "selection_firewall": {
            "model_output_accessed": False,
            "performance_metric_accessed": False,
            "provider_metadata_only": True,
        },
        "products": products,
    }
    atomic_json(manifest_path, manifest)
    result = {
        "manifest": str(manifest_path),
        "manifest_sha256": sha256(manifest_path),
        "products": [
            {
                "short_name": product["short_name"],
                "version": product["version"],
                "granule_count": product["granule_count"],
                "catalogue_sha256": product["catalogue_sha256"],
            }
            for product in products
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
