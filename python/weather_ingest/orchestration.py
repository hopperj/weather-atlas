"""Pure, Airflow-independent routing and request validation for ingestion DAGs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from weather_ingest.adapters import ADAPTER_TYPES
from weather_ingest.adapters.base import ProductSourceAdapter
from weather_ingest.config import ProductConfig, load_enabled_products
from weather_ingest.inventory import InventoryReport
from weather_ingest.models import ParsedSourceObject, RemoteObject, RemoteRun

MAX_MANUAL_REQUEST_BYTES = 256 * 1024


@dataclass(frozen=True, slots=True)
class IngestionDagDefinition:
    """The stable DAG identity derived from one enabled product configuration."""

    product_code: str
    adapter_code: str
    dag_id: str
    domain_code: str
    product_kind: str
    schedule: str
    maximum_objects_per_run: int


@dataclass(frozen=True, slots=True)
class PreparedSourceObject:
    parsed: ParsedSourceObject
    field_code: str


@dataclass(frozen=True, slots=True)
class PreparedManualBatch:
    run: RemoteRun
    objects: tuple[PreparedSourceObject, ...]


def build_manual_trigger_requests(
    report: InventoryReport,
    config: ProductConfig,
) -> tuple[dict[str, Any], ...]:
    """Convert a reviewed inventory into bounded Airflow trigger requests."""

    if report.product_code != config.code:
        raise ValueError(
            f"inventory product {report.product_code!r} does not match configuration "
            f"{config.code!r}"
        )
    if report.domain_code not in {domain.code for domain in config.domains}:
        raise ValueError(
            f"inventory domain {report.domain_code!r} is not configured for {config.code!r}"
        )

    objects: list[dict[str, Any]] = []
    for item in report.objects:
        if item.field_code is None:
            continue
        field = config.field(item.field_code)
        if (
            item.parsed is None
            or not field.download_enabled
            or not field.processing_enabled
            or not field.availability.includes(item.parsed.forecast_hour)
            or item.parsed.data_format != "grib2"
        ):
            continue
        objects.append(
            {
                "url": item.remote.url,
                "filename": item.remote.filename,
                "size_bytes": item.remote.size_bytes,
                "size_is_exact": item.remote.size_is_exact,
            }
        )

    if not objects:
        raise ValueError(
            f"inventory for {config.code!r} contains no processing-enabled GRIB2 objects"
        )

    limit = config.limits.maximum_objects_per_manual_run
    run_time = report.initialization_time.astimezone(UTC).isoformat().replace("+00:00", "Z")
    requests: list[dict[str, Any]] = []
    for start in range(0, len(objects), limit):
        request = {
            "product": config.code,
            "domain": report.domain_code,
            "run": run_time,
            "objects": objects[start : start + limit],
        }
        if len(json.dumps(request, separators=(",", ":")).encode("utf-8")) > (
            MAX_MANUAL_REQUEST_BYTES
        ):
            raise ValueError(
                "generated trigger request exceeds the bounded XCom request size; "
                "inspect fewer forecast hours"
            )
        requests.append(request)
    return tuple(requests)


def load_ingestion_dag_definitions(
    config_root: Path | str,
) -> tuple[IngestionDagDefinition, ...]:
    """Build deterministic DAG definitions from supported ECCC YAML files.

    Forecast GRIB products, deterministic GRIB precipitation analyses, and the
    reviewed HREPA NetCDF ensemble product use a bounded format-specific
    processing workflow.
    """

    definitions: list[IngestionDagDefinition] = []
    for config in load_enabled_products(config_root):
        if config.provider != "eccc":
            continue
        supported_kind = (
            config.kind == "forecast" and config.source_formats == ("grib2",)
        ) or (
            config.kind == "analysis" and config.source_formats == ("grib2",)
        ) or (
            config.code == "hrepa"
            and config.kind == "ensemble_analysis"
            and config.source_formats == ("nc",)
        )
        if not supported_kind:
            continue
        if config.adapter not in ADAPTER_TYPES:
            raise ValueError(
                f"enabled ECCC forecast {config.code!r} has no registered adapter "
                f"{config.adapter!r}"
            )
        definitions.append(
            IngestionDagDefinition(
                product_code=config.code,
                adapter_code=config.adapter,
                dag_id=f"eccc_{config.code}_ingest",
                domain_code=config.domains[0].code,
                product_kind=config.kind,
                schedule=config.discovery.reconciliation_schedule,
                maximum_objects_per_run=config.discovery.maximum_objects_per_run,
            )
        )
    dag_ids = [definition.dag_id for definition in definitions]
    if len(dag_ids) != len(set(dag_ids)):
        raise ValueError("enabled product configuration generated duplicate DAG IDs")
    return tuple(sorted(definitions, key=lambda definition: definition.product_code))


def _parse_run_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("dag_run.conf.run must be an ISO 8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("dag_run.conf.run must be an ISO 8601 UTC timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("dag_run.conf.run must include a UTC offset or Z")
    parsed = parsed.astimezone(UTC)
    if parsed.minute or parsed.second or parsed.microsecond:
        raise ValueError("dag_run.conf.run must be on an exact UTC hour")
    return parsed


def _request_size(objects: object) -> int:
    try:
        serialized = json.dumps(objects, separators=(",", ":"), ensure_ascii=True)
    except (TypeError, ValueError) as exc:
        raise ValueError("dag_run.conf.objects must contain JSON-compatible values") from exc
    return len(serialized.encode("utf-8"))


def _optional_size(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("source object size_bytes must be a non-negative integer or null")
    return value


def prepare_manual_batch(
    product_code: str,
    conf: dict[str, Any],
    config: ProductConfig,
    adapter: ProductSourceAdapter,
) -> PreparedManualBatch:
    """Validate a bounded, inventory-reviewed manual batch before any writes.

    HTTPS listings remain an explicit operator activity. The DAG consumes only
    immutable objects copied from a reviewed inventory report and never performs
    systematic directory polling itself.
    """

    if config.code != product_code:
        raise ValueError(
            f"DAG product {product_code!r} does not match configuration {config.code!r}"
        )
    requested_product = conf.get("product")
    if requested_product is not None and requested_product != product_code:
        raise ValueError(f"dag_run.conf.product must be {product_code!r} when supplied")

    run_time = _parse_run_time(conf.get("run"))
    domain_code = conf.get("domain", config.domains[0].code)
    if not isinstance(domain_code, str):
        raise ValueError("dag_run.conf.domain must be a product domain code")
    run = RemoteRun(product_code, domain_code, run_time)
    # This validates the domain, cadence, and product before object parsing.
    adapter.expected_manifest(run)

    object_values = conf.get("objects")
    if not isinstance(object_values, list) or not object_values:
        raise ValueError("dag_run.conf.objects must be a non-empty inventory-reviewed list")
    if len(object_values) > config.limits.maximum_objects_per_manual_run:
        raise ValueError("manual run exceeds the configured object mapping boundary")
    if _request_size(object_values) > MAX_MANUAL_REQUEST_BYTES:
        raise ValueError("manual run exceeds the bounded XCom request size")

    prepared: list[PreparedSourceObject] = []
    seen_filenames: set[str] = set()
    for value in object_values:
        if not isinstance(value, dict):
            raise ValueError("each source object must be a JSON object")
        url = value.get("url")
        filename = value.get("filename")
        if not isinstance(url, str) or not url or len(url) > 2048:
            raise ValueError("source object url must be a non-empty bounded string")
        if not isinstance(filename, str) or not filename or len(filename) > 512:
            raise ValueError("source object filename must be a non-empty bounded string")
        if filename in seen_filenames:
            raise ValueError(f"duplicate source object in manual run: {filename}")
        seen_filenames.add(filename)

        size_is_exact = value.get("size_is_exact", False)
        if not isinstance(size_is_exact, bool):
            raise ValueError("source object size_is_exact must be a boolean")
        remote = RemoteObject(
            url=url,
            filename=filename,
            size_bytes=_optional_size(value.get("size_bytes")),
            size_is_exact=size_is_exact,
        )
        parsed = adapter.parse_object(remote, expected_run=run)
        field = adapter.field_for(parsed)
        if (
            field is None
            or not field.download_enabled
            or not field.processing_enabled
            or not field.availability.includes(parsed.forecast_hour)
            or parsed.data_format != "grib2"
            or parsed.data_format not in config.source_formats
        ):
            raise ValueError(f"source field is not enabled for processing: {remote.filename}")
        prepared.append(PreparedSourceObject(parsed=parsed, field_code=field.code))
    return PreparedManualBatch(run=run, objects=tuple(prepared))
