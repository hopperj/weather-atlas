"""Shared ECCC Datamart behavior for single-grid deterministic forecasts."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin

from weather_ingest.config import FieldConfig, ProductConfig
from weather_ingest.http_listing import ListingSource, parse_directory_listing
from weather_ingest.models import (
    ExpectedManifest,
    ParsedSourceObject,
    RemoteObject,
    RemoteRun,
)

_FILENAME_RE = re.compile(
    r"^(?P<date>\d{8})T(?P<hour>\d{2})Z_MSC_"
    r"(?P<producer>[A-Za-z0-9.-]+)_"
    r"(?P<parameter>.+)_(?P<level>[^_]+)_"
    r"(?P<grid>[^_]+)_PT(?P<forecast>\d{3})H\."
    r"(?P<format>grib2|json)$"
)


class EcccForecastAdapter:
    """Interpret transport layout while product subclasses declare their code."""

    product_code: str

    def __init__(self, config: ProductConfig, listing_source: ListingSource) -> None:
        if config.code != self.product_code or config.adapter != self.product_code:
            raise ValueError(
                f"{type(self).__name__} requires the {self.product_code} product configuration"
            )
        if config.kind != "forecast" or len(config.domains) != 1:
            raise ValueError("deterministic forecast adapters require one forecast domain")
        self.config = config
        self.listing_source = listing_source
        self.domain_code = config.domains[0].code

    def list_candidate_runs(self, now: datetime, *, lookback_hours: int = 24) -> list[RemoteRun]:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        if lookback_hours < 0:
            raise ValueError("lookback_hours must not be negative")
        now = now.astimezone(UTC)
        cutoff = now - timedelta(hours=lookback_hours)
        runs: list[RemoteRun] = []
        day = cutoff.replace(hour=0, minute=0, second=0, microsecond=0)
        while day <= now:
            for run_hour in self.config.run_hours_utc:
                initialization = day.replace(hour=run_hour)
                if cutoff <= initialization <= now:
                    runs.append(RemoteRun(self.product_code, self.domain_code, initialization))
            day += timedelta(days=1)
        return sorted(runs, key=lambda run: run.initialization_time, reverse=True)

    def directory_url(
        self, run: RemoteRun, forecast_hour: int, *, use_today_alias: bool = False
    ) -> str:
        self._validate_run(run)
        if forecast_hour not in self.config.forecast_hours.values():
            raise ValueError(f"forecast hour {forecast_hour} is not configured")
        domain = self.config.domain(run.domain_code)
        values = {
            "resolution": domain.resolution,
            "run_hour": f"{run.initialization_time.hour:02d}",
            "forecast_hour": f"{forecast_hour:03d}",
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
        hours = forecast_hours or self.config.forecast_hours.values()
        if not hours:
            raise ValueError("at least one forecast hour is required")
        objects: list[RemoteObject] = []
        for forecast_hour in hours:
            directory_url = self.directory_url(
                run, forecast_hour, use_today_alias=use_today_alias
            )
            document = self.listing_source.get_text(directory_url)
            objects.extend(parse_directory_listing(directory_url, document))
        return sorted(objects, key=lambda obj: obj.filename)

    def parse_object(
        self, obj: RemoteObject, *, expected_run: RemoteRun | None = None
    ) -> ParsedSourceObject:
        match = _FILENAME_RE.fullmatch(obj.filename)
        if not match:
            raise ValueError(f"unrecognized {self.product_code.upper()} filename: {obj.filename}")
        producer = match.group("producer")
        if producer not in self.config.source_producers:
            raise ValueError(f"unexpected {self.product_code.upper()} producer {producer!r}")
        initialization = datetime.strptime(
            match.group("date") + match.group("hour"), "%Y%m%d%H"
        ).replace(tzinfo=UTC)
        forecast_hour = int(match.group("forecast"))
        parsed = ParsedSourceObject(
            remote=obj,
            product_code=self.product_code,
            producer=producer,
            domain_code=self.domain_code,
            initialization_time=initialization,
            valid_time=initialization + timedelta(hours=forecast_hour),
            forecast_hour=forecast_hour,
            parameter=match.group("parameter"),
            source_level=match.group("level"),
            grid=match.group("grid"),
            data_format=match.group("format"),
        )
        if parsed.grid != self.config.domain(parsed.domain_code).grid:
            raise ValueError(f"unexpected {self.product_code.upper()} grid {parsed.grid!r}")
        if forecast_hour not in self.config.forecast_hours.values():
            raise ValueError(
                f"unexpected {self.product_code.upper()} forecast hour {forecast_hour}"
            )
        if expected_run is not None:
            self._validate_run(expected_run)
            if (
                parsed.initialization_time != expected_run.initialization_time
                or parsed.domain_code != expected_run.domain_code
            ):
                product_name = self.product_code.upper()
                raise ValueError(
                    f"source object does not belong to the requested {product_name} run"
                )
        return parsed

    def canonical_object_key(self, obj: RemoteObject) -> str:
        parsed = self.parse_object(obj)
        return (
            f"{self.config.provider}/{self.product_code}/{parsed.domain_code}/"
            f"{parsed.initialization_time:%Y%m%dT%HZ}/"
            f"f{parsed.forecast_hour:03d}/{obj.filename}"
        )

    def expected_manifest(self, run: RemoteRun) -> ExpectedManifest:
        self._validate_run(run)
        expected = {
            (field.code, forecast_hour)
            for field in self.config.fields
            if field.download_enabled
            for forecast_hour in self.config.forecast_hours.values()
            if field.availability.includes(forecast_hour)
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

    def _validate_run(self, run: RemoteRun) -> None:
        if run.product_code != self.config.code:
            raise ValueError(f"run product must be {self.config.code}")
        self.config.domain(run.domain_code)
        initialization = run.initialization_time
        if initialization.minute or initialization.second or initialization.microsecond:
            raise ValueError("run initialization must be on an exact hour")
        if initialization.hour not in self.config.run_hours_utc:
            raise ValueError(
                f"unsupported {self.product_code.upper()} run hour {initialization.hour:02d}Z"
            )
