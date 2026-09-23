"""Source adapter protocol used by inventory and orchestration layers."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from weather_ingest.config import FieldConfig, ProductConfig
from weather_ingest.models import (
    ExpectedManifest,
    ParsedSourceObject,
    RemoteObject,
    RemoteRun,
)


class ProductSourceAdapter(Protocol):
    config: ProductConfig

    def list_candidate_runs(
        self, now: datetime, *, lookback_hours: int = 24
    ) -> list[RemoteRun]: ...

    def list_run_objects(
        self,
        run: RemoteRun,
        *,
        forecast_hours: tuple[int, ...] | None = None,
        use_today_alias: bool = False,
    ) -> list[RemoteObject]: ...

    def canonical_object_key(self, obj: RemoteObject) -> str: ...

    def directory_url(
        self, run: RemoteRun, forecast_hour: int, *, use_today_alias: bool = False
    ) -> str: ...

    def parse_object(
        self, obj: RemoteObject, *, expected_run: RemoteRun | None = None
    ) -> ParsedSourceObject: ...

    def expected_manifest(self, run: RemoteRun) -> ExpectedManifest: ...

    def field_for(self, parsed: ParsedSourceObject) -> FieldConfig | None: ...
