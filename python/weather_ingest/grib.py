"""Fixture-testable GRIB2 envelope checks and optional ecCodes inspection."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from weather_ingest.models import ParsedSourceObject


class ToolUnavailableError(RuntimeError):
    pass


class GribValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GribEnvelopeInspection:
    path: Path
    message_count: int
    size_bytes: int


@dataclass(frozen=True, slots=True)
class GribMessageMetadata:
    short_name: str | None
    type_of_level: str | None
    level: str | None
    units: str | None
    data_date: int | None
    data_time: int | None
    step_range: str | None
    end_step: int | None
    step_units: int | None
    validity_date: int | None
    validity_time: int | None
    grid_type: str | None
    grid_width: int | None
    grid_height: int | None
    number_of_data_points: int | None


@dataclass(frozen=True, slots=True)
class GribMetadataInspection:
    messages: tuple[GribMessageMetadata, ...]
    tool: str


@dataclass(frozen=True, slots=True)
class GribContentValidation:
    """Decoded content identity proven for every message in one source object."""

    message_count: int
    initialization_time: datetime
    valid_time: datetime
    forecast_hour: int
    grid_type: str
    grid_width: int
    grid_height: int


@dataclass(frozen=True, slots=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(self, args: Sequence[str], *, timeout_seconds: float) -> CommandResult: ...


class SubprocessCommandRunner:
    def run(self, args: Sequence[str], *, timeout_seconds: float) -> CommandResult:
        completed = subprocess.run(
            tuple(args),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return CommandResult(tuple(args), completed.returncode, completed.stdout, completed.stderr)


def validate_grib2_envelopes(path: Path | str) -> GribEnvelopeInspection:
    source = Path(path)
    size = source.stat().st_size
    offset = 0
    message_count = 0
    with source.open("rb") as data:
        while offset < size:
            data.seek(offset)
            header = data.read(16)
            if len(header) != 16 or header[:4] != b"GRIB":
                raise GribValidationError(f"missing GRIB header at byte {offset}")
            if header[7] != 2:
                raise GribValidationError(f"unsupported GRIB edition {header[7]} at byte {offset}")
            message_length = int.from_bytes(header[8:16], "big")
            if message_length < 20 or offset + message_length > size:
                raise GribValidationError(
                    f"invalid GRIB message length {message_length} at byte {offset}"
                )
            data.seek(offset + message_length - 4)
            if data.read(4) != b"7777":
                raise GribValidationError(f"missing GRIB trailer at byte {offset}")
            offset += message_length
            message_count += 1
    if not message_count:
        raise GribValidationError("GRIB file contains no messages")
    return GribEnvelopeInspection(source, message_count, size)


class EcCodesCliInspector:
    KEYS = (
        "shortName",
        "typeOfLevel",
        "level",
        "units",
        "dataDate",
        "dataTime",
        "stepRange",
        "endStep",
        "stepUnits",
        "validityDate",
        "validityTime",
        "gridType",
        "Ni",
        "Nj",
        "numberOfDataPoints",
    )

    def __init__(
        self,
        runner: CommandRunner | None = None,
        *,
        executable: str = "grib_ls",
        timeout_seconds: float = 60.0,
    ) -> None:
        self.runner = runner or SubprocessCommandRunner()
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    def inspect(self, path: Path | str) -> GribMetadataInspection:
        is_local_runner = isinstance(self.runner, SubprocessCommandRunner)
        if is_local_runner and shutil.which(self.executable) is None:
            raise ToolUnavailableError(f"required ecCodes tool is unavailable: {self.executable}")
        result = self.runner.run(
            (self.executable, "-j", "-p", ",".join(self.KEYS), str(Path(path))),
            timeout_seconds=self.timeout_seconds,
        )
        if result.returncode:
            raise GribValidationError(
                f"ecCodes inspection failed ({result.returncode}): {result.stderr.strip()}"
            )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise GribValidationError("ecCodes returned invalid JSON") from exc
        records: Any = payload.get("messages") if isinstance(payload, dict) else payload
        if not isinstance(records, list) or not records:
            raise GribValidationError("ecCodes returned no GRIB messages")
        return GribMetadataInspection(
            messages=tuple(self._parse_record(record) for record in records),
            tool="ecCodes/grib_ls",
        )

    @staticmethod
    def _parse_record(record: object) -> GribMessageMetadata:
        if not isinstance(record, dict):
            raise GribValidationError("ecCodes message metadata must be an object")

        def optional_string(key: str) -> str | None:
            value = record.get(key)
            return None if value is None else str(value)

        def optional_integer(key: str) -> int | None:
            value = record.get(key)
            if value is None:
                return None
            if isinstance(value, str) and value.strip().lower() in {
                "missing",
                "not_found",
                "undef",
                "unknown",
                "null",
            }:
                return None
            try:
                return int(value)
            except (TypeError, ValueError) as exc:
                raise GribValidationError(f"ecCodes key {key} must be an integer") from exc

        return GribMessageMetadata(
            short_name=optional_string("shortName"),
            type_of_level=optional_string("typeOfLevel"),
            level=optional_string("level"),
            units=optional_string("units"),
            data_date=optional_integer("dataDate"),
            data_time=optional_integer("dataTime"),
            step_range=optional_string("stepRange"),
            end_step=optional_integer("endStep"),
            step_units=optional_integer("stepUnits"),
            validity_date=optional_integer("validityDate"),
            validity_time=optional_integer("validityTime"),
            grid_type=optional_string("gridType"),
            grid_width=optional_integer("Ni"),
            grid_height=optional_integer("Nj"),
            number_of_data_points=optional_integer("numberOfDataPoints"),
        )


_STEP_UNIT_SECONDS = {
    0: 60,  # minute
    1: 60 * 60,  # hour
    2: 24 * 60 * 60,  # day
    10: 3 * 60 * 60,
    11: 6 * 60 * 60,
    12: 12 * 60 * 60,
    13: 1,  # second
    14: 15 * 60,
    15: 30 * 60,
}


def _metadata_datetime(
    date_value: int | None, time_value: int | None, *, label: str
) -> datetime:
    if date_value is None or time_value is None:
        raise GribValidationError(f"GRIB {label} timestamp is missing")
    try:
        return datetime.strptime(
            f"{date_value:08d}{time_value:04d}", "%Y%m%d%H%M"
        ).replace(tzinfo=UTC)
    except (ValueError, OverflowError) as exc:
        raise GribValidationError(
            f"GRIB {label} timestamp is invalid: {date_value}/{time_value}"
        ) from exc


def _expected_grid_type(grid: str) -> str | None:
    if grid.startswith("RLatLon"):
        return "rotated_ll"
    if grid.startswith("LatLon"):
        return "regular_ll"
    return None


def validate_grib_content(
    inspection: GribMetadataInspection,
    parsed: ParsedSourceObject,
    *,
    expected_grid: str,
    expected_dimensions: tuple[int, int] | None = None,
) -> GribContentValidation:
    """Prove that decoded GRIB content matches its registered source identity.

    Parameter names, units, and vertical levels are intentionally not identity
    checks here. ECCC local parameter definitions can decode as ``unknown`` or
    expose generic level metadata even when the reviewed filename is correct.
    """

    if not inspection.messages:
        raise GribValidationError("GRIB metadata contains no messages")
    if parsed.initialization_time.tzinfo is None or parsed.valid_time.tzinfo is None:
        raise GribValidationError("registered GRIB timestamps must be timezone-aware")

    initialization_time = parsed.initialization_time.astimezone(UTC)
    valid_time = parsed.valid_time.astimezone(UTC)
    expected_lead_seconds = parsed.forecast_hour * 60 * 60
    if (valid_time - initialization_time).total_seconds() != expected_lead_seconds:
        raise GribValidationError(
            "registered valid time does not equal initialization plus forecast hour"
        )

    configured_grid_type = _expected_grid_type(expected_grid)
    observed_grid_type: str | None = None
    observed_dimensions: tuple[int, int] | None = None

    for message_number, message in enumerate(inspection.messages, start=1):
        message_initialization = _metadata_datetime(
            message.data_date, message.data_time, label="initialization"
        )
        if message_initialization != initialization_time:
            raise GribValidationError(
                f"GRIB message {message_number} initialization time "
                f"{message_initialization.isoformat()} does not match registered "
                f"{initialization_time.isoformat()}"
            )

        message_valid = _metadata_datetime(
            message.validity_date, message.validity_time, label="validity"
        )
        if message_valid != valid_time:
            raise GribValidationError(
                f"GRIB message {message_number} valid time {message_valid.isoformat()} "
                f"does not match registered {valid_time.isoformat()}"
            )

        if parsed.time_kind == "forecast":
            if message.end_step is None or message.step_units is None:
                raise GribValidationError(
                    f"GRIB message {message_number} forecast step metadata is missing"
                )
            unit_seconds = _STEP_UNIT_SECONDS.get(message.step_units)
            if unit_seconds is None:
                raise GribValidationError(
                    f"GRIB message {message_number} uses unsupported step unit code "
                    f"{message.step_units}"
                )
            observed_lead_seconds = message.end_step * unit_seconds
            if observed_lead_seconds != expected_lead_seconds:
                raise GribValidationError(
                    f"GRIB message {message_number} end step represents "
                    f"{observed_lead_seconds} seconds, expected {expected_lead_seconds}"
                )

        if message.grid_type is None:
            raise GribValidationError(f"GRIB message {message_number} grid type is missing")
        if configured_grid_type is not None and message.grid_type != configured_grid_type:
            raise GribValidationError(
                f"GRIB message {message_number} grid type {message.grid_type!r} does not "
                f"match configured {configured_grid_type!r}"
            )
        if observed_grid_type is not None and message.grid_type != observed_grid_type:
            raise GribValidationError("GRIB messages use inconsistent grid types")
        observed_grid_type = message.grid_type

        if message.grid_width is None or message.grid_height is None:
            raise GribValidationError(
                f"GRIB message {message_number} grid dimensions are missing"
            )
        dimensions = (message.grid_width, message.grid_height)
        if dimensions[0] <= 0 or dimensions[1] <= 0:
            raise GribValidationError(
                f"GRIB message {message_number} grid dimensions must be positive"
            )
        if expected_dimensions is not None and dimensions != expected_dimensions:
            raise GribValidationError(
                f"GRIB message {message_number} grid dimensions {dimensions[0]}x"
                f"{dimensions[1]} do not match configured {expected_dimensions[0]}x"
                f"{expected_dimensions[1]}"
            )
        if observed_dimensions is not None and dimensions != observed_dimensions:
            raise GribValidationError("GRIB messages use inconsistent grid dimensions")
        observed_dimensions = dimensions

        expected_point_count = dimensions[0] * dimensions[1]
        if message.number_of_data_points != expected_point_count:
            raise GribValidationError(
                f"GRIB message {message_number} reports "
                f"{message.number_of_data_points!r} data points, expected "
                f"{expected_point_count} from its dimensions"
            )

    assert observed_grid_type is not None
    assert observed_dimensions is not None
    return GribContentValidation(
        message_count=len(inspection.messages),
        initialization_time=initialization_time,
        valid_time=valid_time,
        forecast_hour=parsed.forecast_hour,
        grid_type=observed_grid_type,
        grid_width=observed_dimensions[0],
        grid_height=observed_dimensions[1],
    )
