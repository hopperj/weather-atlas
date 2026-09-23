"""Public response models for the weather catalogue API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def _camel_case(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.title() for part in rest)


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=_camel_case, populate_by_name=True)


class ProductSummary(ApiModel):
    code: str
    name: str
    description: str | None
    kind: Literal["forecast", "analysis", "ensemble_analysis"]
    priority: int
    latest_run_time: datetime | None


class DomainSummary(ApiModel):
    code: str
    name: str
    bounds: tuple[float, float, float, float] | None


class PaletteStop(ApiModel):
    value: float
    color: str
    label: str | None = None


class FieldSummary(ApiModel):
    code: str
    variable_code: str
    name: str
    variable_class: str
    level_code: str
    level_name: str
    unit: str
    palette: list[PaletteStop]
    default_min: float
    default_max: float


class VariableSummary(ApiModel):
    code: str
    variable_code: str
    name: str
    variable_class: str
    level_code: str
    level_name: str
    unit: str
    products: list[str]


class RunSummary(ApiModel):
    run_time: datetime
    status: str
    available_time_count: int = Field(ge=0)


class TimeSummary(ApiModel):
    valid_time: datetime
    forecast_hour: int | None = Field(default=None, ge=0)
    interval_start: datetime | None
    interval_end: datetime | None
    time_kind: Literal["instant", "accumulation", "average", "maximum"]


class TimelineFrameSummary(TimeSummary):
    run_time: datetime


class IngestionStatus(ApiModel):
    product_code: str
    run_time: datetime | None
    source_status: str | None
    processing_status: str | None
    is_visible: bool
    expected_asset_count: int = Field(ge=0)
    discovered_asset_count: int = Field(ge=0)
    downloaded_asset_count: int = Field(ge=0)
    processed_asset_count: int = Field(ge=0)
    failed_asset_count: int = Field(ge=0)
    first_discovered_at: datetime | None
    completed_at: datetime | None


class Legend(ApiModel):
    minimum: float
    maximum: float
    palette: list[PaletteStop]


class ResolvedLayer(ApiModel):
    product: str
    domain: str
    run_time: datetime
    valid_time: datetime
    forecast_hour: int | None
    field: str
    variable: str
    level: str
    unit: str
    tile_url: str
    token: str
    bounds: tuple[float, float, float, float] | None
    legend: Legend


class SampleValue(ApiModel):
    field: str
    variable: str
    level: str
    value: float | None
    unit: str
    nodata: bool


class SampleResponse(ApiModel):
    longitude: float
    latitude: float
    run_time: datetime
    valid_time: datetime
    values: list[SampleValue]


class WindVectorProperties(ApiModel):
    u: float
    v: float
    speed: float = Field(ge=0)
    bearing: float = Field(ge=0, lt=360)


class WindVectorGeometry(ApiModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]


class WindVectorFeature(ApiModel):
    type: Literal["Feature"] = "Feature"
    geometry: WindVectorGeometry
    properties: WindVectorProperties


class WindVectorCollection(ApiModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    product: str
    domain: str
    run_time: datetime
    valid_time: datetime
    unit: str
    bbox: tuple[float, float, float, float]
    columns: int = Field(ge=1)
    rows: int = Field(ge=1)
    feature_count: int = Field(ge=0)
    features: list[WindVectorFeature]


class ProductCollection(ApiModel):
    items: list[ProductSummary]
    next_cursor: str | None = None


class DomainCollection(ApiModel):
    items: list[DomainSummary]
    next_cursor: str | None = None


class FieldCollection(ApiModel):
    items: list[FieldSummary]
    next_cursor: str | None = None


class VariableCollection(ApiModel):
    items: list[VariableSummary]
    next_cursor: str | None = None


class RunCollection(ApiModel):
    items: list[RunSummary]
    next_cursor: str | None = None


class TimeCollection(ApiModel):
    items: list[TimeSummary]
    next_cursor: str | None = None


class TimelineCollection(ApiModel):
    items: list[TimelineFrameSummary]
    truncated: bool = False


class IngestionStatusCollection(ApiModel):
    items: list[IngestionStatus]


class ErrorBody(ApiModel):
    detail: str
    request_id: str | None = None
