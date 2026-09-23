"""Environment-backed settings with no framework-specific dependency."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    redis_url: str
    data_root: Path
    sql_root: Path
    layer_token_secret: str
    layer_token_ttl_seconds: int
    sample_cache_ttl_seconds: int
    sample_rate_limit_per_minute: int
    simulation_writes_enabled: bool
    smoke_validation_runs_enabled: bool
    smoke_max_horizon_hours: int
    smoke_max_domain_cells: int
    smoke_maximum_particles: int
    smoke_maximum_releases: int
    smoke_max_queued_runs: int
    smoke_run_timeout_seconds: int
    smoke_maximum_output_bytes: int
    smoke_minimum_free_bytes: int
    smoke_maximum_storage_bytes: int
    smoke_interactive_retention_days: int
    smoke_operational_retention_days: int

    def __post_init__(self) -> None:
        if len(self.layer_token_secret) < 24:
            raise ValueError("WEATHER_LAYER_TOKEN_SECRET must contain at least 24 characters")
        if not 60 <= self.layer_token_ttl_seconds <= 604800:
            raise ValueError("WEATHER_LAYER_TOKEN_TTL_SECONDS must be between 60 and 604800")
        if not 0 <= self.sample_cache_ttl_seconds <= 86400:
            raise ValueError("WEATHER_SAMPLE_CACHE_TTL_SECONDS must be between 0 and 86400")
        if not 1 <= self.sample_rate_limit_per_minute <= 10000:
            raise ValueError("WEATHER_SAMPLE_RATE_LIMIT_PER_MINUTE must be between 1 and 10000")
        if not 1 <= self.smoke_max_horizon_hours <= 24:
            raise ValueError("SMOKE_MAX_HORIZON_HOURS must be between 1 and 24")
        if not 1 <= self.smoke_max_domain_cells <= 1_000_000:
            raise ValueError("SMOKE_MAX_DOMAIN_CELLS must be between 1 and 1000000")
        if not 10_000 <= self.smoke_maximum_particles <= 1_000_000:
            raise ValueError("SMOKE_MAXIMUM_PARTICLES must be between 10000 and 1000000")
        if not 1 <= self.smoke_maximum_releases <= 100_000:
            raise ValueError("SMOKE_MAXIMUM_RELEASES must be between 1 and 100000")
        if not 1 <= self.smoke_max_queued_runs <= 100:
            raise ValueError("SMOKE_MAX_QUEUED_RUNS must be between 1 and 100")
        if not 60 <= self.smoke_run_timeout_seconds <= 86_400:
            raise ValueError("SMOKE_RUN_TIMEOUT_SECONDS must be between 60 and 86400")
        if not 1 <= self.smoke_maximum_output_bytes <= 1_099_511_627_776:
            raise ValueError("SMOKE_MAXIMUM_OUTPUT_BYTES must be between 1 byte and 1 TiB")
        if not 0 <= self.smoke_minimum_free_bytes <= 1_099_511_627_776:
            raise ValueError("SMOKE_MINIMUM_FREE_BYTES must be between 0 bytes and 1 TiB")
        if not 1 <= self.smoke_maximum_storage_bytes <= 4_398_046_511_104:
            raise ValueError("SMOKE_MAXIMUM_STORAGE_BYTES must be between 1 byte and 4 TiB")
        if not 1 <= self.smoke_interactive_retention_days <= 3650:
            raise ValueError("SMOKE_INTERACTIVE_RETENTION_DAYS must be between 1 and 3650")
        if not 1 <= self.smoke_operational_retention_days <= 3650:
            raise ValueError("SMOKE_OPERATIONAL_RETENTION_DAYS must be between 1 and 3650")

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(
            database_url=os.getenv(
                "WEATHER_DATABASE_URL",
                "postgresql://weather_api:change-me-weather-api@localhost/weather_app",
            ),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            data_root=Path(os.getenv("WEATHER_DATA_ROOT", "./data")).resolve(),
            sql_root=Path(os.getenv("WEATHER_SQL_ROOT", "./database/queries")).resolve(),
            layer_token_secret=os.getenv(
                "WEATHER_LAYER_TOKEN_SECRET", "development-only-change-me-layer-token"
            ),
            layer_token_ttl_seconds=int(os.getenv("WEATHER_LAYER_TOKEN_TTL_SECONDS", "86400")),
            sample_cache_ttl_seconds=int(os.getenv("WEATHER_SAMPLE_CACHE_TTL_SECONDS", "300")),
            sample_rate_limit_per_minute=int(
                os.getenv("WEATHER_SAMPLE_RATE_LIMIT_PER_MINUTE", "120")
            ),
            simulation_writes_enabled=os.getenv(
                "SIMULATION_WRITES_ENABLED", "false"
            ).lower() in {"1", "true", "yes"},
            smoke_validation_runs_enabled=os.getenv(
                "SMOKE_VALIDATION_RUNS_ENABLED", "false"
            ).lower() in {"1", "true", "yes"},
            smoke_max_horizon_hours=int(os.getenv("SMOKE_MAX_HORIZON_HOURS", "24")),
            smoke_max_domain_cells=int(os.getenv("SMOKE_MAX_DOMAIN_CELLS", "50000")),
            smoke_maximum_particles=int(os.getenv("SMOKE_MAXIMUM_PARTICLES", "1000000")),
            smoke_maximum_releases=int(os.getenv("SMOKE_MAXIMUM_RELEASES", "20000")),
            smoke_max_queued_runs=int(os.getenv("SMOKE_MAX_QUEUED_RUNS", "5")),
            smoke_run_timeout_seconds=int(os.getenv("SMOKE_RUN_TIMEOUT_SECONDS", "10800")),
            smoke_maximum_output_bytes=int(
                os.getenv("SMOKE_MAXIMUM_OUTPUT_BYTES", "21474836480")
            ),
            smoke_minimum_free_bytes=int(
                os.getenv("SMOKE_MINIMUM_FREE_BYTES", "21474836480")
            ),
            smoke_maximum_storage_bytes=int(
                os.getenv("SMOKE_MAXIMUM_STORAGE_BYTES", "549755813888")
            ),
            smoke_interactive_retention_days=int(
                os.getenv("SMOKE_INTERACTIVE_RETENTION_DAYS", "30")
            ),
            smoke_operational_retention_days=int(
                os.getenv("SMOKE_OPERATIONAL_RETENTION_DAYS", "14")
            ),
        )
