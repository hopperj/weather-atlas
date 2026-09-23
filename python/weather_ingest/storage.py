"""Deterministic local-storage paths independent of database identifiers."""

from __future__ import annotations

import re
from pathlib import Path

from weather_ingest.config import FieldConfig
from weather_ingest.models import ParsedSourceObject

_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _safe_segment(value: str, label: str) -> str:
    if not _SEGMENT_RE.fullmatch(value) or value in {".", ".."}:
        raise ValueError(f"unsafe {label}: {value!r}")
    return value


def raw_relative_path(parsed: ParsedSourceObject) -> Path:
    initialization = parsed.initialization_time
    filename = _safe_segment(parsed.remote.filename, "source filename")
    prefix = Path(
        "raw",
        "eccc",
        _safe_segment(parsed.product_code, "product code"),
        _safe_segment(parsed.domain_code, "domain code"),
        f"{initialization:%Y}",
        f"{initialization:%m}",
        f"{initialization:%d}",
        f"{initialization:%H}",
    )
    if parsed.time_kind == "forecast":
        return prefix / f"f{parsed.forecast_hour:03d}" / filename
    if parsed.accumulation_hours is None or parsed.analysis_revision is None:
        raise ValueError("analysis storage paths require interval and revision metadata")
    return (
        prefix
        / f"a{parsed.accumulation_hours:03d}h"
        / _safe_segment(parsed.analysis_revision, "analysis revision")
        / filename
    )


def processed_relative_path(parsed: ParsedSourceObject, field: FieldConfig) -> Path:
    initialization = parsed.initialization_time
    prefix = Path(
        "processed",
        "eccc",
        _safe_segment(parsed.product_code, "product code"),
        _safe_segment(parsed.domain_code, "domain code"),
        f"{initialization:%Y}",
        f"{initialization:%m}",
        f"{initialization:%d}",
        f"{initialization:%H}",
        _safe_segment(field.code, "field code"),
        _safe_segment(field.level_code, "level code"),
    )
    if parsed.time_kind == "forecast":
        return prefix / f"f{parsed.forecast_hour:03d}.tif"
    if parsed.accumulation_hours is None:
        raise ValueError("analysis storage paths require an accumulation interval")
    return prefix / f"a{parsed.accumulation_hours:03d}h.tif"


def canonical_source_key(parsed: ParsedSourceObject) -> str:
    """Return a stable object identity without transport aliases or database IDs."""

    if parsed.time_kind == "forecast":
        time_segment = f"{parsed.initialization_time:%Y%m%dT%HZ}/f{parsed.forecast_hour:03d}"
    else:
        if parsed.accumulation_hours is None or parsed.analysis_revision is None:
            raise ValueError("analysis source identity requires interval and revision metadata")
        time_segment = (
            f"valid_{parsed.valid_time:%Y%m%dT%HZ}/"
            f"a{parsed.accumulation_hours:03d}h/"
            f"{_safe_segment(parsed.analysis_revision, 'analysis revision')}"
        )
    return (
        f"eccc/{_safe_segment(parsed.product_code, 'product code')}/"
        f"{_safe_segment(parsed.domain_code, 'domain code')}/{time_segment}/"
        f"{_safe_segment(parsed.remote.filename, 'source filename')}"
    )


def staging_relative_path(parsed: ParsedSourceObject, field: FieldConfig) -> Path:
    destination = processed_relative_path(parsed, field)
    return Path("staging", *destination.parts[1:]).with_suffix(".tif.part")


def resolve_under(data_root: Path | str, relative_path: Path | str) -> Path:
    root = Path(data_root).expanduser().resolve()
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"storage path must be safe and relative: {relative}")
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"storage path escapes data root: {relative}")
    return candidate
