"""Frozen observation and FLEXPART operators for vertical plume validation."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np

from weather_ingest.misr_minx import MinxPlume
from weather_ingest.smoke_evaluation import EvaluationPair, calculate_metrics


@dataclass(frozen=True, slots=True)
class VerticalPlumeObservation:
    observation_id: str
    event_id: str
    overpass_id: str
    observed_at_utc: str
    product: str
    product_version: str
    primary_height_agl_m: float
    upper_height_agl_m: float
    zero_wind_height_agl_m: float | None
    valid_retrieval_points: int
    polygon: tuple[tuple[float, float], ...]
    terrain_reference: str
    qa_status: str
    role: str
    source_path: str
    source_sha256: str
    rejection_reason: str | None = None


def observation_from_minx(
    plume: MinxPlume,
    *,
    event_id: str,
    role: str,
    minimum_agl_m: float = 250.0,
) -> VerticalPlumeObservation:
    primary = plume.valid_heights_agl_m(
        field="wind_corrected",
        minimum_agl_m=minimum_agl_m,
    )
    if primary.size == 0:
        raise ValueError(f"{plume.region_name} has no eligible wind-corrected heights")
    zero_wind = plume.valid_heights_agl_m(
        field="no_wind",
        minimum_agl_m=minimum_agl_m,
    )
    return VerticalPlumeObservation(
        observation_id=f"misr-minx-{plume.region_name}",
        event_id=event_id,
        overpass_id=f"MISR-O{plume.orbit_number:06d}",
        observed_at_utc=plume.acquired_at.isoformat().replace("+00:00", "Z"),
        product="MISR MINX",
        product_version=plume.minx_version,
        primary_height_agl_m=float(np.median(primary)),
        upper_height_agl_m=float(np.quantile(primary, 0.95)),
        zero_wind_height_agl_m=(float(np.median(zero_wind)) if zero_wind.size else None),
        valid_retrieval_points=int(primary.size),
        polygon=plume.polygon,
        terrain_reference="per-retrieval MINX terrain elevation; height converted ASL to AGL",
        qa_status=plume.retrieval_quality,
        role=role,
        source_path=plume.source_path.as_posix(),
        source_sha256=plume.source_sha256,
    )


def write_observation_ledger(
    path: Path,
    observations: list[VerticalPlumeObservation],
    *,
    operator_version: str = "misr-minx-wind-corrected-median-v1",
) -> dict[str, Any]:
    identities = [item.observation_id for item in observations]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate vertical observation IDs")
    payload = {
        "schema_version": 1,
        "artifact_type": "vertical-plume-observation-ledger",
        "operator_version": operator_version,
        "observation_count": len(observations),
        "observations": [asdict(item) for item in observations],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)
    return payload


def _clip_polygon(
    polygon: list[tuple[float, float]],
    *,
    axis: int,
    boundary: float,
    keep_greater: bool,
) -> list[tuple[float, float]]:
    if not polygon:
        return []
    result: list[tuple[float, float]] = []

    def inside(point: tuple[float, float]) -> bool:
        return point[axis] >= boundary if keep_greater else point[axis] <= boundary

    def crossing(
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> tuple[float, float]:
        denominator = end[axis] - start[axis]
        fraction = 0.0 if denominator == 0 else (boundary - start[axis]) / denominator
        return (
            start[0] + fraction * (end[0] - start[0]),
            start[1] + fraction * (end[1] - start[1]),
        )

    previous = polygon[-1]
    previous_inside = inside(previous)
    for current in polygon:
        current_inside = inside(current)
        if current_inside:
            if not previous_inside:
                result.append(crossing(previous, current))
            result.append(current)
        elif previous_inside:
            result.append(crossing(previous, current))
        previous = current
        previous_inside = current_inside
    return result


def rectangle_overlap_area(
    polygon: tuple[tuple[float, float], ...],
    *,
    west: float,
    east: float,
    south: float,
    north: float,
) -> float:
    """Planar lon/lat overlap used only for relative cell-area weighting."""

    clipped = list(polygon)
    for axis, boundary, keep_greater in (
        (0, west, True),
        (0, east, False),
        (1, south, True),
        (1, north, False),
    ):
        clipped = _clip_polygon(
            clipped,
            axis=axis,
            boundary=boundary,
            keep_greater=keep_greater,
        )
    if len(clipped) < 3:
        return 0.0
    return (
        abs(
            sum(
                first[0] * second[1] - second[0] * first[1]
                for first, second in zip(clipped, clipped[1:] + clipped[:1], strict=True)
            )
        )
        / 2.0
    )


def _cell_edges(centres: np.ndarray) -> np.ndarray:
    values = np.asarray(centres, dtype=np.float64)
    if values.ndim != 1 or values.size < 2 or np.any(np.diff(values) <= 0):
        raise ValueError("model coordinates must be increasing one-dimensional arrays")
    midpoints = (values[:-1] + values[1:]) / 2.0
    return np.concatenate(
        (
            [values[0] - (midpoints[0] - values[0])],
            midpoints,
            [values[-1] + (values[-1] - midpoints[-1])],
        )
    )


def _model_times(variable: Any) -> list[datetime]:
    return [
        value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        for value in netCDF4.num2date(
            variable[:],
            units=variable.units,
            calendar=getattr(variable, "calendar", "standard"),
            only_use_cftime_datetimes=False,
            only_use_python_datetimes=True,
        )
    ]


def _temporal_weights(
    times: list[datetime],
    target: datetime,
    maximum_offset_minutes: float,
) -> list[tuple[int, float]]:
    seconds = np.asarray([(value - target).total_seconds() for value in times])
    exact = np.nonzero(seconds == 0)[0]
    if exact.size:
        return [(int(exact[0]), 1.0)]
    before = np.nonzero(seconds < 0)[0]
    after = np.nonzero(seconds > 0)[0]
    if before.size and after.size:
        left = int(before[-1])
        right = int(after[0])
        if max(abs(seconds[left]), abs(seconds[right])) <= maximum_offset_minutes * 60:
            fraction = float(-seconds[left] / (seconds[right] - seconds[left]))
            return [(left, 1.0 - fraction), (right, fraction)]
    nearest = int(np.argmin(np.abs(seconds)))
    if abs(seconds[nearest]) <= maximum_offset_minutes * 60:
        return [(nearest, 1.0)]
    return []


def sample_flexpart_vertical(
    model_path: Path,
    observation: VerticalPlumeObservation,
    *,
    maximum_time_offset_minutes: float = 90.0,
    minimum_column_weight: float = 0.0,
) -> dict[str, Any]:
    """Area/time-weight a FLEXPART aerosol profile over one frozen polygon."""

    observed_at = datetime.fromisoformat(
        observation.observed_at_utc.replace("Z", "+00:00")
    ).astimezone(UTC)
    with netCDF4.Dataset(model_path) as dataset:
        required = {"time", "longitude", "latitude", "height", "spec001_mr"}
        missing = required.difference(dataset.variables)
        if missing:
            raise ValueError(f"FLEXPART output lacks variables: {sorted(missing)}")
        longitude = np.asarray(dataset.variables["longitude"][:], dtype=np.float64)
        latitude = np.asarray(dataset.variables["latitude"][:], dtype=np.float64)
        upper = np.asarray(dataset.variables["height"][:], dtype=np.float64)
        times = _model_times(dataset.variables["time"])
        time_weights = _temporal_weights(
            times,
            observed_at,
            maximum_time_offset_minutes,
        )
        if not time_weights:
            raise ValueError("no FLEXPART output within the frozen time tolerance")
        concentration = np.asarray(
            np.ma.filled(dataset.variables["spec001_mr"][:], np.nan),
            dtype=np.float64,
        )
        while concentration.ndim > 4:
            concentration = concentration.sum(axis=0)
        if concentration.shape != (len(times), len(upper), len(latitude), len(longitude)):
            raise ValueError("unexpected FLEXPART concentration dimensions")
        interpolated = sum(concentration[index] * weight for index, weight in time_weights)
        if not np.all(np.isfinite(interpolated)) or np.any(interpolated < 0):
            raise ValueError("FLEXPART vertical field contains invalid concentrations")

        longitude_edges = _cell_edges(longitude)
        latitude_edges = _cell_edges(latitude)
        overlap = np.zeros((latitude.size, longitude.size), dtype=np.float64)
        for row in range(latitude.size):
            for column in range(longitude.size):
                overlap[row, column] = rectangle_overlap_area(
                    observation.polygon,
                    west=float(longitude_edges[column]),
                    east=float(longitude_edges[column + 1]),
                    south=float(latitude_edges[row]),
                    north=float(latitude_edges[row + 1]),
                ) * math.cos(math.radians(float(latitude[row])))
        overlap_sum = float(overlap.sum())
        if overlap_sum <= 0:
            raise ValueError("frozen plume polygon does not overlap the FLEXPART grid")
        profile = (interpolated * overlap[np.newaxis, :, :]).sum(axis=(1, 2)) / overlap_sum
        lower = np.concatenate(([0.0], upper[:-1]))
        thickness = upper - lower
        if np.any(thickness <= 0):
            raise ValueError("FLEXPART height boundaries must increase")
        layer_mass = profile * thickness
        column_weight = float(layer_mass.sum())
        if column_weight <= minimum_column_weight:
            raise ValueError("FLEXPART column is below the frozen minimum-mass rule")
        midpoints = (lower + upper) / 2.0
        mean_height = float(np.dot(layer_mass, midpoints) / column_weight)
        cumulative = np.cumsum(layer_mass) / column_weight
        top_index = min(int(np.searchsorted(cumulative, 0.95)), len(upper) - 1)
        return {
            "modelled_mean_height_agl_m": mean_height,
            "modelled_95pct_top_agl_m": float(upper[top_index]),
            "column_weight_ng_m2": column_weight,
            "layer_mass_profile_ng_m2": layer_mass.tolist(),
            "overlap_weight": overlap_sum,
            "model_times": [
                {"timestamp": times[index].isoformat(), "weight": weight}
                for index, weight in time_weights
            ],
        }


def _event_bootstrap(
    rows: list[dict[str, str]],
    *,
    observed_field: str,
    modelled_field: str,
    seed: int,
    repetitions: int,
) -> dict[str, Any]:
    if repetitions < 100:
        raise ValueError("vertical bootstrap requires at least 100 repetitions")
    event_ids = sorted({row["event_id"] for row in rows})
    if not event_ids:
        raise ValueError("vertical bootstrap has no event groups")
    by_event = {
        event_id: [row for row in rows if row["event_id"] == event_id]
        for event_id in event_ids
    }
    random = np.random.default_rng(seed)
    samples: dict[str, list[float]] = {
        "mean_bias": [],
        "root_mean_square_error": [],
        "pearson_correlation": [],
    }
    for selected_indices in random.integers(
        0,
        len(event_ids),
        size=(repetitions, len(event_ids)),
    ):
        selected = [
            row
            for index in selected_indices
            for row in by_event[event_ids[int(index)]]
        ]
        metrics = calculate_metrics(
            [
                EvaluationPair(
                    float(row[observed_field]),
                    float(row[modelled_field]),
                )
                for row in selected
            ]
        )
        for name in samples:
            value = metrics[name]
            if isinstance(value, int | float) and math.isfinite(float(value)):
                samples[name].append(float(value))
    return {
        "method": "event_block_bootstrap",
        "seed": seed,
        "repetitions": repetitions,
        "event_count": len(event_ids),
        "intervals_95pct": {
            name: {
                "lower": float(np.quantile(values, 0.025)),
                "median": float(np.quantile(values, 0.5)),
                "upper": float(np.quantile(values, 0.975)),
            }
            for name, values in samples.items()
            if values
        },
    }


def evaluate_vertical_pairs(
    path: Path,
    *,
    bootstrap_seed: int = 2026072601,
    bootstrap_repetitions: int = 2000,
) -> dict[str, Any]:
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    pairs = [EvaluationPair(float(row["observed"]), float(row["modelled"])) for row in rows]
    if not pairs:
        raise ValueError("vertical evaluation contains no pairs")
    metrics = calculate_metrics(pairs)
    upper_pairs_available = all(
        row.get("observed_upper_agl_m") and row.get("modelled_95pct_top_agl_m")
        for row in rows
    )
    upper_metrics = (
        calculate_metrics(
            [
                EvaluationPair(
                    float(row["observed_upper_agl_m"]),
                    float(row["modelled_95pct_top_agl_m"]),
                )
                for row in rows
            ]
        )
        if upper_pairs_available
        else None
    )
    criteria = {
        "pair_count": metrics["pair_count"] >= 10,
        "mean_bias": -1000.0 <= float(metrics["mean_bias"]) <= 1000.0,
        "root_mean_square_error": float(metrics["root_mean_square_error"]) <= 2000.0,
        "pearson_correlation": float(metrics["pearson_correlation"]) >= 0.40,
    }
    event_counts = Counter(row["event_id"] for row in rows)
    return {
        "schema_version": 1,
        "evaluation_kind": "vertical_plume",
        "metrics": metrics,
        "criteria": criteria,
        "criteria_passed": all(criteria.values()),
        "event_count": len(event_counts),
        "event_pair_counts": dict(sorted(event_counts.items())),
        "clustered_uncertainty": _event_bootstrap(
            rows,
            observed_field="observed",
            modelled_field="modelled",
            seed=bootstrap_seed,
            repetitions=bootstrap_repetitions,
        ),
        "upper_height_diagnostic": {
            "operator": "misr_p95_vs_flexpart_95pct_mass_top",
            "metrics": upper_metrics,
            "available_for_all_pairs": upper_pairs_available,
        },
        "pairs_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
