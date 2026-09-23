"""Shared ECCC behavior for deterministic and ensemble precipitation analyses."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin

from weather_ingest.config import FieldConfig, ProductConfig
from weather_ingest.http_listing import ListingSource, parse_directory_listing
from weather_ingest.models import ExpectedManifest, ParsedSourceObject, RemoteObject, RemoteRun

_FILENAME_RE = re.compile(
    r"^(?P<date>\d{8})T(?P<hour>\d{2})Z_MSC_"
    r"(?P<producer>[A-Za-z0-9.-]+)_"
    r"(?P<parameter>.+)_(?P<level>[^_]+)_"
    r"(?P<grid>[^_]+)_PT0H\.(?P<format>grib2|nc)$"
)
_ACCUMULATION_RE = re.compile(r"Accum(?P<hours>\d{1,2})h(?:-(?P<stat>Pct25|Pct75))?$")


class EcccAnalysisAdapter:
    """Interpret PT0H files whose timestamp is an accumulation valid/end time."""

    product_code: str
    product_kind: str

    def __init__(self, config: ProductConfig, listing_source: ListingSource) -> None:
        if config.code != self.product_code or config.adapter != self.product_code:
            raise ValueError(
                f"{type(self).__name__} requires the {self.product_code} product configuration"
            )
        if config.kind != self.product_kind or len(config.domains) != 1:
            raise ValueError(
                f"{self.product_code.upper()} requires one {self.product_kind} domain"
            )
        if config.analysis_timing is None:
            raise ValueError("analysis timing configuration is required")
        self.config = config
        self.listing_source = listing_source
        self.domain_code = config.domains[0].code

    def list_candidate_runs(
        self, now: datetime, *, lookback_hours: int = 24
    ) -> list[RemoteRun]:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        if lookback_hours < 0:
            raise ValueError("lookback_hours must not be negative")
        now = now.astimezone(UTC)
        cutoff = now - timedelta(hours=lookback_hours)
        runs: list[RemoteRun] = []
        day = cutoff.replace(hour=0, minute=0, second=0, microsecond=0)
        while day <= now:
            for valid_hour in self.config.run_hours_utc:
                valid_time = day.replace(hour=valid_hour)
                if cutoff <= valid_time <= now:
                    runs.append(RemoteRun(self.product_code, self.domain_code, valid_time))
            day += timedelta(days=1)
        return sorted(runs, key=lambda run: run.initialization_time, reverse=True)

    def directory_url(
        self, run: RemoteRun, forecast_hour: int = 0, *, use_today_alias: bool = False
    ) -> str:
        self._validate_run(run)
        if forecast_hour != 0:
            raise ValueError("analysis products do not have forecast lead hours")
        domain = self.config.domain(run.domain_code)
        values = {
            "resolution": domain.resolution,
            "run_hour": f"{run.initialization_time.hour:02d}",
            "run_date": run.initialization_time.strftime("%Y%m%d"),
        }
        template = (
            self.config.discovery.today_path
            if use_today_alias
            else self.config.discovery.archive_path
        )
        return urljoin(self.config.discovery.base_url.rstrip("/") + "/", template.format(**values))

    def list_run_objects(
        self,
        run: RemoteRun,
        *,
        forecast_hours: tuple[int, ...] | None = None,
        use_today_alias: bool = False,
    ) -> list[RemoteObject]:
        offsets = forecast_hours or (0,)
        if tuple(sorted(set(offsets))) != (0,):
            raise ValueError("analysis inventory accepts only the zero time offset")
        directory_url = self.directory_url(run, use_today_alias=use_today_alias)
        return parse_directory_listing(directory_url, self.listing_source.get_text(directory_url))

    def parse_object(
        self, obj: RemoteObject, *, expected_run: RemoteRun | None = None
    ) -> ParsedSourceObject:
        match = _FILENAME_RE.fullmatch(obj.filename)
        if not match:
            raise ValueError(
                f"unrecognized {self.product_code.upper()} analysis filename: {obj.filename}"
            )
        producer = match.group("producer")
        if producer not in self.config.source_producers:
            raise ValueError(f"unexpected {self.product_code.upper()} producer {producer!r}")
        data_format = match.group("format")
        if data_format not in self.config.source_formats:
            raise ValueError(f"unexpected {self.product_code.upper()} format {data_format!r}")
        valid_time = datetime.strptime(
            match.group("date") + match.group("hour"), "%Y%m%d%H"
        ).replace(tzinfo=UTC)
        accumulation_match = _ACCUMULATION_RE.search(match.group("parameter"))
        if not accumulation_match:
            raise ValueError("analysis parameter does not identify an accumulation interval")
        accumulation_hours = int(accumulation_match.group("hours"))
        revision = self._revision(producer, accumulation_match.group("stat"))
        parsed = ParsedSourceObject(
            remote=obj,
            product_code=self.product_code,
            producer=producer,
            domain_code=self.domain_code,
            initialization_time=valid_time,
            valid_time=valid_time,
            forecast_hour=0,
            parameter=match.group("parameter"),
            source_level=match.group("level"),
            grid=match.group("grid"),
            data_format=data_format,
            time_kind=self.config.kind,
            interval_start=valid_time - timedelta(hours=accumulation_hours),
            interval_end=valid_time,
            accumulation_hours=accumulation_hours,
            analysis_revision=revision,
        )
        if parsed.grid != self.config.domain(parsed.domain_code).grid:
            raise ValueError(f"unexpected {self.product_code.upper()} grid {parsed.grid!r}")
        self.config.analysis_timing.accumulation(accumulation_hours)
        field = self.field_for(parsed)
        if field is not None and (
            field.analysis is None
            or field.analysis.accumulation_hours != accumulation_hours
            or field.analysis.revision != revision
        ):
            raise ValueError("analysis filename conflicts with configured field timing")
        if expected_run is not None:
            self._validate_run(expected_run)
            if (
                parsed.valid_time != expected_run.initialization_time
                or parsed.domain_code != expected_run.domain_code
            ):
                raise ValueError("source object does not belong to the requested analysis time")
        return parsed

    def canonical_object_key(self, obj: RemoteObject) -> str:
        parsed = self.parse_object(obj)
        return (
            f"{self.config.provider}/{self.product_code}/{parsed.domain_code}/"
            f"valid_{parsed.valid_time:%Y%m%dT%HZ}/"
            f"accum_{parsed.accumulation_hours:02d}h/{parsed.analysis_revision}/"
            f"{obj.filename}"
        )

    def expected_manifest(self, run: RemoteRun) -> ExpectedManifest:
        self._validate_run(run)
        valid_hour = run.initialization_time.hour
        expected = {
            (field.code, 0)
            for field in self.config.fields
            if field.download_enabled
            and field.analysis is not None
            and valid_hour
            in self.config.analysis_timing.accumulation(
                field.analysis.accumulation_hours
            ).valid_hours_utc
        }
        return ExpectedManifest(self.config.code, run, frozenset(expected))

    def field_for(self, parsed: ParsedSourceObject) -> FieldConfig | None:
        return next(
            (
                field
                for field in self.config.fields
                if field.matches(parsed.producer, parsed.parameter, parsed.source_level)
            ),
            None,
        )

    def _revision(self, producer: str, statistic: str | None) -> str:
        if statistic == "Pct25":
            return "percentile_25"
        if statistic == "Pct75":
            return "percentile_75"
        if self.config.kind == "ensemble_analysis":
            return "ensemble_members"
        return "preliminary" if producer.endswith("-Prelim") else "final"

    def _validate_run(self, run: RemoteRun) -> None:
        if run.product_code != self.config.code:
            raise ValueError(f"run product must be {self.config.code}")
        self.config.domain(run.domain_code)
        valid_time = run.initialization_time
        if valid_time.minute or valid_time.second or valid_time.microsecond:
            raise ValueError("analysis valid time must be on an exact hour")
        if valid_time.hour not in self.config.run_hours_utc:
            raise ValueError(
                f"unsupported {self.product_code.upper()} valid hour {valid_time.hour:02d}Z"
            )
