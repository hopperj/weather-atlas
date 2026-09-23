"""Deterministic reconciliation of thermal detections into auditable fire events."""

from __future__ import annotations

import hashlib
import json
import math
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml


@dataclass(frozen=True, slots=True)
class EventMatchingConfig:
    algorithm_version: str
    maximum_time_gap_hours: float
    maximum_distance_km: float
    maximum_spread_km_per_hour: float
    compatible_fuel_prefix_length: int
    ambiguity_distance_ratio: float
    provisional: bool = True

    @classmethod
    def from_yaml(cls, path: Path) -> EventMatchingConfig:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("unsupported event-matching configuration")
        return cls(**{key: payload[key] for key in cls.__dataclass_fields__})


@dataclass(frozen=True, slots=True)
class Detection:
    detection_id: str
    observed_at: datetime
    latitude: float
    longitude: float
    fuel: str
    properties: dict[str, Any]


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical(payload: object) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _distance_km(left: Detection, right: Detection) -> float:
    radius = 6371.0088
    lat1, lat2 = math.radians(left.latitude), math.radians(right.latitude)
    dlat = lat2 - lat1
    dlon = math.radians(right.longitude - left.longitude)
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(value))


def load_detections(paths: list[Path]) -> tuple[list[Detection], list[dict[str, str]]]:
    detections: dict[str, Detection] = {}
    sources: list[dict[str, str]] = []
    for path in sorted(path.resolve() for path in paths):
        raw = path.read_bytes()
        payload = json.loads(raw)
        if payload.get("type") != "FeatureCollection":
            raise ValueError(f"not a GeoJSON FeatureCollection: {path}")
        sources.append({"name": path.name, "sha256": hashlib.sha256(raw).hexdigest()})
        for feature in payload.get("features", []):
            props = feature.get("properties", {})
            coordinates = feature.get("geometry", {}).get("coordinates", [])
            detection_id = props.get("detection_id") or feature.get("id")
            if not isinstance(detection_id, str) or len(coordinates) != 2:
                raise ValueError(f"invalid hotspot feature in {path}")
            observed = datetime.fromisoformat(props["observed_at"].replace("Z", "+00:00"))
            candidate = Detection(
                detection_id=detection_id,
                observed_at=observed.astimezone(UTC),
                latitude=float(coordinates[1]),
                longitude=float(coordinates[0]),
                fuel=str(props.get("fuel") or "UNKNOWN").upper(),
                properties=dict(props),
            )
            existing = detections.get(detection_id)
            if existing is not None and existing != candidate:
                raise ValueError(f"conflicting duplicate detection {detection_id}")
            detections[detection_id] = candidate
    return sorted(detections.values(), key=lambda item: item.detection_id), sources


