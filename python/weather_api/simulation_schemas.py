"""Public bounded schemas for research smoke simulations."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field
from weather_ingest.fire_scenarios import SmokeScenarioConfig

from weather_api.schemas import ApiModel


class ScenarioCreate(ApiModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    config: SmokeScenarioConfig


class RevisionCreate(ApiModel):
    config: SmokeScenarioConfig


class RunCreate(ApiModel):
    revision_id: UUID
    run_kind: Literal["interactive"] = "interactive"


class ScenarioSummary(ApiModel):
    id: UUID
    name: str
    description: str
    owner_label: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    revision_count: int | None = None


class RevisionSummary(ApiModel):
    id: UUID
    scenario_id: UUID
    revision_number: int
    canonical_config: dict[str, Any]
    config_sha256: str
    created_at: datetime


class SimulationRunSummary(ApiModel):
    id: UUID
    scenario_revision_id: UUID
    scenario_id: UUID | None = None
    run_kind: str
    status: str
    requested_at: datetime
    queued_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    requested_by: str | None = None
    gfs_cycle_time: datetime | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    warnings: list[Any] = Field(default_factory=list)
    error_class: str | None = None
    error_message: str | None = None
    cancellation_requested_at: datetime | None = None


class RunSubmission(ApiModel):
    run_id: UUID
    status: str
    status_url: str
    reused: bool
    estimate: dict[str, int]


class ArtifactSummary(ApiModel):
    artifact_kind: str
    relative_path: str
    sha256: str
    size_bytes: int
    mime_type: str
    metadata: dict[str, Any]
    status: str


class ItemCollection(ApiModel):
    items: list[dict[str, Any]]
