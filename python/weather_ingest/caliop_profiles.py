"""Source-neutral CALIOP smoke-layer records for secondary W3 matchups."""

from __future__ import annotations

import csv
import hashlib
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CaliopSmokeLayer:
    profile_id: str
    event_id: str
    observed_at_utc: datetime
    latitude: float
    longitude: float
    base_agl_m: float
    top_agl_m: float
    feature_type: str
    subtype: str
    horizontal_averaging_km: float
    qa_status: str
    source_path: str
    source_sha256: str

    @property
    def midpoint_agl_m(self) -> float:
        return (self.base_agl_m + self.top_agl_m) / 2.0


def read_caliop_layer_csv(path: Path) -> list[CaliopSmokeLayer]:
    """Read a frozen analyst-exported CALIOP layer table.

    Native CALIOP product extraction is intentionally separate from the matchup
    operator so an observation analyst can complete and review smoke typing
    without seeing FLEXPART output.
    """

    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    required = {
        "profile_id",
        "event_id",
        "observed_at_utc",
        "latitude",
        "longitude",
        "base_agl_m",
        "top_agl_m",
        "feature_type",
        "subtype",
        "horizontal_averaging_km",
        "qa_status",
    }
    records = []
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("CALIOP layer table lacks frozen contract fields")
        for row in reader:
            timestamp = datetime.fromisoformat(
                row["observed_at_utc"].replace("Z", "+00:00")
            ).astimezone(UTC)
            values = [
                float(row[name])
                for name in (
                    "latitude",
                    "longitude",
                    "base_agl_m",
                    "top_agl_m",
                    "horizontal_averaging_km",
                )
            ]
            if not all(math.isfinite(value) for value in values):
                raise ValueError(f"CALIOP profile contains non-finite values: {row['profile_id']}")
            if values[2] < 0 or values[3] <= values[2]:
                raise ValueError(f"CALIOP layer geometry is invalid: {row['profile_id']}")
            records.append(
                CaliopSmokeLayer(
                    profile_id=row["profile_id"],
                    event_id=row["event_id"],
                    observed_at_utc=timestamp,
                    latitude=values[0],
                    longitude=values[1],
                    base_agl_m=values[2],
                    top_agl_m=values[3],
                    feature_type=row["feature_type"],
                    subtype=row["subtype"],
                    horizontal_averaging_km=values[4],
                    qa_status=row["qa_status"],
                    source_path=path.resolve().as_posix(),
                    source_sha256=checksum,
                )
            )
    identities = [record.profile_id for record in records]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate CALIOP profile IDs")
    return records
