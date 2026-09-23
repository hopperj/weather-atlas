"""Immutable CAMS GFAS v1.2 acquisition helpers for scientific validation."""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

ADS_API_URL = "https://ads.atmosphere.copernicus.eu/api"
GFAS_DATASET_ID = "cams-global-fire-emissions-gfas"
GFAS_VERSION = "1.2"
GFAS_VARIABLES = (
    "altitude_of_plume_bottom",
    "altitude_of_plume_top",
    "injection_height",
    "wildfire_combustion_rate",
    "wildfire_flux_of_black_carbon",
    "wildfire_flux_of_carbon_monoxide",
    "wildfire_flux_of_particulate_matter_d_2_5_µm",
    "wildfire_fraction_of_area_observed",
    "wildfire_radiative_power",
)
GFAS_SHORT_NAMES = frozenset(
    {
        "apb",
        "apt",
        "injh",
        "crfire",
        "bcfire",
        "cofire",
        "pm2p5fire",
        "offire",
        "frpfire",
    }
)
GFAS_FLUX_SHORT_NAMES = frozenset({"crfire", "bcfire", "cofire", "pm2p5fire"})


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


def load_dotenv_value(path: Path, name: str) -> str | None:
    """Read one simple dotenv key without modifying or exposing other secrets."""
    if not path.is_file():
        return None
    matches: list[str] = []
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
        matches.append(value)
    if len(matches) > 1:
        raise ValueError(f"{name} occurs more than once in {path}")
    return matches[0] if matches else None


def parse_iso_dates(values: Iterable[str]) -> list[date]:
    dates = sorted({date.fromisoformat(str(value)) for value in values})
    if not dates:
        raise ValueError("the GFAS acquisition date set is empty")
    return dates


def split_contiguous_ranges(
    dates: Sequence[date],
    *,
    maximum_days: int = 7,
) -> list[tuple[date, date]]:
    """Group sorted unique dates without retrieving intervening unrequested days."""
    if maximum_days < 1:
        raise ValueError("maximum_days must be positive")
    unique_dates = sorted(set(dates))
    if not unique_dates:
        return []
    ranges: list[tuple[date, date]] = []
    start = unique_dates[0]
    previous = unique_dates[0]
    for current in unique_dates[1:]:
        contiguous = current == previous + timedelta(days=1)
        within_limit = (current - start).days + 1 <= maximum_days
        if not contiguous or not within_limit:
            ranges.append((start, previous))
            start = current
        previous = current
    ranges.append((start, previous))
    return ranges


