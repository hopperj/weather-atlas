"""Low-cardinality Prometheus metrics shared by the HTTP services."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import Response

HTTP_REQUESTS = Counter(
    "weather_http_requests_total",
    "HTTP requests handled by weather-platform services.",
    ("service", "method", "route", "status"),
)
HTTP_DURATION = Histogram(
    "weather_http_request_duration_seconds",
    "HTTP request latency for weather-platform services.",
    ("service", "method", "route"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
OPERATION_DURATION = Histogram(
    "weather_operation_duration_seconds",
    "Duration of expensive catalogue, sampling, and raster operations.",
    ("service", "operation"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
SMOKE_JOBS = Gauge(
    "weather_smoke_jobs",
    "Persisted smoke simulation jobs by current state.",
    ("status",),
)
SMOKE_LATEST_COUNTS = Gauge(
    "weather_smoke_latest_run_count",
    "Counts recorded by the latest completed smoke simulation.",
    ("kind",),
)
SMOKE_LATEST_MASS_KG = Gauge(
    "weather_smoke_latest_run_released_mass_kg",
    "Released mass in the latest completed smoke simulation.",
    ("species",),
)
SMOKE_LATEST_DURATION_SECONDS = Gauge(
    "weather_smoke_latest_run_duration_seconds",
    "Phase duration in the latest completed smoke simulation.",
    ("phase",),
)
SMOKE_LATEST_INPUT_AGE_SECONDS = Gauge(
    "weather_smoke_latest_run_input_age_seconds",
    "Input age at admission for the latest completed smoke simulation.",
    ("input",),
)
SMOKE_LATEST_MASS_RESIDUAL_KG = Gauge(
    "weather_smoke_latest_run_mass_balance_residual_kg",
    "Maximum absolute emission-to-release mass residual in the latest completed run.",
)
SMOKE_LATEST_BYTES = Gauge(
    "weather_smoke_latest_run_bytes",
    "Bytes recorded for the latest completed smoke simulation.",
    ("kind",),
)
SMOKE_LAST_COMPLETED_TIMESTAMP = Gauge(
    "weather_smoke_last_completed_timestamp_seconds",
    "Completion time of the latest terminal smoke simulation.",
)
SMOKE_STORAGE_BYTES = Gauge(
    "weather_smoke_storage_bytes",
    "Smoke workspace storage capacity measurement.",
    ("kind",),
)

SMOKE_STATUSES = (
    "queued",
    "resolving_inputs",
    "emissions_running",
    "transport_running",
    "processing_outputs",
    "publishing",
    "complete",
    "complete_with_warnings",
    "cancellation_requested",
    "cancelled",
    "failed",
)


async def observe_http_request(
    service: str,
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Record a request without using unbounded URL values as labels."""
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = request.scope.get("route")
        route_label = getattr(route, "path", "unmatched")
        method = request.method
        HTTP_REQUESTS.labels(service, method, route_label, str(status)).inc()
        HTTP_DURATION.labels(service, method, route_label).observe(time.perf_counter() - started)


def prometheus_response() -> Response:
    """Return the process registry in the Prometheus text exposition format."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def update_smoke_metrics(
    snapshot: dict[str, object], *, free_bytes: int, minimum_free_bytes: int
) -> None:
    """Refresh bounded gauges from one database snapshot before exposition."""

    raw_counts = snapshot.get("run_counts")
    counts = raw_counts if isinstance(raw_counts, dict) else {}
    for status in SMOKE_STATUSES:
        SMOKE_JOBS.labels(status).set(float(counts.get(status, 0)))

    raw_latest = snapshot.get("latest_metrics")
    latest = raw_latest if isinstance(raw_latest, dict) else {}
    for label, key in (
        ("fires", "event_count"),
        ("releases", "release_count"),
        ("particles", "particle_count"),
        ("cogs", "asset_count"),
    ):
        SMOKE_LATEST_COUNTS.labels(label).set(float(latest.get(key, 0)))
    raw_mass = latest.get("mass_kg_by_species")
    mass = raw_mass if isinstance(raw_mass, dict) else {}
    for species in ("PM25", "CO", "BC"):
        SMOKE_LATEST_MASS_KG.labels(species).set(float(mass.get(species, 0)))
    for phase, key in (
        ("resolving_inputs", "resolving_inputs_seconds"),
        ("emissions", "emissions_seconds"),
        ("transport", "transport_seconds"),
        ("processing_outputs", "processing_outputs_seconds"),
        ("publishing", "publishing_seconds"),
        ("total", "total_duration_seconds"),
    ):
        SMOKE_LATEST_DURATION_SECONDS.labels(phase).set(float(latest.get(key, 0)))
    for input_name, key in (("gfs", "gfs_input_age_seconds"), ("fire", "fire_input_age_seconds")):
        SMOKE_LATEST_INPUT_AGE_SECONDS.labels(input_name).set(float(latest.get(key, 0)))
    SMOKE_LATEST_MASS_RESIDUAL_KG.set(float(latest.get("mass_balance_residual_kg", 0)))
    for label, key in (
        ("scientific", "scientific_output_bytes"),
        ("display", "display_output_bytes"),
        ("temporary_peak", "temporary_peak_bytes"),
    ):
        SMOKE_LATEST_BYTES.labels(label).set(float(latest.get(key, 0)))
    SMOKE_LAST_COMPLETED_TIMESTAMP.set(float(snapshot.get("last_completed_epoch", 0) or 0))
    SMOKE_STORAGE_BYTES.labels("free").set(free_bytes)
    SMOKE_STORAGE_BYTES.labels("admission_reserve").set(minimum_free_bytes)
