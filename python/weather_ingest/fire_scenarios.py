"""Validated, immutable smoke-simulation scenario configuration."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AreaMode(StrEnum):
    CFFEPS_NATIVE = "cffeps_native_growth"
    USER_AREA_CURVE = "user_area_curve"
    FIXED_SOURCE_TEST = "fixed_source_test"


class UncertaintyMode(StrEnum):
    LOW = "low"
    CENTRAL = "central"
    HIGH = "high"
    ENSEMBLE = "ensemble"


class FireWeatherMode(StrEnum):
    AUTOMATIC_CWFIS = "automatic_cwfis"
    MANUAL = "manual"


class FireWeatherCodes(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ffmc: float = Field(gt=0, le=101)
    dmc: float = Field(gt=0, le=1000)
    dc: float = Field(gt=0, le=2000)


class AreaPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    time: datetime
    area_ha: float = Field(ge=0, le=10_000_000)

    @field_validator("time")
    @classmethod
    def time_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("area-curve times must include a UTC offset")
        return value.astimezone(UTC)


class SmokeScenarioConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(min_length=1, max_length=100)
    start_time: datetime
    end_time: datetime
    bbox: tuple[float, float, float, float]
    event_ids: tuple[str, ...] = ()
    area_mode: AreaMode = AreaMode.CFFEPS_NATIVE
    area_curve: tuple[AreaPoint, ...] = ()
    fire_weather_mode: FireWeatherMode = FireWeatherMode.AUTOMATIC_CWFIS
    fire_weather: FireWeatherCodes | None = None
    species: tuple[str, ...] = ("PM25", "CO", "BC")
    uncertainty: UncertaintyMode = UncertaintyMode.CENTRAL
    grid_spacing_degrees: float = 0.5
    particle_budget: int = Field(default=250_000, ge=10_000, le=1_000_000)
    random_seed: int = Field(default=20260722, ge=1, le=2_147_483_647)

    @model_validator(mode="before")
    @classmethod
    def preserve_legacy_manual_contract(cls, value: object) -> object:
        """Interpret old revisions containing explicit codes as manual overrides."""

        if isinstance(value, dict) and "fire_weather_mode" not in value and value.get(
            "fire_weather"
        ) is not None:
            return value | {"fire_weather_mode": FireWeatherMode.MANUAL}
        return value

    @model_validator(mode="after")
    def validate_contract(self) -> SmokeScenarioConfig:
        if self.start_time.tzinfo is None or self.end_time.tzinfo is None:
            raise ValueError("scenario times must include UTC offsets")
        if self.end_time <= self.start_time:
            raise ValueError("end_time must follow start_time")
        if (self.end_time - self.start_time).total_seconds() > 24 * 3600:
            raise ValueError("scenario horizon must not exceed 24 hours")
        west, south, east, north = self.bbox
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError("bbox must be ordered geographic coordinates")
        if (east - west) * (north - south) > 2500:
            raise ValueError("scenario domain is too large")
        if self.grid_spacing_degrees not in {0.25, 0.5, 1.0}:
            raise ValueError("unsupported grid spacing")
        if not self.species or set(self.species) - {"PM25", "CO", "BC"}:
            raise ValueError("species must be a non-empty subset of PM25, CO, BC")
        if self.fire_weather_mode == FireWeatherMode.MANUAL and self.fire_weather is None:
            raise ValueError("manual fire weather mode requires FFMC, DMC, and DC")
        if (
            self.fire_weather_mode == FireWeatherMode.AUTOMATIC_CWFIS
            and self.fire_weather is not None
        ):
            raise ValueError("automatic CWFIS mode does not accept manual fire-weather values")
        if self.uncertainty == UncertaintyMode.ENSEMBLE:
            raise ValueError(
                "ensemble submission is not enabled until member-specific publication "
                "is implemented; submit low, central, and high revisions separately"
            )
        if len(set(self.event_ids)) != len(self.event_ids) or len(self.event_ids) > 200:
            raise ValueError("event_ids must be unique and contain at most 200 events")
        if self.area_mode == AreaMode.USER_AREA_CURVE:
            if not self.area_curve:
                raise ValueError("user_area_curve requires area_curve")
            if len(self.event_ids) != 1:
                raise ValueError("user_area_curve requires exactly one explicit fire event")
            times = [point.time for point in self.area_curve]
            if times != sorted(times) or len(set(times)) != len(times):
                raise ValueError("area_curve times must be strictly ordered")
            if times[0] > self.start_time or times[-1] < self.end_time:
                raise ValueError("area_curve must cover the full scenario interval")
            areas = [point.area_ha for point in self.area_curve]
            if any(later < earlier for earlier, later in zip(areas, areas[1:], strict=False)):
                raise ValueError("area_curve cumulative area must be non-decreasing")
        elif self.area_mode == AreaMode.FIXED_SOURCE_TEST:
            raise ValueError(
                "fixed_source_test is reserved for internal validation until its explicit "
                "mass-rate contract is implemented"
            )
        elif self.area_curve:
            raise ValueError("area_curve is only valid for user_area_curve")
        return self

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    @property
    def config_sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()
