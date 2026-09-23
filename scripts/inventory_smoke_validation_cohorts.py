#!/usr/bin/env python3
"""Build an input-only historical smoke-validation product inventory."""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

DATE_8_PATTERN = re.compile(r"(?<!\d)(20\d{6})(?!\d)")
MODIS_DATE_PATTERN = re.compile(r"\.A(20\d{2})(\d{3})\.")
PATH_DATE_PATTERN = re.compile(r"/(20\d{2})/(\d{2})/(\d{2})(?:/|$)")
DENIED_PARTS = {"candidates", "transport", "evaluation", "verification"}


@dataclass(frozen=True)
class Period:
    period_id: str
    start: date
    end: date
    purpose: str


@dataclass(frozen=True)
class Product:
    product_id: str
    role: str
    relative_root: str
    version: str
    official_url: str
    remote_coverage: str
    remote_access: str


PERIODS = (
    Period(
        "canada-2023-fire-season",
        date(2023, 5, 1),
        date(2023, 10, 31),
        "preferred source/GFAS and final-NAPS surface feasibility period",
    ),
    Period(
        "misr-summer-2017",
        date(2017, 6, 1),
        date(2017, 9, 30),
        "public MISR plume-height vertical feasibility period",
    ),
    Period(
        "misr-summer-2018",
        date(2018, 6, 1),
        date(2018, 9, 30),
        "public MISR plume-height vertical feasibility period",
    ),
)

