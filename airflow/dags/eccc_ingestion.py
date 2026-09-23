"""Parameterless, configuration-driven ECCC weather-data ingestion DAGs.

Every scheduled or manually triggered run performs the same operation: inspect
the product's recent provider inventory, merge locally delivered AMQP objects,
exclude assets already published with the current conversion, and run every new
source object through download, format-specific validation, COG creation, and
catalogue publish.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from math import isfinite
from pathlib import Path
from urllib.parse import unquote, urlsplit

from airflow.sdk import dag, task
from airflow.sdk.exceptions import AirflowSkipException
from weather_ingest.adapters import create_adapter
from weather_ingest.adapters.base import ProductSourceAdapter
from weather_ingest.amqp_inbox import discover_inbox_objects, stage_inbox_file
from weather_ingest.catalogue import IngestionCatalogue
from weather_ingest.cog import GdalCogPipeline
from weather_ingest.config import ProductConfig, default_config_root, load_product_config
from weather_ingest.discovery import discover_available_objects
from weather_ingest.downloader import (
    SourceUnavailableError,
    StreamingDownloader,
    classify_source_failure,
    sha256_file,
)
from weather_ingest.grib import (
    EcCodesCliInspector,
    validate_grib2_envelopes,
    validate_grib_content,
)
from weather_ingest.http_listing import HttpsListingSource
from weather_ingest.models import ParsedSourceObject, RemoteObject, RemoteRun
from weather_ingest.netcdf import (
    GdalNetcdfInspector,
    hrepa_variable_name,
    validate_hrepa_netcdf_content,
)
from weather_ingest.orchestration import (
    IngestionDagDefinition,
    load_ingestion_dag_definitions,
)
from weather_ingest.storage import (
    processed_relative_path,
    raw_relative_path,
    resolve_under,
    staging_relative_path,
)


class _NoListingSource:
    def get_text(self, _url: str) -> str:
        raise RuntimeError("ingestion DAGs do not poll HTTPS directory listings")


def _runtime(
    product_code: str,
) -> tuple[ProductConfig, Path, ProductSourceAdapter]:
    config_root = Path(os.environ.get("WEATHER_CONFIG_ROOT", "/opt/weather/config"))
    data_root = Path(os.environ.get("WEATHER_DATA_ROOT", "/srv/weather-platform/data"))
    config = load_product_config(config_root, product_code)
    return config, data_root, create_adapter(config, _NoListingSource())


def _object_identity(
    product_code: str, request: dict[str, object]
) -> tuple[
    ProductConfig,
    Path,
    ProductSourceAdapter,
    RemoteRun,
    RemoteObject,
    ParsedSourceObject,
]:
    product_run_id = int(request["product_run_id"])
    source_object_id = int(request["source_object_id"])
    registered = IngestionCatalogue().source_object_for_processing(source_object_id)
    if (
        registered["product_code"] != product_code
        or int(registered["product_run_id"]) != product_run_id
    ):
        raise ValueError("mapped database IDs were routed to the wrong product DAG")
    config, data_root, adapter = _runtime(product_code)
    run = RemoteRun(
        product_code,
        str(registered["domain_code"]),
        registered["run_time"],
    )
    observed_url = str(registered["observed_url"])
    filename = Path(unquote(urlsplit(observed_url).path)).name
    remote = RemoteObject(
        url=observed_url,
        filename=filename,
        size_bytes=(
            int(registered["reported_size_bytes"])
            if registered["reported_size_bytes"] is not None
            else None
        ),
        size_is_exact=bool(registered["size_is_exact"]),
    )
    parsed = adapter.parse_object(remote, expected_run=run)
    field = adapter.field_for(parsed)
    if field is None or not field.download_enabled or not field.processing_enabled:
        raise ValueError("mapped request field no longer matches validated configuration")
    return config, data_root, adapter, run, remote, parsed


def _published_asset_exists(
    data_root: Path, relative_path: Path, parsed: ParsedSourceObject
) -> bool:
    destination = resolve_under(data_root, relative_path)
    if not destination.is_file():
        return False
    if parsed.grid.startswith("RLatLon"):
        return Path(str(destination) + ".aux.xml").is_file()
    return True


def build_ingestion_dag(definition: IngestionDagDefinition):
    """Create one parameterless DAG from a validated product configuration route."""

    product_code = definition.product_code

    @dag(
        dag_id=definition.dag_id,
        schedule=definition.schedule,
        start_date=datetime(2026, 1, 1),
        catchup=False,
        max_active_runs=1,
        tags=[
            "eccc",
            product_code,
            definition.product_kind,
            "automatic-discovery",
            "config-driven",
        ],
    )
    def configured_ingestion():
        @task(
            retries=2,
            retry_delay=timedelta(minutes=2),
            retry_exponential_backoff=True,
            max_retry_delay=timedelta(minutes=10),
        )
        def discover_and_register() -> dict[str, object]:
            config, data_root, adapter = _runtime(product_code)
            catalogue = IngestionCatalogue()
            now = datetime.now().astimezone()
            discovery_limit = definition.maximum_objects_per_run
            # Keep part of every bounded batch available for newly published
            # objects. Otherwise a large recovery backlog can indefinitely
            # hide new forecast hours and newly enabled fields.
            recovery_limit = max(1, discovery_limit * 3 // 4)
            recovered_requests = catalogue.recover_source_requests(
                product_code,
                limit=recovery_limit,
            )
            candidate_runs = adapter.list_candidate_runs(
                now,
                lookback_hours=config.discovery.retry_window_hours,
            )
            available_slots = catalogue.available_processing_slots(
                product_code,
                definition.domain_code,
                (run.initialization_time for run in candidate_runs),
            )
            inbox_objects = discover_inbox_objects(
                data_root,
                config,
                adapter,
                limit=discovery_limit,
            )
            with HttpsListingSource(
                user_agent="weather-platform-ingestion/0.1"
            ) as listing_source:
                inventory_adapter = create_adapter(config, listing_source)
                inventory_objects = discover_available_objects(
                    config,
                    inventory_adapter,
                    now=now,
                    data_root=data_root,
                    available_slots=available_slots,
                    limit=discovery_limit,
                )

            # Prefer a completed AMQP delivery over fetching the same immutable
            # object again from HTTPS.
            discovered: dict[
                str, tuple[ParsedSourceObject, str | None]
            ] = {}
            for item in inventory_objects:
                discovered[adapter.canonical_object_key(item.parsed.remote)] = (
                    item.parsed,
                    None,
                )
            for item in inbox_objects:
                discovered[adapter.canonical_object_key(item.parsed.remote)] = (
                    item.parsed,
                    str(item.local_path),
                )
            registered: list[
                tuple[int, ParsedSourceObject, str | None, int]
            ] = []
            product_run_ids: list[int] = [
                int(request["product_run_id"]) for request in recovered_requests
            ]
            grouped: dict[
                tuple[str, datetime], list[tuple[ParsedSourceObject, str | None]]
            ] = {}
            for parsed, inbox_path in discovered.values():
                key = (parsed.domain_code, parsed.initialization_time)
                grouped.setdefault(key, []).append((parsed, inbox_path))
            for (_domain_code, _run_time), items in grouped.items():
                parsed_first = items[0][0]
                run = RemoteRun(
                    product_code,
                    parsed_first.domain_code,
                    parsed_first.initialization_time,
                )
                product_run_id, source_ids = catalogue.register_manifest(
                    config,
                    run,
                    (parsed for parsed, _inbox_path in items),
                    source="automatic_inventory",
                )
                product_run_ids.append(product_run_id)
                registered.extend(
                    (
                        product_run_id,
                        parsed,
                        inbox_path,
                        source_ids[parsed.remote.filename],
                    )
                    for parsed, inbox_path in items
                )

            available_conversions = catalogue.available_asset_conversions(product_run_ids)
            requests_by_source_id: dict[int, dict[str, object]] = {
                int(request["source_object_id"]): dict(request)
                for request in recovered_requests
            }
            skipped = 0
            for product_run_id, parsed, inbox_path, source_object_id in registered:
                field = adapter.field_for(parsed)
                if field is None:
                    raise ValueError("registered source field is absent from configuration")
                relative_output = processed_relative_path(parsed, field)
                if (
                    available_conversions.get(relative_output.as_posix())
                    == field.conversion_key
                    and _published_asset_exists(data_root, relative_output, parsed)
                ):
                    skipped += 1
                    if inbox_path is not None:
                        Path(inbox_path).unlink(missing_ok=True)
                    requests_by_source_id.pop(source_object_id, None)
                    continue
                request: dict[str, object] = {
                    "product_run_id": product_run_id,
                    "source_object_id": source_object_id,
                }
                if inbox_path is not None:
                    request["inbox_path"] = inbox_path
                requests_by_source_id[source_object_id] = request
            requests = list(requests_by_source_id.values())[:discovery_limit]
            requested_run_ids = {
                int(request["product_run_id"]) for request in requests
            }
            logging.getLogger("airflow.task").info(
                "Queued %d source object(s), including %d recoverable object(s); "
                "reserved %d slot(s) for new discovery; skipped %d already "
                "available asset(s)",
                len(requests),
                len(recovered_requests),
                discovery_limit - recovery_limit,
                skipped,
            )
            return {
                "requests": requests,
                "product_run_ids": sorted(requested_run_ids),
                "skipped": skipped,
            }

        @task
        def requests_for_mapping(prepared: dict[str, object]) -> list[dict[str, object]]:
            requests = prepared.get("requests")
            if not isinstance(requests, list):
                raise ValueError("prepared ingestion request list is invalid")
            return requests

        @task(
            pool="eccc_downloads",
            retries=4,
            retry_delay=timedelta(minutes=2),
            retry_exponential_backoff=True,
            max_retry_delay=timedelta(minutes=20),
        )
        def download_source(request: dict[str, object]) -> dict[str, object]:
            config, data_root, _adapter, _run, remote, parsed = _object_identity(
                product_code, request
            )
            catalogue = IngestionCatalogue()
            source_object_id = int(request["source_object_id"])
            catalogue.begin_download(source_object_id)
            try:
                relative_raw = raw_relative_path(parsed)
                if request.get("inbox_path") is not None:
                    inbox_root = (data_root / "amqp" / "inbox").resolve()
                    inbox_path = Path(str(request["inbox_path"])).resolve()
                    inbox_path.relative_to(inbox_root)
                    destination = resolve_under(data_root, relative_raw)
                    stage_inbox_file(inbox_path, destination)
                    size_bytes = destination.stat().st_size
                    source_sha256 = sha256_file(destination)
                    local_path = destination
                    reused_existing = False
                else:
                    with StreamingDownloader(
                        data_root,
                        minimum_free_bytes=config.limits.minimum_free_bytes,
                    ) as downloader:
                        result = downloader.download(remote, relative_raw)
                    size_bytes = result.size_bytes
                    source_sha256 = result.sha256
                    local_path = result.path
                    reused_existing = result.reused_existing
                catalogue.mark_downloaded(
                    source_object_id,
                    relative_path=local_path.relative_to(data_root).as_posix(),
                    size_bytes=size_bytes,
                    sha256=source_sha256,
                )
                logging.getLogger("airflow.task").info(
                    "%s source object %s",
                    "Reused" if reused_existing else "Staged",
                    remote.filename,
                )
            except Exception as error:
                failure = classify_source_failure(
                    error,
                    reference_time=parsed.initialization_time,
                    now=datetime.now(UTC),
                    retry_window_hours=config.discovery.retry_window_hours,
                )
                catalogue.mark_source_failed(source_object_id, failure)
                if isinstance(failure, SourceUnavailableError):
                    # Explicitly skip this absent payload and its transforms, not
                    # the whole batch. Finalization retains the failed-source
                    # count and partial coverage; no placeholder asset is made.
                    raise AirflowSkipException(str(failure)) from error
                raise
            return {
                **request,
                "local_path": str(local_path),
                "source_sha256": source_sha256,
            }

        @task(trigger_rule="none_failed")
        def validate_source(downloaded: dict[str, object]) -> dict[str, object]:
            config, _data_root, _adapter, _run, _remote, parsed = _object_identity(
                product_code, downloaded
            )
            path = Path(str(downloaded["local_path"]))
            domain = config.domain(parsed.domain_code)
            dimensions = (
                (domain.grid_width, domain.grid_height)
                if domain.grid_width is not None and domain.grid_height is not None
                else None
            )
            if parsed.data_format == "grib2":
                envelope = validate_grib2_envelopes(path)
                metadata = EcCodesCliInspector().inspect(path)
                if envelope.message_count != len(metadata.messages):
                    raise ValueError("GRIB envelope and ecCodes message counts disagree")
                validate_grib_content(
                    metadata,
                    parsed,
                    expected_grid=domain.grid,
                    expected_dimensions=dimensions,
                )
                return {
                    **downloaded,
                    "source_message_count": envelope.message_count,
                }
            if parsed.data_format == "nc" and parsed.product_code == "hrepa":
                if dimensions is None:
                    raise ValueError("HREPA NetCDF dimensions must be configured")
                field = _adapter.field_for(parsed)
                if field is None:
                    raise ValueError("registered NetCDF field is absent from configuration")
                inspection = GdalNetcdfInspector().inspect(
                    path,
                    variable_name=hrepa_variable_name(parsed),
                )
                validate_hrepa_netcdf_content(
                    inspection,
                    parsed,
                    expected_dimensions=dimensions,
                    expected_unit=field.source.expected_unit,
                )
                return {
                    **downloaded,
                    "source_message_count": inspection.band_count,
                    "raster_source": inspection.dataset_name,
                }
            raise ValueError(
                f"no validation pipeline exists for {parsed.product_code}/{parsed.data_format}"
            )

        @task(pool="cog_transforms", retries=1, retry_delay=timedelta(minutes=1))
        def create_cog(validated: dict[str, object]) -> dict[str, int]:
            config, data_root, _adapter, _run, _remote, parsed = _object_identity(
                product_code, validated
            )
            field = _adapter.field_for(parsed)
            if field is None:
                raise ValueError("registered source field is absent from configuration")
            staging = resolve_under(data_root, staging_relative_path(parsed, field))
            destination = resolve_under(data_root, processed_relative_path(parsed, field))
            metadata = GdalCogPipeline().create(
                Path(str(validated["local_path"])),
                staging,
                destination,
                field,
                source_dataset=(
                    str(validated["raster_source"])
                    if validated.get("raster_source") is not None
                    else None
                ),
                replace_existing=True,
            )
            if metadata.wgs84_bounds is None:
                raise ValueError("processed COG has no WGS84 extent")
            domain = config.domain(parsed.domain_code)
            expected_dimensions = (domain.grid_width, domain.grid_height)
            if (
                None not in expected_dimensions
                and (
                    metadata.width,
                    metadata.height,
                )
                != expected_dimensions
            ):
                raise ValueError("processed COG dimensions do not match the configured grid")
            if metadata.band_count != 1:
                raise ValueError("processed display COG must contain exactly one selected band")
            if metadata.nodata_value != field.nodata_value:
                raise ValueError("processed COG nodata does not match field configuration")
            if metadata.minimum_value is None or metadata.maximum_value is None:
                raise ValueError("processed COG statistics are required")
            if not isfinite(metadata.minimum_value) or not isfinite(metadata.maximum_value):
                raise ValueError("processed COG statistics must be finite")
            if field.canonical_variable == "precipitation" and metadata.minimum_value < -1e-6:
                raise ValueError("processed precipitation COG contains negative values")
            processed_sha256 = sha256_file(destination)
            asset_id = IngestionCatalogue().register_asset(
                product_run_id=int(validated["product_run_id"]),
                parsed=parsed,
                field_code=field.code,
                relative_path=destination.relative_to(data_root).as_posix(),
                file_size_bytes=destination.stat().st_size,
                sha256=processed_sha256,
                projection=metadata.coordinate_system,
                bounds=metadata.wgs84_bounds,
                width=metadata.width,
                height=metadata.height,
                band_count=metadata.band_count,
                nodata_value=metadata.nodata_value,
                minimum_value=metadata.minimum_value,
                maximum_value=metadata.maximum_value,
                source_sha256=str(validated["source_sha256"]),
                conversion_key=field.conversion_key,
            )
            inbox_value = validated.get("inbox_path")
            if inbox_value is not None:
                inbox_root = (data_root / "amqp" / "inbox").resolve()
                inbox_path = Path(str(inbox_value)).resolve()
                inbox_path.relative_to(inbox_root)
                inbox_path.unlink(missing_ok=True)
            # The reduce task needs only IDs. Paths, checksums, and raster metadata
            # already live in PostgreSQL and must not be duplicated in XCom.
            return {
                "product_run_id": int(validated["product_run_id"]),
                "asset_id": asset_id,
            }

        @task(trigger_rule="none_failed")
        def finalize_run(prepared: dict[str, object]) -> dict[str, object]:
            config, _data_root, _adapter = _runtime(product_code)
            prepared_run_ids = prepared.get("product_run_ids")
            if not isinstance(prepared_run_ids, list):
                raise ValueError("prepared product run ID list is invalid")
            run_ids = {int(value) for value in prepared_run_ids}
            results = [
                dict(
                    IngestionCatalogue().finalize_run(
                        run_id, config.visibility.required_field_codes
                    )
                )
                for run_id in sorted(run_ids)
            ]
            return {
                "status": "complete" if results else "no_new_data",
                "runs": results,
            }

        prepared = discover_and_register()
        requests = requests_for_mapping(prepared)
        downloaded = download_source.expand(request=requests)
        validated = validate_source.expand(downloaded=downloaded)
        processed = create_cog.expand(validated=validated)
        finalized = finalize_run(prepared)
        processed >> finalized

    return configured_ingestion()


_CONFIG_ROOT = Path(os.environ.get("WEATHER_CONFIG_ROOT", str(default_config_root())))
INGESTION_DAG_DEFINITIONS = load_ingestion_dag_definitions(_CONFIG_ROOT)
for _definition in INGESTION_DAG_DEFINITIONS:
    globals()[_definition.dag_id] = build_ingestion_dag(_definition)
