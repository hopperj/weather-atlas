"""Input-only sparse event support on the CAMS GFAS 0.1-degree grid."""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np

GFAS_NI = 3600
GFAS_NJ = 1800
GFAS_SPACING_DEGREES = 0.1


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


def gfas_cell(longitude: float, latitude: float) -> tuple[int, int]:
    if not -90 <= latitude <= 90:
        raise ValueError("latitude lies outside the GFAS grid")
    normalized_longitude = ((longitude + 180.0) % 360.0) - 180.0
    column = min(
        GFAS_NI - 1,
        max(0, int(np.floor((normalized_longitude + 180.0) / GFAS_SPACING_DEGREES))),
    )
    row = min(
        GFAS_NJ - 1,
        max(0, int(np.floor((90.0 - latitude) / GFAS_SPACING_DEGREES))),
    )
    return row, column


def _role_events(ledger: dict[str, Any]) -> dict[str, str]:
    return {
        str(event["event_id"]): str(event["role"])
        for event in [*ledger["retained_events"], *ledger["reserve_events"]]
    }


def build_support_records(
    *,
    area_report: dict[str, Any],
    source_ledger: dict[str, Any],
    dilation_cells: int = 1,
) -> dict[str, Any]:
    if dilation_cells != 1:
        raise ValueError("the frozen W2 uncertainty dilation is exactly one GFAS cell")
    roles = _role_events(source_ledger)
    by_cell_day: dict[tuple[str, int, int], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    occurrence_count = 0
    for event in area_report["events"]:
        event_id = str(event["event_id"])
        if event_id not in roles:
            continue
        occurrences = event.get("support_occurrences")
        if not isinstance(occurrences, list):
            raise ValueError(f"event lacks input-only support occurrences: {event_id}")
        for occurrence in occurrences:
            day = str(occurrence["burn_date"])
            if day not in event["daily_area"]["central_daily_increment_ha"]:
                raise ValueError(f"support occurrence lies outside the area curve: {event_id}")
            row, column = gfas_cell(
                float(occurrence["longitude"]),
                float(occurrence["latitude"]),
            )
            by_cell_day[(day, row, column)][event_id] += 1
            occurrence_count += 1

    ambiguous = {key: claims for key, claims in by_cell_day.items() if len(claims) > 1}
    ambiguous_exact = [
        {
            "date": day,
            "row": row,
            "column": column,
            "event_ids": sorted(claims),
            "mcd64a1_occurrence_count": sum(claims.values()),
            "support_role": "ambiguous",
        }
        for (day, row, column), claims in sorted(ambiguous.items())
    ]
    exact = []
    for (day, row, column), claims in sorted(by_cell_day.items()):
        if len(claims) > 1:
            continue
        event_id, pixel_count = next(iter(claims.items()))
        exact.append(
            {
                "date": day,
                "row": row,
                "column": column,
                "event_id": event_id,
                "event_role": roles[event_id],
                "mcd64a1_occurrence_count": pixel_count,
                "support_role": "exact",
            }
        )

    dilated_claims: dict[tuple[str, int, int], set[str]] = defaultdict(set)
    exact_lookup = {(record["date"], record["row"], record["column"]): record for record in exact}
    for record in exact:
        for row_offset in (-1, 0, 1):
            for column_offset in (-1, 0, 1):
                row = record["row"] + row_offset
                column = (record["column"] + column_offset) % GFAS_NI
                if 0 <= row < GFAS_NJ:
                    dilated_claims[(record["date"], row, column)].add(record["event_id"])
    dilated = []
    dilated_ambiguous = 0
    for (day, row, column), event_ids in sorted(dilated_claims.items()):
        if len(event_ids) > 1:
            dilated_ambiguous += 1
            continue
        event_id = next(iter(event_ids))
        exact_record = exact_lookup.get((day, row, column))
        dilated.append(
            {
                "date": day,
                "row": row,
                "column": column,
                "event_id": event_id,
                "event_role": roles[event_id],
                "mcd64a1_occurrence_count": (
                    int(exact_record["mcd64a1_occurrence_count"]) if exact_record is not None else 0
                ),
                "support_role": "exact" if exact_record is not None else "dilated",
            }
        )

    return {
        "schema_version": 1,
        "grid": {
            "type": "regular_ll",
            "dimensions": [GFAS_NI, GFAS_NJ],
            "spacing_degrees": GFAS_SPACING_DEGREES,
            "longitude_extent": [-180.0, 180.0],
            "latitude_extent": [-90.0, 90.0],
        },
        "ambiguity_policy": "exclude_claimed_cell_day_from_all_events",
        "dilation": {
            "cells": dilation_cells,
            "topology": "chebyshev_3_by_3",
            "longitude_wrap": True,
            "latitude_clip": True,
        },
        "input_occurrence_count": occurrence_count,
        "exact_record_count": len(exact),
        "ambiguous_exact_cell_day_count": len(ambiguous),
        "dilated_record_count": len(dilated),
        "ambiguous_dilated_cell_day_count": dilated_ambiguous,
        "event_exact_counts": dict(sorted(Counter(record["event_id"] for record in exact).items())),
        "exact": exact,
        "dilated": dilated,
        "ambiguous_exact": ambiguous_exact,
    }


def write_sparse_support_netcdf(path: Path, support: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.unlink(missing_ok=True)
    event_ids = sorted(
        {str(record["event_id"]) for role in ("exact", "dilated") for record in support[role]}
    )
    event_index = {event_id: index for index, event_id in enumerate(event_ids)}
    dates = sorted(
        {
            str(record["date"])
            for role in ("exact", "dilated", "ambiguous_exact")
            for record in support[role]
        }
    )
    date_index = {day: index for index, day in enumerate(dates)}
    records = [
        (0 if role == "exact" else 1, record)
        for role in ("exact", "dilated")
        for record in support[role]
    ]
    records.extend((2, record) for record in support["ambiguous_exact"])
    try:
        with netCDF4.Dataset(temporary, "w", format="NETCDF4") as dataset:
            dataset.createDimension("support_record", len(records))
            dataset.createDimension("event", len(event_ids))
            dataset.createDimension("date", len(dates))
            dataset.setncattr("artifact_type", "w2_sparse_gfas_event_support")
            dataset.setncattr("schema_version", 1)
            dataset.setncattr("ambiguity_policy", support["ambiguity_policy"])
            dataset.setncattr("dilation_cells", support["dilation"]["cells"])
            dataset.createVariable("event_id", str, ("event",))[:] = np.asarray(
                event_ids,
                dtype=object,
            )
            dataset.createVariable("date", str, ("date",))[:] = np.asarray(
                dates,
                dtype=object,
            )
            arrays = {
                "support_set": np.asarray([role for role, _ in records], dtype=np.int8),
                "date_index": np.asarray(
                    [date_index[str(record["date"])] for _, record in records],
                    dtype=np.int16,
                ),
                "event_index": np.asarray(
                    [
                        event_index[str(record["event_id"])] if "event_id" in record else -1
                        for _, record in records
                    ],
                    dtype=np.int16,
                ),
                "row": np.asarray(
                    [int(record["row"]) for _, record in records],
                    dtype=np.int16,
                ),
                "column": np.asarray(
                    [int(record["column"]) for _, record in records],
                    dtype=np.int16,
                ),
                "mcd64a1_occurrence_count": np.asarray(
                    [int(record["mcd64a1_occurrence_count"]) for _, record in records],
                    dtype=np.int32,
                ),
                "support_role": np.asarray(
                    [
                        (
                            0
                            if str(record["support_role"]) == "exact"
                            else 1
                            if str(record["support_role"]) == "dilated"
                            else 2
                        )
                        for _, record in records
                    ],
                    dtype=np.int8,
                ),
            }
            for name, values in arrays.items():
                variable = dataset.createVariable(
                    name,
                    values.dtype,
                    ("support_record",),
                    zlib=True,
                    complevel=4,
                )
                variable[:] = values
            dataset.variables["support_set"].setncattr(
                "flag_meanings",
                "exact_set dilated_set ambiguous_exact_set",
            )
            dataset.variables["support_role"].setncattr(
                "flag_meanings",
                "exact_cell dilation_only_cell ambiguous_cell",
            )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "path": path.resolve().as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
        "support_record_count": len(records),
        "event_count": len(event_ids),
        "date_count": len(dates),
    }


def build_support_manifest(
    *,
    support: dict[str, Any],
    output: dict[str, Any],
    sources: dict[str, Path],
    command: list[str],
) -> dict[str, Any]:
    return {
        "artifact_type": "w2-gfas-event-support-manifest",
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "frozen_input_only",
        "selection_firewall": {
            "candidate_output_path_accepted": False,
            "candidate_output_accessed": False,
            "gfas_emission_values_accessed": False,
            "support_inputs": "frozen events and independently assigned MCD64A1 occurrences",
        },
        "sources": {
            name: {
                "path": path.resolve().as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for name, path in sorted(sources.items())
        },
        "operator": {
            "grid": support["grid"],
            "ambiguity_policy": support["ambiguity_policy"],
            "dilation": support["dilation"],
        },
        "counts": {
            key: value
            for key, value in support.items()
            if key.endswith("_count") or key == "event_exact_counts"
        },
        "output": output,
        "command": command,
    }
