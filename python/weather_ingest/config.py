"""Strict YAML configuration loading for ingestion products and fields."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

_CODE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DomainConfig(StrictModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1)
    resolution: str = Field(min_length=1)
    grid: str = Field(min_length=1)
    grid_width: int | None = Field(default=None, gt=0)
    grid_height: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_dimensions(self) -> DomainConfig:
        if (self.grid_width is None) != (self.grid_height is None):
            raise ValueError("grid_width and grid_height must be configured together")
        return self


class ForecastHourSegment(StrictModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    step: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> ForecastHourSegment:
        if self.end < self.start:
            raise ValueError("forecast hour end must be greater than or equal to start")
        if (self.end - self.start) % self.step:
            raise ValueError("forecast hour range must be evenly divisible by step")
        return self

    def values(self) -> tuple[int, ...]:
        return tuple(range(self.start, self.end + 1, self.step))


class ForecastHoursConfig(StrictModel):
    start: int | None = Field(ge=0, default=None)
    end: int | None = Field(ge=0, default=None)
    step: int | None = Field(gt=0, default=None)
    segments: tuple[ForecastHourSegment, ...] = ()

    @model_validator(mode="after")
    def validate_schedule(self) -> ForecastHoursConfig:
        simple_values = (self.start, self.end, self.step)
        has_simple = any(value is not None for value in simple_values)
        if has_simple and (not all(value is not None for value in simple_values) or self.segments):
            raise ValueError("use either one complete forecast range or segments, not both")
        if not has_simple and not self.segments:
            raise ValueError("forecast hours require a range or at least one segment")
        if has_simple:
            ForecastHourSegment(start=self.start, end=self.end, step=self.step)
        else:
            combined = [hour for segment in self.segments for hour in segment.values()]
            if len(combined) != len(set(combined)):
                raise ValueError("forecast hour segments must not overlap")
        return self

    def values(self) -> tuple[int, ...]:
        if self.segments:
            return tuple(sorted(hour for segment in self.segments for hour in segment.values()))
        return ForecastHourSegment(start=self.start, end=self.end, step=self.step).values()


class DiscoveryConfig(StrictModel):
    mode: Literal["https_listing"]
    base_url: str = Field(pattern=r"^https://")
    today_path: str = Field(min_length=1)
    archive_path: str = Field(min_length=1)
    operational_mode: Literal["amqps_required"]
    late_arrival_grace_minutes: int = Field(ge=0)
    retry_window_hours: int = Field(ge=0)
    reconciliation_schedule: str = Field(default="15 * * * *", min_length=1)
    maximum_objects_per_run: int = Field(default=512, ge=1, le=512)

    @model_validator(mode="after")
    def validate_templates(self) -> DiscoveryConfig:
        common = {"resolution", "run_hour"}
        for name, template, required in (
            ("today_path", self.today_path, common),
            ("archive_path", self.archive_path, common | {"run_date"}),
        ):
            missing = {value for value in required if "{" + value + "}" not in template}
            if missing:
                raise ValueError(f"{name} is missing placeholders: {sorted(missing)}")
            if template.startswith("/") or ".." in Path(template).parts:
                raise ValueError(f"{name} must be a safe relative URL path")
        return self


class LimitsConfig(StrictModel):
    maximum_parallel_downloads: int = Field(ge=1, le=32)
    maximum_objects_per_manual_run: int = Field(ge=1, le=512)
    minimum_free_bytes: int = Field(ge=0)


class RetentionConfig(StrictModel):
    raw_days: int = Field(ge=1)
    processed_days: int = Field(ge=1)
    retain_forever: bool = False


class VisibilityConfig(StrictModel):
    required_field_codes: tuple[str, ...] = Field(min_length=1)


class EstimateConfig(StrictModel):
    processed_to_raw_ratio: float = Field(gt=0)


class AvailabilityConfig(StrictModel):
    start_forecast_hour: int = Field(ge=0, default=0)
    end_forecast_hour: int | None = Field(ge=0, default=None)
    forecast_hour_step: int = Field(gt=0, default=1)

    @model_validator(mode="after")
    def validate_range(self) -> AvailabilityConfig:
        if self.end_forecast_hour is not None and self.end_forecast_hour < self.start_forecast_hour:
            raise ValueError("field availability end must not precede start")
        return self

    def includes(self, forecast_hour: int) -> bool:
        return (
            forecast_hour >= self.start_forecast_hour
            and (
                self.end_forecast_hour is None
                or forecast_hour <= self.end_forecast_hour
            )
            and (forecast_hour - self.start_forecast_hour) % self.forecast_hour_step == 0
        )


class SourceSelectorConfig(StrictModel):
    producer: str = Field(min_length=1)
    parameter: str = Field(min_length=1)
    level: str = Field(min_length=1)
    expected_unit: str = Field(min_length=1)


class AnalysisFieldConfig(StrictModel):
    accumulation_hours: int = Field(gt=0, le=168)
    revision: Literal[
        "preliminary",
        "final",
        "ensemble_members",
        "percentile_25",
        "percentile_75",
    ]


class AnalysisAccumulationConfig(StrictModel):
    hours: int = Field(gt=0, le=168)
    valid_hours_utc: tuple[int, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_hours(self) -> AnalysisAccumulationConfig:
        if len(set(self.valid_hours_utc)) != len(self.valid_hours_utc):
            raise ValueError("analysis valid hours must be unique")
        if any(hour < 0 or hour > 23 for hour in self.valid_hours_utc):
            raise ValueError("analysis valid hours must be in the range 0..23")
        return self


class AnalysisTimingConfig(StrictModel):
    reference_time_semantics: Literal["valid_time"]
    interval_end_semantics: Literal["reference_time"]
    accumulations: tuple[AnalysisAccumulationConfig, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_accumulations(self) -> AnalysisTimingConfig:
        hours = [accumulation.hours for accumulation in self.accumulations]
        if len(hours) != len(set(hours)):
            raise ValueError("analysis accumulation intervals must be unique")
        return self

    def accumulation(self, hours: int) -> AnalysisAccumulationConfig:
        try:
            return next(item for item in self.accumulations if item.hours == hours)
        except StopIteration as exc:
            raise KeyError(f"analysis accumulation {hours}h is not configured") from exc


class FieldConfig(StrictModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    canonical_variable: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    level_code: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$")
    source: SourceSelectorConfig
    canonical_unit: str = Field(min_length=1)
    conversion_key: Literal[
        "identity",
        "kilograms_per_cubic_metre_to_micrograms_per_cubic_metre",
        "kelvin_to_celsius",
        "metres_to_kilometres",
        "pascals_to_hectopascals",
    ]
    output_data_type: Literal["Float32", "Float64", "UInt8", "UInt16"]
    nodata_value: float
    resampling: Literal["nearest", "bilinear", "average"]
    download_enabled: bool
    processing_enabled: bool
    display_enabled: bool
    default_style: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    display_name: str | None = Field(default=None, min_length=1)
    availability: AvailabilityConfig = AvailabilityConfig()
    analysis: AnalysisFieldConfig | None = None
    source_band: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_enablement(self) -> FieldConfig:
        if self.processing_enabled and not self.download_enabled:
            raise ValueError("processing requires downloads to be enabled")
        if self.display_enabled and not self.processing_enabled:
            raise ValueError("display requires processing to be enabled")
        return self

    def matches(self, producer: str, parameter: str, level: str) -> bool:
        return (
            self.source.producer == producer
            and self.source.parameter == parameter
            and self.source.level == level
        )


class VariableConfigFile(StrictModel):
    version: Literal[1]
    products: dict[str, tuple[FieldConfig, ...]]


class ProductConfig(StrictModel):
    version: Literal[1]
    code: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    provider: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    kind: Literal["forecast", "analysis", "ensemble_analysis"]
    enabled: bool
    adapter: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    source_producers: tuple[str, ...] = Field(min_length=1)
    source_formats: tuple[Literal["grib2", "json", "nc"], ...] = ("grib2",)
    domains: tuple[DomainConfig, ...] = Field(min_length=1)
    run_hours_utc: tuple[int, ...] = Field(min_length=1)
    forecast_hours: ForecastHoursConfig
    discovery: DiscoveryConfig
    limits: LimitsConfig
    retention: RetentionConfig
    visibility: VisibilityConfig
    estimates: EstimateConfig
    analysis_timing: AnalysisTimingConfig | None = None
    variable_config_files: tuple[str, ...] = Field(min_length=1)
    fields: tuple[FieldConfig, ...] = ()

    @model_validator(mode="after")
    def validate_product(self) -> ProductConfig:
        if len(set(self.run_hours_utc)) != len(self.run_hours_utc):
            raise ValueError("run_hours_utc must be unique")
        if any(hour < 0 or hour > 23 for hour in self.run_hours_utc):
            raise ValueError("run_hours_utc values must be in the range 0..23")
        if len({domain.code for domain in self.domains}) != len(self.domains):
            raise ValueError("domain codes must be unique")
        if len(set(self.source_producers)) != len(self.source_producers):
            raise ValueError("source_producers must be unique")
        if len(set(self.source_formats)) != len(self.source_formats):
            raise ValueError("source formats must be unique")

        templates = (self.discovery.today_path, self.discovery.archive_path)
        if self.kind == "forecast":
            if self.analysis_timing is not None:
                raise ValueError("forecast products cannot define analysis_timing")
            if any("{forecast_hour}" not in template for template in templates):
                raise ValueError("forecast discovery paths require {forecast_hour}")
        else:
            if self.analysis_timing is None:
                raise ValueError("analysis products require analysis_timing")
            if self.forecast_hours.values() != (0,):
                raise ValueError("analysis products must use only the zero time offset")
            if any("{forecast_hour}" in template for template in templates):
                raise ValueError("analysis discovery paths cannot use {forecast_hour}")
            analysis_hours = {
                hour
                for accumulation in self.analysis_timing.accumulations
                for hour in accumulation.valid_hours_utc
            }
            if set(self.run_hours_utc) != analysis_hours:
                raise ValueError(
                    "run_hours_utc must equal the analysis accumulation valid-hour union"
                )
        if self.fields:
            field_codes = {field.code for field in self.fields}
            missing = set(self.visibility.required_field_codes) - field_codes
            if missing:
                raise ValueError(f"required fields are not configured: {sorted(missing)}")
            if len(field_codes) != len(self.fields):
                raise ValueError("field codes must be unique")
            for field in self.fields:
                if field.source.producer not in self.source_producers:
                    raise ValueError(
                        f"field {field.code!r} uses producer "
                        f"{field.source.producer!r}, which is not declared by "
                        f"product {self.code!r}"
                    )
                if self.kind == "forecast" and field.analysis is not None:
                    raise ValueError("forecast fields cannot define analysis metadata")
                if self.kind != "forecast":
                    if field.analysis is None:
                        raise ValueError("analysis fields require analysis metadata")
                    self.analysis_timing.accumulation(field.analysis.accumulation_hours)
        return self

    def domain(self, code: str) -> DomainConfig:
        try:
            return next(domain for domain in self.domains if domain.code == code)
        except StopIteration as exc:
            raise KeyError(f"unknown domain {code!r} for product {self.code}") from exc

    def field(self, code: str) -> FieldConfig:
        try:
            return next(field for field in self.fields if field.code == code)
        except StopIteration as exc:
            raise KeyError(f"unknown field {code!r} for product {self.code}") from exc

    def expected_processing_asset_count(self, *, reference_hour: int | None = None) -> int:
        """Count every enabled field/hour pair expected to become a COG asset."""

        if self.kind != "forecast":
            if reference_hour is None:
                raise ValueError("analysis asset counts require a reference hour")
            if self.analysis_timing is None:
                raise ValueError("analysis timing configuration is required")
            return sum(
                1
                for field in self.fields
                if field.download_enabled
                and field.processing_enabled
                and field.analysis is not None
                and reference_hour
                in self.analysis_timing.accumulation(
                    field.analysis.accumulation_hours
                ).valid_hours_utc
            )
        return sum(
            1
            for field in self.fields
            if field.download_enabled and field.processing_enabled
            for forecast_hour in self.forecast_hours.values()
            if field.availability.includes(forecast_hour)
        )


def default_config_root() -> Path:
    configured = os.getenv("WEATHER_CONFIG_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "config"


def _load_yaml(path: Path) -> object:
    try:
        with path.open("r", encoding="utf-8") as source:
            return yaml.safe_load(source)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML in {path}: {exc}") from exc


def _resolve_config_file(root: Path, relative_name: str) -> Path:
    candidate = (root / relative_name).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"configuration path escapes root: {relative_name}")
    if candidate.suffix not in {".yaml", ".yml"}:
        raise ValueError(f"configuration file must be YAML: {relative_name}")
    return candidate


def load_product_config(config_root: Path | str, product_code: str) -> ProductConfig:
    if not _CODE_RE.fullmatch(product_code):
        raise ValueError(f"invalid product code: {product_code!r}")
    root = Path(config_root).expanduser().resolve()
    product_path = _resolve_config_file(root, f"models/{product_code}.yaml")
    product = ProductConfig.model_validate(_load_yaml(product_path))
    if product.code != product_code:
        raise ValueError(f"product file code {product.code!r} does not match {product_code!r}")

    fields: list[FieldConfig] = []
    for relative_name in product.variable_config_files:
        variable_path = _resolve_config_file(root, relative_name)
        variable_file = VariableConfigFile.model_validate(_load_yaml(variable_path))
        fields.extend(variable_file.products.get(product_code, ()))

    return ProductConfig.model_validate({**product.model_dump(), "fields": fields})


def load_enabled_products(config_root: Path | str) -> tuple[ProductConfig, ...]:
    root = Path(config_root).expanduser().resolve()
    model_paths = sorted((root / "models").glob("*.yaml"))
    products = [load_product_config(root, path.stem) for path in model_paths]
    return tuple(product for product in products if product.enabled)