def dates_inclusive(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("end precedes start")
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def request_payload(start: date, end: date) -> dict[str, Any]:
    return {
        "variable": list(GFAS_VARIABLES),
        "date": f"{start.isoformat()}/{end.isoformat()}",
        "data_format": "grib",
    }


def request_filename(start: date, end: date) -> str:
    return f"cams-gfas-v1.2-daily-{start.isoformat()}_{end.isoformat()}.grib"


def _metadata_rows(
    path: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> list[dict[str, Any]]:
    output = runner(
        [
            "grib_get",
            "-p",
            (
                "edition,centre,gridType,Ni,Nj,typeOfLevel,level,dataDate,dataTime,"
                "stepRange,shortName,paramId,units"
            ),
            path.as_posix(),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=900,
    ).stdout
    rows: list[dict[str, Any]] = []
    for message_number, line in enumerate(output.splitlines(), start=1):
        fields = line.split(maxsplit=12)
        if len(fields) != 13:
            raise ValueError(f"invalid GFAS GRIB metadata on message {message_number}")
        rows.append(
            {
                "edition": int(fields[0]),
                "centre": fields[1],
                "grid_type": fields[2],
                "ni": int(fields[3]),
                "nj": int(fields[4]),
                "level_type": fields[5],
                "level": int(fields[6]),
                "date": datetime.strptime(fields[7], "%Y%m%d").date(),
                "time": int(fields[8]),
                "step": fields[9],
                "short_name": fields[10],
                "parameter_id": int(fields[11]),
                "units": fields[12],
            }
        )
    if not rows:
        raise ValueError("GFAS GRIB contains no messages")
    return rows


def _value_statistics(
    path: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, dict[str, float | int]]:
    output = runner(
        [
            "grib_get",
            "-p",
            "shortName,numberOfDataPoints,numberOfMissing,minimum,maximum,average",
            path.as_posix(),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=1800,
    ).stdout
    statistics: dict[str, dict[str, float | int]] = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) != 6 or fields[0] not in GFAS_SHORT_NAMES:
            continue
        short_name = fields[0]
        points = int(fields[1])
        missing = int(fields[2])
        minimum, maximum, average = map(float, fields[3:])
        if points <= 0 or missing < 0 or missing > points:
            raise ValueError(f"invalid GFAS point counts for {short_name}")
        if not all(math.isfinite(value) for value in (minimum, maximum, average)):
            raise ValueError(f"non-finite GFAS statistics for {short_name}")
        if short_name in GFAS_FLUX_SHORT_NAMES | {"offire", "frpfire"} and minimum < 0:
            raise ValueError(f"negative GFAS emission/observation field for {short_name}")
        aggregate = statistics.setdefault(
            short_name,
            {
                "message_count": 0,
                "point_count": 0,
                "missing_value_count": 0,
                "minimum": minimum,
                "maximum": maximum,
                "sum_of_message_means": 0.0,
            },
        )
        aggregate["message_count"] = int(aggregate["message_count"]) + 1
        aggregate["point_count"] = int(aggregate["point_count"]) + points
        aggregate["missing_value_count"] = int(aggregate["missing_value_count"]) + missing
        aggregate["minimum"] = min(float(aggregate["minimum"]), minimum)
        aggregate["maximum"] = max(float(aggregate["maximum"]), maximum)
        aggregate["sum_of_message_means"] = float(aggregate["sum_of_message_means"]) + average
    for values in statistics.values():
        count = int(values["message_count"])
        values["mean_of_message_means"] = float(values.pop("sum_of_message_means")) / count
    return statistics


def validate_gfas_grib(
    path: Path,
    expected_dates: Sequence[date],
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
        raise FileNotFoundError(f"GFAS output is not a non-empty regular file: {path}")
    expected = set(expected_dates)
    rows = _metadata_rows(path, runner=runner)
    seen: set[tuple[date, str]] = set()
    definitions: dict[str, dict[str, Any]] = {}
    counts_by_date = {day: 0 for day in expected}
    for row in rows:
        if row["date"] not in expected:
            raise ValueError(f"GFAS message date is outside the request: {row['date']}")
        identity = (
            row["edition"],
            row["centre"],
            row["grid_type"],
            row["ni"],
            row["nj"],
            row["level_type"],
            row["level"],
            row["time"],
            row["step"],
        )
        if identity != (1, "ecmf", "regular_ll", 3600, 1800, "surface", 0, 0, "0-24"):
            raise ValueError(f"unexpected GFAS message identity: {identity}")
        short_name = str(row["short_name"])
        if short_name not in GFAS_SHORT_NAMES:
            raise ValueError(f"unexpected GFAS parameter: {short_name}")
        pair = (row["date"], short_name)
        if pair in seen:
            raise ValueError(f"duplicate GFAS date/parameter message: {pair}")
        seen.add(pair)
        counts_by_date[row["date"]] += 1
        definition = {
            "parameter_id": row["parameter_id"],
            "units": row["units"],
        }
        if short_name in definitions and definitions[short_name] != definition:
            raise ValueError(f"inconsistent GFAS parameter definition: {short_name}")
        definitions[short_name] = definition

    missing_dates = sorted(day.isoformat() for day, count in counts_by_date.items() if count == 0)
    if missing_dates:
        raise ValueError(f"GFAS request lacks dates: {missing_dates}")
    missing_pairs = sorted(
        f"{day.isoformat()}:{short_name}"
        for day in expected
        for short_name in GFAS_SHORT_NAMES
        if (day, short_name) not in seen
    )
    if missing_pairs:
        raise ValueError(f"GFAS request lacks date/parameter pairs: {missing_pairs[:10]}")

    statistics = _value_statistics(path, runner=runner)
    if set(statistics) != GFAS_SHORT_NAMES:
        raise ValueError("GFAS statistics do not cover the complete required parameter set")
    for short_name, values in statistics.items():
        if int(values["message_count"]) != len(expected):
            raise ValueError(f"incomplete GFAS statistics for {short_name}")
        if int(values["missing_value_count"]) != 0:
            raise ValueError(f"GFAS contains missing values for {short_name}")

    return {
        "message_count": len(rows),
        "date_count": len(expected),
        "dates": sorted(day.isoformat() for day in expected),
        "parameters": dict(sorted(definitions.items())),
        "value_statistics": dict(sorted(statistics.items())),
        "grid": {
            "type": "regular_ll",
            "dimensions": [3600, 1800],
            "resolution_degrees": 0.1,
            "level_type": "surface",
        },
    }


def build_archive_manifest(
    *,
    cohort_id: str,
    ledger_path: Path,
    dates: Sequence[date],
    records: Sequence[dict[str, Any]],
    request_maximum_days: int,
) -> dict[str, Any]:
    covered = sorted(
        {date.fromisoformat(day) for record in records for day in record["validation"]["dates"]}
    )
    if covered != sorted(set(dates)):
        raise ValueError("GFAS archive records do not exactly cover the frozen date set")
    return {
        "artifact_type": "cams-gfas-v1.2-ads-validation-archive",
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "complete",
        "cohort_id": cohort_id,
        "dataset": {
            "id": GFAS_DATASET_ID,
            "version": GFAS_VERSION,
            "api_url": ADS_API_URL,
            "data_type": "analysis",
            "temporal_resolution": "daily_24_hour_average",
            "format": "GRIB1",
            "license": "CC-BY-4.0",
            "variables": list(GFAS_VARIABLES),
            "required_short_names": sorted(GFAS_SHORT_NAMES),
        },
        "selection_firewall": {
            "date_source": ledger_path.resolve().as_posix(),
            "date_source_sha256": sha256(ledger_path),
            "candidate_output_accessed": False,
            "gfas_magnitudes_used_for_event_selection": False,
            "request_maximum_days": request_maximum_days,
        },
        "coverage": {
            "date_count": len(covered),
            "dates": [day.isoformat() for day in covered],
        },
        "files": list(records),
        "secret_handling": {
            "token_environment_variable": "ADS_PERSONAL_ACCESS_TOKEN",
            "token_recorded": False,
        },
    }
