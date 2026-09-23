"""Discover completed ECCC files delivered locally by Sarracenia."""

from __future__ import annotations

import errno
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from weather_ingest.adapters.base import ProductSourceAdapter
from weather_ingest.config import ProductConfig
from weather_ingest.models import ParsedSourceObject, RemoteObject


@dataclass(frozen=True, slots=True)
class InboxObject:
    parsed: ParsedSourceObject
    field_code: str
    local_path: Path


def discover_inbox_objects(
    data_root: Path,
    config: ProductConfig,
    adapter: ProductSourceAdapter,
    *,
    limit: int,
) -> tuple[InboxObject, ...]:
    """Return a bounded set of complete, processing-enabled local deliveries."""

    if limit < 1:
        raise ValueError("inbox discovery limit must be positive")
    inbox_root = data_root / "amqp" / "inbox"
    if not inbox_root.is_dir():
        return ()

    discovered: list[InboxObject] = []
    for path in sorted(inbox_root.rglob("*.grib2")):
        if not path.is_file() or path.name.endswith(".part"):
            continue
        relative = path.relative_to(inbox_root)
        remote = RemoteObject(
            url="https://dd.weather.gc.ca/" + quote(relative.as_posix(), safe="/._-"),
            filename=path.name,
            size_bytes=path.stat().st_size,
            size_is_exact=True,
        )
        try:
            parsed = adapter.parse_object(remote)
        except ValueError:
            continue
        field = adapter.field_for(parsed)
        if (
            parsed.product_code != config.code
            or field is None
            or not field.download_enabled
            or not field.processing_enabled
            or parsed.data_format != "grib2"
        ):
            continue
        discovered.append(InboxObject(parsed, field.code, path))
        if len(discovered) == limit:
            break
    return tuple(discovered)


def stage_inbox_file(source: Path, destination: Path) -> None:
    """Publish an inbox file at its canonical raw path without consuming it."""

    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file():
        return
    staging = destination.with_name(destination.name + ".part")
    staging.unlink(missing_ok=True)
    try:
        try:
            os.link(source, staging)
        except OSError as error:
            if error.errno not in {
                errno.EXDEV,
                errno.EPERM,
                errno.EACCES,
                errno.ENOTSUP,
            }:
                raise
            with source.open("rb") as source_file, staging.open("xb") as output_file:
                shutil.copyfileobj(source_file, output_file, length=1024 * 1024)
                output_file.flush()
                os.fsync(output_file.fileno())
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)
