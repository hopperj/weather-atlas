"""Operator CLI for configuration, inventory, and runtime diagnostics."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from weather_ingest.adapters import adapter_type_for
from weather_ingest.config import default_config_root, load_enabled_products, load_product_config
from weather_ingest.http_listing import FixtureListingSource, HttpsListingSource
from weather_ingest.inventory import InventoryReport, inspect_run
from weather_ingest.models import InventoryDisposition, RemoteRun
from weather_ingest.orchestration import build_manual_trigger_requests
from weather_ingest.tools import inspect_geospatial_tools


def parse_run_time(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    try:
        result = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("run must be an ISO 8601 timestamp") from exc
    if result.tzinfo is None:
        raise argparse.ArgumentTypeError("run must include a UTC offset or Z")
    result = result.astimezone(UTC)
    if result.minute or result.second or result.microsecond:
        raise argparse.ArgumentTypeError("run must be on an exact UTC hour")
    return result


def _forecast_hour(value: str) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("forecast hour must be an integer") from exc
    if not 0 <= result <= 999:
        raise argparse.ArgumentTypeError("forecast hour must be between 0 and 999")
    return result


def _add_inventory_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--product", required=True)
    parser.add_argument(
        "--domain", help="domain code (defaults to the product's configured domain)"
    )
    parser.add_argument(
        "--run",
        "--reference-time",
        dest="run",
        required=True,
        type=parse_run_time,
        help="forecast initialization time or analysis valid/end time",
    )
    parser.add_argument(
        "--forecast-hour",
        action="append",
        type=_forecast_hour,
        dest="forecast_hours",
        help="inspect only this forecast hour; repeat to select more than one",
    )
    parser.add_argument(
        "--today-alias",
        action="store_true",
        help="use the rolling /today alias instead of the stable dated archive path",
    )
    parser.add_argument(
        "--listing-fixture",
        type=Path,
        help="read NNN.html listings from this directory instead of using the network",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="weather-ingest")
    parser.add_argument(
        "--config-root",
        type=Path,
        default=default_config_root(),
        help="validated configuration root (default: WEATHER_CONFIG_ROOT or repository config)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("validate-config", help="load and validate every enabled product")
    commands.add_parser("check-tools", help="report optional ecCodes and GDAL command availability")

    inspect_parser = commands.add_parser(
        "inspect-source", help="perform an explicit ad hoc HTTPS inventory of one model run"
    )
    _add_inventory_arguments(inspect_parser)
    inspect_parser.add_argument("--format", choices=("text", "json"), default="text")
    inspect_parser.add_argument(
        "--summary-only", action="store_true", help="omit per-object details from JSON output"
    )

    trigger_parser = commands.add_parser(
        "build-trigger",
        help="inventory one run and emit bounded Airflow DAG trigger requests",
    )
    _add_inventory_arguments(trigger_parser)
    return parser


def _human_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    number = float(value)
    for suffix in ("B", "KiB", "MiB", "GiB", "TiB"):
        if number < 1024 or suffix == "TiB":
            return f"{number:.1f} {suffix}"
        number /= 1024
    raise AssertionError("unreachable")


def _format_report(report: InventoryReport) -> str:
    time_label = "Initialization" if report.product_kind == "forecast" else "Analysis valid/end"
    offset_label = "Forecast hours" if report.product_kind == "forecast" else "Time offsets"
    lines = [
        f"Product: {report.product_code} ({report.product_kind})",
        f"{time_label}: {report.initialization_time:%Y-%m-%d %HZ}",
        f"Domain: {report.domain_code}",
        f"{offset_label}: " + ", ".join(f"{hour:03d}" for hour in report.inspected_forecast_hours),
        f"Remote objects: {report.remote_object_count} "
        f"({_human_bytes(report.remote_bytes_observed)} observed)",
        f"Enabled objects: {report.enabled_object_count} "
        f"({_human_bytes(report.enabled_bytes_observed)} observed)",
        f"Configured but disabled/ignored: {report.configured_ignored_count}",
        f"Unknown objects: {report.unknown_object_count}",
        f"Parser errors: {report.parser_error_count}",
        f"Unknown sizes: {report.unknown_size_count}",
        f"Estimated enabled bytes/run: {_human_bytes(report.estimated_enabled_bytes_per_run)}",
        f"Estimated enabled raw bytes/day: "
        f"{_human_bytes(report.estimated_enabled_raw_bytes_per_day)}",
        f"Estimated processed bytes/day: {_human_bytes(report.estimated_processed_bytes_per_day)}",
    ]
    if report.missing_enabled_field_hours:
        lines.append(
            "Missing enabled field-hours: "
            + ", ".join(
                f"{field}@f{hour:03d}" for field, hour in report.missing_enabled_field_hours
            )
        )
    notable = [
        item
        for item in report.objects
        if item.disposition in {InventoryDisposition.UNKNOWN, InventoryDisposition.PARSER_ERROR}
    ]
    if notable:
        lines.append("Unknown/parser-error objects (first 50):")
        lines.extend(
            f"  {item.disposition.value}: {item.remote.filename} — {item.reason}"
            for item in notable[:50]
        )
    return "\n".join(lines)


def run_cli(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate-config":
        products = load_enabled_products(args.config_root)
        for product in products:
            print(f"{product.code}: valid ({len(product.fields)} configured fields)")
        return 0
    if args.command == "check-tools":
        statuses = inspect_geospatial_tools()
        for status in statuses:
            state = "available" if status.available else "missing"
            suffix = f" — {status.version}" if status.version else ""
            print(f"{status.name}: {state}{suffix}")
        return 0 if all(status.available for status in statuses) else 1
    if args.command not in {"inspect-source", "build-trigger"}:
        raise AssertionError(f"unhandled command {args.command}")

    config = load_product_config(args.config_root, args.product)
    adapter_type = adapter_type_for(config)
    source = (
        FixtureListingSource(args.listing_fixture) if args.listing_fixture else HttpsListingSource()
    )
    try:
        adapter = adapter_type(config, source)
        domain_code = args.domain or config.domains[0].code
        run = RemoteRun(config.code, domain_code, args.run)
        hours = tuple(args.forecast_hours) if args.forecast_hours else None
        report = inspect_run(adapter, run, forecast_hours=hours, use_today_alias=args.today_alias)
    finally:
        close = getattr(source, "close", None)
        if close is not None:
            close()

    if args.command == "build-trigger":
        requests = build_manual_trigger_requests(report, config)
        print(
            json.dumps(
                {
                    "dag_id": f"eccc_{config.code}_ingest",
                    "requests": list(requests),
                },
                indent=2,
            )
        )
    elif args.format == "json":
        print(json.dumps(report.to_dict(include_objects=not args.summary_only), indent=2))
    else:
        print(_format_report(report))
    return 0


def main() -> int:
    try:
        return run_cli()
    except (OSError, ValueError) as exc:
        print(f"weather-ingest: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
