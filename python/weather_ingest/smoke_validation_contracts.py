"""Shared immutable records and dependence-aware statistics for smoke validation."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from weather_ingest.smoke_evaluation import EvaluationPair, calculate_metrics


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


@dataclass(frozen=True, slots=True)
class SourceArtifact:
    path: str
    sha256: str
    size_bytes: int
    provider: str
    product: str
    version: str

    @classmethod
    def from_path(
        cls,
        path: Path,
        *,
        provider: str,
        product: str,
        version: str,
    ) -> SourceArtifact:
        resolved = path.expanduser().resolve()
        if not resolved.is_file() or resolved.is_symlink():
            raise FileNotFoundError(resolved)
        return cls(
            path=resolved.as_posix(),
            sha256=sha256(resolved),
            size_bytes=resolved.stat().st_size,
            provider=provider,
            product=product,
            version=version,
        )

    def verify(self) -> Path:
        path = Path(self.path).expanduser().resolve()
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(path)
        if path.stat().st_size != self.size_bytes or sha256(path) != self.sha256:
            raise ValueError(f"source artifact changed: {path}")
        return path


@dataclass(frozen=True, slots=True)
class ObservationRecord:
    observation_id: str
    observation_kind: str
    event_id: str
    observed_at_utc: str
    units: str
    source: SourceArtifact
    acceptance_role: str
    geometry: Mapping[str, Any] | None = None
    qa_flags: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    rejection_reason: str | None = None

    def validate(self) -> None:
        if not self.observation_id or not self.event_id:
            raise ValueError("observation and event identifiers are required")
        timestamp = datetime.fromisoformat(self.observed_at_utc.replace("Z", "+00:00"))
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("observation timestamp must be timezone-aware")
        if not self.units or self.acceptance_role not in {
            "primary",
            "sensitivity",
            "diagnostic",
        }:
            raise ValueError("invalid observation units or acceptance role")
        if self.rejection_reason is not None and self.acceptance_role == "primary":
            raise ValueError("a rejected observation cannot retain a primary role")


@dataclass(frozen=True, slots=True)
class PairRecord:
    pair_id: str
    observed: float
    modelled: float
    units: str
    event_id: str
    role: str
    observation_id: str | None = None
    station_id: str | None = None
    time_utc: str | None = None
    species: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.pair_id or not self.event_id:
            raise ValueError("pair and event identifiers are required")
        if not math.isfinite(self.observed) or not math.isfinite(self.modelled):
            raise ValueError("pair values must be finite")
        if self.role not in {"primary", "sensitivity", "diagnostic"}:
            raise ValueError("invalid pair role")
        if self.time_utc is not None:
            timestamp = datetime.fromisoformat(self.time_utc.replace("Z", "+00:00"))
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("pair timestamp must be timezone-aware")

    def evaluation_pair(self) -> EvaluationPair:
        return EvaluationPair(observed=self.observed, modelled=self.modelled)


@dataclass(slots=True)
class RejectionLedger:
    input_count: int = 0
    retained_ids: list[str] = field(default_factory=list)
    rejected: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))

    def retain(self, record_id: str) -> None:
        self.input_count += 1
        self.retained_ids.append(record_id)

    def reject(self, record_id: str, reason: str) -> None:
        if not reason or reason.lower() == "other":
            raise ValueError("a stable, specific rejection reason is required")
        self.input_count += 1
        self.rejected.setdefault(reason, []).append(record_id)

    def report(self) -> dict[str, Any]:
        rejected_count = sum(len(values) for values in self.rejected.values())
        retained_count = len(self.retained_ids)
        if retained_count + rejected_count != self.input_count:
            raise ValueError("rejection ledger does not reconcile")
        return {
            "schema_version": 1,
            "input_count": self.input_count,
            "retained_count": retained_count,
            "rejected_count": rejected_count,
            "rejection_counts": dict(
                sorted((reason, len(values)) for reason, values in self.rejected.items())
            ),
            "retained_ids": list(self.retained_ids),
            "rejections": {
                reason: list(values) for reason, values in sorted(self.rejected.items())
            },
            "reconciled": True,
        }


PAIR_FIELDS = (
    "pair_id",
    "observed",
    "modelled",
    "units",
    "event_id",
    "role",
    "observation_id",
    "station_id",
    "time_utc",
    "species",
    "metadata_json",
)


def write_pair_records(path: Path, pairs: Sequence[PairRecord]) -> dict[str, Any]:
    if not pairs:
        raise ValueError("at least one pair is required")
    identifiers: set[str] = set()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        with temporary.open("x", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=PAIR_FIELDS)
            writer.writeheader()
            for pair in pairs:
                pair.validate()
                if pair.pair_id in identifiers:
                    raise ValueError(f"duplicate pair identifier: {pair.pair_id}")
                identifiers.add(pair.pair_id)
                row = asdict(pair)
                metadata = row.pop("metadata")
                row["metadata_json"] = json.dumps(
                    metadata,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                writer.writerow(row)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "path": path.resolve().as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
        "pair_count": len(pairs),
        "event_count": len({pair.event_id for pair in pairs}),
        "station_count": len({pair.station_id for pair in pairs if pair.station_id}),
        "role_counts": dict(sorted(Counter(pair.role for pair in pairs).items())),
    }


def write_observation_ledger(
    path: Path,
    records: Sequence[ObservationRecord],
    *,
    selection_firewall: Mapping[str, Any],
) -> dict[str, Any]:
    if not records:
        raise ValueError("at least one observation record is required")
    identifiers: set[str] = set()
    serialized = []
    for record in records:
        record.validate()
        record.source.verify()
        if record.observation_id in identifiers:
            raise ValueError(f"duplicate observation identifier: {record.observation_id}")
        identifiers.add(record.observation_id)
        serialized.append(asdict(record))
    payload = {
        "artifact_type": "smoke-validation-observation-ledger",
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "selection_firewall": dict(selection_firewall),
        "record_count": len(serialized),
        "records": serialized,
    }
    atomic_json(path, payload)
    return {
        "path": path.resolve().as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
        "record_count": len(serialized),
    }


def build_pair_manifest(
    *,
    pair_path: Path,
    sources: Sequence[SourceArtifact],
    candidate_manifest: Path,
    operator: Mapping[str, Any],
    rejection_report: Mapping[str, Any],
    command: Sequence[str],
) -> dict[str, Any]:
    for source in sources:
        source.verify()
    if rejection_report.get("reconciled") is not True:
        raise ValueError("pair manifest requires a reconciled rejection ledger")
    return {
        "artifact_type": "smoke-validation-pair-manifest",
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "pairs": {
            "path": pair_path.resolve().as_posix(),
            "size_bytes": pair_path.stat().st_size,
            "sha256": sha256(pair_path),
        },
        "sources": [asdict(source) for source in sources],
        "candidate_manifest": {
            "path": candidate_manifest.resolve().as_posix(),
            "size_bytes": candidate_manifest.stat().st_size,
            "sha256": sha256(candidate_manifest),
        },
        "operator": dict(operator),
        "rejections": dict(rejection_report),
        "command": list(command),
    }


def clustered_bootstrap_metrics(
    pairs: Sequence[PairRecord],
    *,
    replicates: int,
    seed: int,
    nested_station_resampling: bool = False,
) -> dict[str, Any]:
    if replicates < 100:
        raise ValueError("at least 100 bootstrap replicates are required")
    primary = [pair for pair in pairs if pair.role == "primary"]
    if not primary:
        raise ValueError("no primary pairs are available")
    by_event: dict[str, list[PairRecord]] = defaultdict(list)
    for pair in primary:
        by_event[pair.event_id].append(pair)
    event_ids = sorted(by_event)
    rng = np.random.default_rng(seed)
    samples: dict[str, list[float]] = defaultdict(list)
    for _ in range(replicates):
        selected: list[PairRecord] = []
        for event_index in rng.integers(0, len(event_ids), size=len(event_ids)):
            event_pairs = by_event[event_ids[int(event_index)]]
            if not nested_station_resampling:
                selected.extend(event_pairs)
                continue
            by_station: dict[str, list[PairRecord]] = defaultdict(list)
            for pair in event_pairs:
                by_station[pair.station_id or "__missing_station__"].append(pair)
            station_ids = sorted(by_station)
            for station_index in rng.integers(
                0,
                len(station_ids),
                size=len(station_ids),
            ):
                selected.extend(by_station[station_ids[int(station_index)]])
        metrics = calculate_metrics([pair.evaluation_pair() for pair in selected])
        for name, value in metrics.items():
            if isinstance(value, int | float) and value is not None and math.isfinite(value):
                samples[name].append(float(value))
    intervals = {
        name: {
            "lower_2_5": float(np.percentile(values, 2.5)),
            "median": float(np.percentile(values, 50)),
            "upper_97_5": float(np.percentile(values, 97.5)),
        }
        for name, values in sorted(samples.items())
        if values
    }
    return {
        "schema_version": 1,
        "method": (
            "event_then_station_cluster_bootstrap"
            if nested_station_resampling
            else "event_cluster_bootstrap"
        ),
        "replicates": replicates,
        "seed": seed,
        "event_count": len(event_ids),
        "pair_count": len(primary),
        "intervals": intervals,
    }