def reconcile_events(detections: list[Detection], config: EventMatchingConfig) -> dict[str, Any]:
    parent = list(range(len(detections)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    # A time-windowed ECEF grid avoids an all-pairs pass for national snapshots.
    # A cell is the maximum matching envelope, so any possible match must be in
    # the same or one of the 26 adjacent cells. Indices remain tied to canonical
    # detection-id order, preserving order-independent identities.
    chronological = sorted(
        range(len(detections)),
        key=lambda index: (detections[index].observed_at, detections[index].detection_id),
    )
    maximum_envelope = config.maximum_distance_km + (
        config.maximum_time_gap_hours * config.maximum_spread_km_per_hour
    )
    cell_size = max(maximum_envelope, 0.001)
    observed_seconds = np.asarray(
        [item.observed_at.timestamp() for item in detections],
        dtype=np.float64,
    )
    latitude_radians = np.radians(
        np.asarray([item.latitude for item in detections], dtype=np.float64)
    )
    longitude_radians = np.radians(
        np.asarray([item.longitude for item in detections], dtype=np.float64)
    )
    fuel_prefixes = [
        item.fuel[: config.compatible_fuel_prefix_length]
        if config.compatible_fuel_prefix_length
        else ""
        for item in detections
    ]

    def spatial_key(index: int) -> tuple[int, int, int, str]:
        latitude = latitude_radians[index]
        longitude = longitude_radians[index]
        radius = 6371.0088
        return (
            math.floor(radius * math.cos(latitude) * math.cos(longitude) / cell_size),
            math.floor(radius * math.cos(latitude) * math.sin(longitude) / cell_size),
            math.floor(radius * math.sin(latitude) / cell_size),
            fuel_prefixes[index],
        )

    # Ambiguity reporting needs only the two nearest admissible predecessors.
    # Retaining every admissible edge can grow quadratically for dense national
    # hotspot snapshots even though the extra edges are never read after union.
    nearest_possible: dict[int, list[tuple[float, int]]] = {}
    buckets: dict[tuple[int, int, int, str], set[int]] = {}
    active: deque[tuple[float, int, tuple[int, int, int, str]]] = deque()
    for right in chronological:
        second_time = observed_seconds[right]
        while active:
            age = (second_time - active[0][0]) / 3600
            if age <= config.maximum_time_gap_hours:
                break
            _, expired, expired_key = active.popleft()
            buckets[expired_key].remove(expired)
            if not buckets[expired_key]:
                del buckets[expired_key]

        key = spatial_key(right)
        candidates: set[int] = set()
        for x_offset in (-1, 0, 1):
            for y_offset in (-1, 0, 1):
                for z_offset in (-1, 0, 1):
                    candidates.update(
                        buckets.get(
                            (
                                key[0] + x_offset,
                                key[1] + y_offset,
                                key[2] + z_offset,
                                key[3],
                            ),
                            (),
                        )
                    )
        if candidates:
            candidate_indices = np.fromiter(
                candidates,
                dtype=np.int64,
                count=len(candidates),
            )
            gaps = (second_time - observed_seconds[candidate_indices]) / 3600
            dlat = latitude_radians[right] - latitude_radians[candidate_indices]
            dlon = longitude_radians[right] - longitude_radians[candidate_indices]
            haversine = np.sin(dlat / 2) ** 2 + (
                np.cos(latitude_radians[candidate_indices])
                * math.cos(float(latitude_radians[right]))
                * np.sin(dlon / 2) ** 2
            )
            distances = 2 * 6371.0088 * np.arcsin(
                np.sqrt(np.clip(haversine, 0.0, 1.0))
            )
            envelopes = config.maximum_distance_km + (
                gaps * config.maximum_spread_km_per_hour
            )
            margins = distances - envelopes
            tolerance_km = 1e-8
            eligible_mask = margins < -tolerance_km
            for position in np.flatnonzero(np.abs(margins) <= tolerance_km):
                left = int(candidate_indices[position])
                eligible_mask[position] = (
                    _distance_km(detections[left], detections[right])
                    <= envelopes[position]
                )
            eligible_indices = candidate_indices[eligible_mask]
            if eligible_indices.size:
                # Connecting once to each existing component is graph-equivalent
                # to retaining and unioning every dense admissible edge.
                for root in sorted({find(int(left)) for left in eligible_indices}):
                    union(root, right)

                eligible_distances = distances[eligible_mask]
                order = np.lexsort((eligible_indices, eligible_distances))
                second_position = order[min(1, order.size - 1)]
                nearest_limit = (
                    float(eligible_distances[second_position]) + tolerance_km
                )
                nearest_candidates = [
                    (
                        _distance_km(detections[int(left)], detections[right]),
                        int(left),
                    )
                    for left, distance in zip(
                        eligible_indices,
                        eligible_distances,
                        strict=True,
                    )
                    if distance <= nearest_limit
                ]
                nearest_possible[right] = sorted(nearest_candidates)[:2]
        buckets.setdefault(key, set()).add(right)
        active.append((second_time, right, key))

    groups: dict[int, list[Detection]] = {}
    for index, detection in enumerate(detections):
        groups.setdefault(find(index), []).append(detection)

    events: list[dict[str, Any]] = []
    detection_index = {item.detection_id: index for index, item in enumerate(detections)}
    for members in groups.values():
        members = sorted(members, key=lambda item: item.detection_id)
        member_ids = sorted(item.detection_id for item in members)
        identity = f"{config.algorithm_version}\n" + "\n".join(member_ids)
        event_id = hashlib.sha256(identity.encode()).hexdigest()[:24]
        weights = [max(float(item.properties.get("estarea") or 0), 0.001) for item in members]
        weight_sum = sum(weights)
        warnings: list[str] = []
        for detection in members:
            candidates = nearest_possible.get(
                detection_index[detection.detection_id],
                [],
            )
            if (
                len(candidates) > 1
                and candidates[1][0] <= candidates[0][0] * config.ambiguity_distance_ratio
            ):
                warnings.append(f"ambiguous_match:{detection.detection_id}")
        if any(key not in member.properties for member in members for key in ("ffmc", "dmc", "dc")):
            warnings.append("missing_cffeps_fire_weather_codes")
        events.append(
            {
                "event_id": event_id,
                "member_detection_ids": member_ids,
                "first_observed_at": _utc_text(min(item.observed_at for item in members)),
                "last_observed_at": _utc_text(max(item.observed_at for item in members)),
                "latitude": sum(
                    item.latitude * weight for item, weight in zip(members, weights, strict=True)
                )
                / weight_sum,
                "longitude": sum(
                    item.longitude * weight for item, weight in zip(members, weights, strict=True)
                )
                / weight_sum,
                "fuel_types": sorted({item.fuel for item in members}),
                "maximum_estimated_area_ha": max(
                    float(item.properties.get("estarea") or 0) for item in members
                ),
                "detections": [
                    item.properties | {"latitude": item.latitude, "longitude": item.longitude}
                    for item in members
                ],
                "warnings": sorted(set(warnings)),
            }
        )
    events.sort(key=lambda item: item["event_id"])
    return {
        "schema_version": 1,
        "algorithm_version": config.algorithm_version,
        "configuration": {key: getattr(config, key) for key in config.__dataclass_fields__},
        "event_count": len(events),
        "detection_count": len(detections),
        "events": events,
    }


def build_event_snapshot(
    geojson_paths: list[Path], config_path: Path, output_path: Path
) -> dict[str, Any]:
    config = EventMatchingConfig.from_yaml(config_path)
    detections, sources = load_detections(geojson_paths)
    payload = reconcile_events(detections, config)
    payload["sources"] = sources
    content = _canonical(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".part")
    temporary.write_bytes(content)
    temporary.replace(output_path)
    return {
        "path": output_path.as_posix(),
        "sha256": hashlib.sha256(content).hexdigest(),
        **payload,
    }