PRODUCTS = (
    Product(
        "cwfis-firem3",
        "fire identity, fuel, and hotspot-level CFFDRS state",
        "nrcan/cwfis/firem3",
        "provider annual/daily archive",
        "https://cwfis.cfs.nrcan.gc.ca/downloads/hotspots/archive/",
        "public annual hotspot archives from 1994 through the last completed year",
        "public direct download",
    ),
    Product(
        "cwfis-cffdrs",
        "authoritative gridded FFMC/DMC/DC",
        "nrcan/cwfis/cffdrs",
        "CWFIS 2.0 public layers",
        "https://cwfis.cfs.nrcan.gc.ca/downloads/docs/en/references/cwfif/cwfis-data-placemat.pdf",
        "public time dimension 2024-01-01 to current",
        "public for 2024-current; provider request or reviewed reconstruction before 2024",
    ),
    Product(
        "mcd64a1-v061",
        "primary independent burned area",
        "nasa/lpdaac/mcd64a1/v061",
        "Collection 6.1",
        "https://www.earthdata.nasa.gov/s3fs-public/2025-04/MCD64_User_Guide_V61.pdf",
        "monthly global product from November 2000",
        "NASA Earthdata authentication",
    ),
    Product(
        "vnp64a1-v002",
        "prospective burned-area sensitivity and continuity",
        "nasa/lpdaac/vnp64a1/v002",
        "Version 2",
        "https://forum.earthdata.nasa.gov/viewtopic.php?t=6121",
        "monthly global product from March 2012",
        "NASA Earthdata authentication",
    ),
    Product(
        "noaa-gfs-global-1p00",
        "transport meteorology",
        "noaa/gfs/global_1p00",
        "archived GFS/GDAS family; exact homogeneous product to freeze",
        "https://www.ncei.noaa.gov/products/weather-climate-models/global-data-assimilation",
        "NCEI GDAS archive states 2001-present; exact GFS grid/cycle inventory required",
        "public NCEI archive/HAS/THREDDS",
    ),
    Product(
        "cams-gfas",
        "independent source-magnitude comparison",
        "ecmwf/cams/gfas",
        "v1.2 historical or a prospectively frozen compatible version",
        "https://confluence.ecmwf.int/pages/viewpage.action?pageId=88247878",
        "global 0.1-degree data from 2003; version boundaries must be explicit",
        "ECMWF/Copernicus account and accepted licence",
    ),
    Product(
        "misr-minx-merlin",
        "independent vertical plume observations",
        "nasa/asdc/misr/minx",
        "MISR Plume Height Project/MINX",
        "https://asdc.larc.nasa.gov/news/merlin-a-new-tool-for-misr-plume-height-project-access-and-analysis",
        "public project cohorts include 2008-2011 and summer 2017/2018",
        "public MERLIN metadata/files; additional raw processing may be manual",
    ),
    Product(
        "eccc-naps-hourly-pm25",
        "final surface PM2.5 observations",
        "eccc/naps",
        "final continuous hourly archive",
        "https://www.canada.ca/en/environment-climate-change/services/air-pollution/monitoring-networks-data/national-air-pollution-program.html",
        "continuous NAPS record extends from the 1970s to current; station/parameter years vary",
        "public NAPS data portal/query tool",
    ),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inferred_dates(path: Path) -> set[date]:
    result: set[date] = set()
    text = path.as_posix()
    for token in DATE_8_PATTERN.findall(text):
        with contextlib.suppress(ValueError):
            result.add(datetime.strptime(token, "%Y%m%d").date())
    for year, day_of_year in MODIS_DATE_PATTERN.findall(path.name):
        with contextlib.suppress(ValueError):
            result.add(date(int(year), 1, 1) + timedelta(days=int(day_of_year) - 1))
    for year, month, day in PATH_DATE_PATTERN.findall(text):
        with contextlib.suppress(ValueError):
            result.add(date(int(year), int(month), int(day)))
    return result


def assert_input_only_root(raw_root: Path, path: Path) -> None:
    resolved_raw = raw_root.resolve()
    resolved = path.resolve()
    if resolved != resolved_raw and resolved_raw not in resolved.parents:
        raise ValueError(f"inventory path escapes raw root: {resolved}")
    if DENIED_PARTS.intersection(resolved.parts):
        raise ValueError(f"inventory path crosses denied model-output tree: {resolved}")


def scan_product(raw_root: Path, product: Product, period: Period) -> dict[str, Any]:
    root = raw_root / product.relative_root
    assert_input_only_root(raw_root, root)
    all_files: list[Path] = []
    committed_files: list[Path] = []
    dated_files: list[tuple[Path, set[date]]] = []
    if root.exists():
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            all_files.append(path)
            if any(part.startswith(".") for part in path.relative_to(root).parts):
                continue
            committed_files.append(path)
            dates = inferred_dates(path)
            if dates:
                dated_files.append((path, dates))
    matching_files = [
        path
        for path, dates in dated_files
        if any(period.start <= item <= period.end for item in dates)
    ]
    matching_dates = sorted(
        {
            item
            for _path, dates in dated_files
            for item in dates
            if period.start <= item <= period.end
        }
    )
    annual_archive_complete = False
    if product.product_id == "cwfis-firem3" and period.start.year == period.end.year:
        annual_archive = root / "archive" / f"{period.start.year}_hotspots.zip"
        annual_manifest = root / "archive" / f"{period.start.year}_hotspots.manifest.json"
        if annual_archive.is_file() and annual_manifest.is_file():
            annual_archive_complete = True
            matching_files.extend([annual_archive, annual_manifest])
            matching_dates = [
                period.start + timedelta(days=offset)
                for offset in range((period.end - period.start).days + 1)
            ]
    all_dates = sorted({item for _path, dates in dated_files for item in dates})
    manifests = [
        {
            "path": path.relative_to(raw_root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in committed_files
        if path.suffix.lower() == ".json"
    ]
    if annual_archive_complete:
        local_status = "local_complete"
    elif matching_files:
        local_status = "local_partial"
        expected_dates = (period.end - period.start).days + 1
        if len(matching_dates) >= expected_dates:
            local_status = "local_complete"
    elif committed_files:
        local_status = "remote_available"
    else:
        local_status = "remote_available"
    if product.product_id == "cwfis-cffdrs" and period.end < date(2024, 1, 1):
        local_status = "manual_request_required"
    return {
        "period_id": period.period_id,
        "product_id": product.product_id,
        "role": product.role,
        "version": product.version,
        "local_root": str(root),
        "local_status": local_status,
        "local_root_exists": root.exists(),
        "local_committed_file_count": len(committed_files),
        "local_committed_bytes": sum(path.stat().st_size for path in committed_files),
        "local_staging_or_hidden_file_count": len(all_files) - len(committed_files),
        "local_period_file_count": len(matching_files),
        "local_period_unique_date_count": len(matching_dates),
        "local_period_first_date": matching_dates[0].isoformat() if matching_dates else None,
        "local_period_last_date": matching_dates[-1].isoformat() if matching_dates else None,
        "local_all_first_inferred_date": all_dates[0].isoformat() if all_dates else None,
        "local_all_last_inferred_date": all_dates[-1].isoformat() if all_dates else None,
        "local_manifest_files": manifests,
        "official_url": product.official_url,
        "remote_coverage": product.remote_coverage,
        "remote_access": product.remote_access,
        "interpretation": (
            "No committed local file with an inferred date in this period was found."
            if not matching_files
            else "Some committed local files map to this period; product-specific completeness "
            "checks are still required."
        ),
    }


def write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return sha256(path)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> str:
    columns = [
        "period_id",
        "product_id",
        "role",
        "version",
        "local_status",
        "local_root",
        "local_root_exists",
        "local_committed_file_count",
        "local_committed_bytes",
        "local_staging_or_hidden_file_count",
        "local_period_file_count",
        "local_period_unique_date_count",
        "local_period_first_date",
        "local_period_last_date",
        "local_all_first_inferred_date",
        "local_all_last_inferred_date",
        "official_url",
        "remote_coverage",
        "remote_access",
        "interpretation",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column) for column in columns})
    temporary.replace(path)
    return sha256(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    raw_root = (args.data_root / "raw").resolve()
    output = args.output_directory.resolve()
    if not raw_root.is_dir():
        raise FileNotFoundError(raw_root)
    if raw_root in output.parents or output == raw_root:
        raise ValueError("research outputs must not be written into the immutable raw tree")

    rows = [
        scan_product(raw_root, product, period)
        for period in PERIODS
        for product in PRODUCTS
    ]
    created_at = datetime.now(UTC).isoformat()
    script_path = Path(__file__).resolve()
    manifest = {
        "schema_version": 1,
        "artifact_type": "smoke-validation-input-only-period-product-inventory",
        "created_at": created_at,
        "command": [str(item) for item in sys.argv],
        "script": {"path": str(script_path), "sha256": sha256(script_path)},
        "data_root": str(args.data_root.resolve()),
        "raw_root": str(raw_root),
        "selection_firewall": {
            "allowed_root": str(raw_root),
            "denied_path_parts": sorted(DENIED_PARTS),
            "model_output_opened": False,
            "model_performance_used": False,
            "scope": "raw provider files, raw catalogues, and official discovery metadata only",
        },
        "periods": [
            {
                **asdict(period),
                "start": period.start.isoformat(),
                "end": period.end.isoformat(),
            }
            for period in PERIODS
        ],
        "products": [asdict(product) for product in PRODUCTS],
        "availability": rows,
        "limitations": [
            "Filename/path date inference is a discovery scan, not a "
            "product-specific completeness audit.",
            "remote_available means an official archive is advertised; it does not mean "
            "credentials, "
            "licence, variables, spatial coverage, or every required file have been verified.",
            "No event-level cohort has been selected by this product-level inventory.",
        ],
    }
    manifest_path = output / "inventory-manifest.json"
    csv_path = output / "period-product-availability.csv"
    periods_path = output / "candidate-periods.json"
    gaps_path = output / "access-gaps.json"
    audit_path = output / "no-output-access-audit.json"
    digests = {
        "inventory-manifest.json": write_json(manifest_path, manifest),
        "period-product-availability.csv": write_csv(csv_path, rows),
        "candidate-periods.json": write_json(
            periods_path,
            {
                "schema_version": 1,
                "created_at": created_at,
                "periods": manifest["periods"],
                "status": "catalogue_hypotheses_not_selected_cohorts",
            },
        ),
        "access-gaps.json": write_json(
            gaps_path,
            {
                "schema_version": 1,
                "created_at": created_at,
                "gaps": [
                    row
                    for row in rows
                    if row["local_status"] != "local_complete"
                ],
            },
        ),
        "no-output-access-audit.json": write_json(
            audit_path,
            {
                "schema_version": 1,
                "created_at": created_at,
                "allowed_root": str(raw_root),
                "scanned_product_roots": [
                    str(raw_root / product.relative_root) for product in PRODUCTS
                ],
                "denied_path_parts": sorted(DENIED_PARTS),
                "model_output_opened": False,
                "model_performance_used": False,
                "enforcement": (
                    "all scan roots resolved under raw root and were checked for denied parts"
                ),
            },
        ),
    }
    (output / "SHA256SUMS").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in sorted(digests.items())),
        encoding="ascii",
    )
    print(
        json.dumps(
            {
                "output_directory": str(output),
                "availability_rows": len(rows),
                "digests": digests,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
