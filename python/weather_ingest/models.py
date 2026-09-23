"""Small immutable domain objects shared by adapters and ingestion services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RemoteRun:
    product_code: str
    domain_code: str
    initialization_time: datetime

    def __post_init__(self) -> None:
        if self.initialization_time.tzinfo is None:
            raise ValueError("initialization_time must be timezone-aware")
        object.__setattr__(self, "initialization_time", self.initialization_time.astimezone(UTC))


@dataclass(frozen=True, slots=True)
class RemoteObject:
    url: str
    filename: str
    size_bytes: int | None = None
    size_is_exact: bool = True
    last_modified: datetime | None = None
    etag: str | None = None

    def __post_init__(self) -> None:
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("remote object size must not be negative")


@dataclass(frozen=True, slots=True)
class ParsedSourceObject:
    remote: RemoteObject
    product_code: str
    producer: str
    domain_code: str
    initialization_time: datetime
    valid_time: datetime
    forecast_hour: int
    parameter: str
    source_level: str
    grid: str
    data_format: str
    time_kind: str = "forecast"
    interval_start: datetime | None = None
    interval_end: datetime | None = None
    accumulation_hours: int | None = None
    analysis_revision: str | None = None

    def __post_init__(self) -> None:
        if self.time_kind not in {"forecast", "analysis", "ensemble_analysis"}:
            raise ValueError("time_kind is not supported")
        if self.time_kind == "forecast":
            if self.interval_start is not None or self.interval_end is not None:
                raise ValueError("instant forecast objects cannot define an interval")
            return
        if self.forecast_hour != 0:
            raise ValueError("analysis objects must use a zero forecast offset")
        if self.interval_start is None or self.interval_end is None:
            raise ValueError("analysis objects require an accumulation interval")
        if self.interval_start.tzinfo is None or self.interval_end.tzinfo is None:
            raise ValueError("analysis interval timestamps must be timezone-aware")
        if self.interval_start >= self.interval_end or self.interval_end != self.valid_time:
            raise ValueError("analysis interval must end at the valid time")
        if self.accumulation_hours is None or self.accumulation_hours <= 0:
            raise ValueError("analysis objects require a positive accumulation interval")
        if self.analysis_revision is None:
            raise ValueError("analysis objects require a revision/statistic identity")


@dataclass(frozen=True, slots=True)
class ExpectedManifest:
    product_code: str
    run: RemoteRun
    expected_field_hours: frozenset[tuple[str, int]]


class InventoryDisposition(StrEnum):
    ENABLED = "enabled"
    IGNORED = "ignored"
    UNKNOWN = "unknown"
    PARSER_ERROR = "parser_error"


@dataclass(frozen=True, slots=True)
class InventoryObject:
    remote: RemoteObject
    parsed: ParsedSourceObject | None
    disposition: InventoryDisposition
    field_code: str | None
    expected_source_unit: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class DownloadResult:
    path: Path
    size_bytes: int
    sha256: str
    reused_existing: bool
