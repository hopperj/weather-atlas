"""Collect GeoMet observation images on the ETL server; publish local COGs in PostgreSQL.

The serving API never calls GeoMet. Coverage and request/storage budgets are operator
configuration. RGB images are for display only and cannot supply scalar point samples.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import httpx
import psycopg
import rasterio
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from rasterio.enums import ColorInterp
from rasterio.io import MemoryFile
from rasterio.shutil import copy as raster_copy
from rasterio.transform import from_bounds
from weather_common.db import SqlFileLoader

GEOMET = "https://geo.weather.gc.ca/geomet"
SOURCES = {
    "radar_rain": "RADAR_1KM_RRAI",
    "satellite_natural": "GOES-East_1km_NaturalColor",
    "satellite_ir": "GOES-East_2km_NightIR",
}
NS = {"w": "http://www.opengis.net/wms"}


def stamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Observation time must include a UTC offset")
    return result.astimezone(UTC)


def available_times(xml: bytes, layer: str, now: datetime, lookback_hours: int) -> list[datetime]:
    """Parse only the selected layer's advertised time dimension, never synthesize cadence."""
    if len(xml) > 8 * 1024**2 or b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise ValueError("Unsafe or oversized capabilities document")
    root = ET.fromstring(xml)
    dimension = None
    for node in root.findall(".//w:Layer", NS):
        if node.findtext("w:Name", namespaces=NS) == layer:
            dimension = node.find("w:Dimension[@name='time']", NS)
            break
    if dimension is None or not dimension.text:
        raise ValueError(f"Missing time dimension for {layer}")
    times = set()
    for item in dimension.text.split(","):
        parts = item.strip().split("/")
        if len(parts) == 1:
            times.add(stamp(parts[0]))
        elif len(parts) == 3:
            start, end = stamp(parts[0]), stamp(parts[1])
            match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", parts[2])
            if not match:
                raise ValueError("Unsupported time interval")
            seconds = sum(
                int(value or 0) * factor
                for value, factor in zip(match.groups(), (3600, 60, 1), strict=True)
            )
            if seconds <= 0 or end < start or (end - start).total_seconds() / seconds > 10000:
                raise ValueError("Invalid or unbounded time interval")
            step = timedelta(seconds=seconds)
            while start <= end:
                times.add(start)
                start += step
        else:
            raise ValueError("Invalid time dimension")
    return sorted(t for t in times if now - timedelta(hours=lookback_hours) <= t <= now)


def validate_config(config: dict) -> dict:
    west, south, east, north = config["bounds"]
    if not all(math.isfinite(v) for v in (west, south, east, north)):
        raise ValueError("Non-finite imagery bounds")
    if not (-180 <= west < east <= 180 and -85 <= south < north <= 85):
        raise ValueError("Invalid imagery bounds")
    for key in ("width", "height"):
        if type(config[key]) is not int or not 256 <= config[key] <= 4096:
            raise ValueError("Imagery dimensions must be between 256 and 4096")
    for key, low, high in (
        ("lookback_hours", 1, 24),
        ("max_new_frames_per_product", 1, 30),
        ("minimum_free_bytes", 0, 2**40),
        ("maximum_archive_bytes", 1, 2**40),
    ):
        if type(config[key]) is not int or not low <= config[key] <= high:
            raise ValueError(f"Invalid {key}")
    if not config["products"] or len(config["products"]) != len(set(config["products"])):
        raise ValueError("Select distinct imagery products")
    if any(code not in SOURCES for code in config["products"]):
        raise ValueError("Unsupported imagery source")
    return config


def bounded_get(client: httpx.Client, params: dict, limit: int) -> bytes:
    with client.stream("GET", GEOMET, params=params) as response:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > limit:
                raise ValueError("GeoMet response exceeded its configured size bound")
            chunks.append(chunk)
        return b"".join(chunks)


def create_cog(png: bytes, destination: Path, bounds: list, width: int, height: int) -> None:
    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Expected a PNG image, not an upstream service error")
    with MemoryFile(png) as memory, memory.open() as source:
        if source.width != width or source.height != height or source.count not in (3, 4):
            raise ValueError("Unexpected imagery dimensions or bands")
        if any(dtype != "uint8" for dtype in source.dtypes):
            raise ValueError("Expected 8-bit RGB(A) imagery")
        pixels = source.read()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Temporary work is on the destination filesystem for atomic publication.
    with tempfile.TemporaryDirectory(prefix="imagery-", dir=destination.parent) as staging:
        source_path, cog_path = Path(staging) / "image.tif", Path(staging) / "cog.tif"
        with rasterio.open(
            source_path,
            "w",
            driver="GTiff",
            width=width,
            height=height,
            count=len(pixels),
            dtype="uint8",
            crs="EPSG:4326",
            transform=from_bounds(*bounds, width, height),
        ) as target:
            target.write(pixels)
            target.colorinterp = (ColorInterp.red, ColorInterp.green, ColorInterp.blue) + (
                (ColorInterp.alpha,) if len(pixels) == 4 else ()
            )
        raster_copy(source_path, cog_path, driver="COG", compress="DEFLATE", blocksize=256)
        with rasterio.open(cog_path) as check:
            if check.driver != "GTiff" or check.crs.to_epsg() != 4326:
                raise ValueError("Invalid processed imagery")
        os.replace(cog_path, destination)


def atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(data)
            output.flush()
            # NamedTemporaryFile starts at 0600 regardless of the service umask.
            # Publish weather payloads readable/writable by the shared data group.
            os.fchmod(output.fileno(), 0o664)
            os.fsync(output.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    os.replace(temporary, path)


def ingest_imagery(config_path: Path, data_root: Path, database_url: str) -> dict:
    config = validate_config(json.loads(config_path.read_text()))
    data_root.mkdir(parents=True, exist_ok=True)
    loader = SqlFileLoader()
    now = datetime.now(UTC)
    collected = 0
    # Account only this archive; retain history until an explicit retention policy is added.
    archive_bytes = sum(
        p.stat().st_size
        for sub in ("raw", "processed")
        for p in (data_root / sub / "eccc" / "imagery").rglob("*")
        if p.is_file()
    )
    failures = []
    with (
        psycopg.connect(database_url, row_factory=dict_row) as connection,
        httpx.Client(
            timeout=45, follow_redirects=False, headers={"User-Agent": "WeatherAtlas-ETL/1.0"}
        ) as client,
    ):
        enabled = {row["code"] for row in connection.execute(loader.load("imagery/products.sql"))}
        connection.commit()
        for code in config["products"]:
            if code not in enabled:
                continue
            try:
                layer = SOURCES[code]
                identity = {
                    "layer": layer,
                    "bounds": config["bounds"],
                    "width": config["width"],
                    "height": config["height"],
                    "version": "1.3.0",
                    "style": "",
                    "format": "image/png",
                }
                configuration_sha = hashlib.sha256(
                    json.dumps(identity, sort_keys=True).encode()
                ).hexdigest()
                xml = bounded_get(
                    client,
                    {
                        "SERVICE": "WMS",
                        "VERSION": "1.3.0",
                        "REQUEST": "GetCapabilities",
                        "LAYER": layer,
                    },
                    8 * 1024**2,
                )
                times = available_times(xml, layer, now, config["lookback_hours"])
                count = 0
                legend_path = None
                for valid in reversed(times):
                    parameters = {
                        "code": code,
                        "valid_time": valid,
                        "configuration_sha256": configuration_sha,
                    }
                    exists = connection.execute(
                        loader.load("imagery/exists.sql"), parameters
                    ).fetchone()
                    connection.commit()
                    if exists:
                        continue
                    if count >= config["max_new_frames_per_product"]:
                        break
                    # Reserve room for one bounded source + COG and temporary files.
                    reserve = 256 * 1024**2
                    if shutil.disk_usage(data_root).free < config["minimum_free_bytes"] + reserve:
                        raise ValueError("Imagery ingestion paused: low disk")
                    if archive_bytes + reserve > config["maximum_archive_bytes"]:
                        raise ValueError("Imagery ingestion paused: archive budget reached")
                    west, south, east, north = config["bounds"]
                    params = {
                        "SERVICE": "WMS",
                        "VERSION": "1.3.0",
                        "REQUEST": "GetMap",
                        "LAYERS": layer,
                        "STYLES": "",
                        "CRS": "CRS:84",
                        "BBOX": f"{west},{south},{east},{north}",
                        "WIDTH": config["width"],
                        "HEIGHT": config["height"],
                        "FORMAT": "image/png",
                        "TRANSPARENT": "TRUE",
                        "TIME": valid.isoformat().replace("+00:00", "Z"),
                    }
                    if legend_path is None:
                        legend = bounded_get(
                            client,
                            {
                                "SERVICE": "WMS",
                                "VERSION": "1.3.0",
                                "REQUEST": "GetLegendGraphic",
                                "SLD_VERSION": "1.1.0",
                                "LAYER": layer,
                                "FORMAT": "image/png",
                                "STYLE": "",
                            },
                            4 * 1024**2,
                        )
                        if not legend.startswith(b"\x89PNG\r\n\x1a\n"):
                            raise ValueError("GeoMet legend is not PNG")
                        with MemoryFile(legend) as memory, memory.open() as image:
                            if image.width > 2048 or image.height > 4096:
                                raise ValueError("Oversized legend")
                        legend_sha = hashlib.sha256(legend).hexdigest()
                        legend_path = (
                            Path("processed/eccc/imagery") / code / f"legend-{legend_sha}.png"
                        )
                        atomic_bytes(data_root / legend_path, legend)
                        archive_bytes += len(legend)
                    png = bounded_get(client, params, 32 * 1024**2)
                    source_sha = hashlib.sha256(png).hexdigest()
                    frame_id = uuid5(
                        NAMESPACE_URL,
                        f"{code}/{valid.isoformat()}/{configuration_sha}/{source_sha}",
                    )
                    raw_prefix = Path("raw/eccc/imagery") / code / str(frame_id)
                    relative = Path("processed/eccc/imagery") / code / f"{frame_id}.tif"
                    create_cog(
                        png,
                        data_root / relative,
                        config["bounds"],
                        config["width"],
                        config["height"],
                    )
                    atomic_bytes(data_root / raw_prefix.with_suffix(".png"), png)
                    atomic_bytes(data_root / raw_prefix.with_suffix(".xml"), xml)
                    parameters.update(
                        {
                            "id": frame_id,
                            "content_sha256": hashlib.sha256(
                                (data_root / relative).read_bytes()
                            ).hexdigest(),
                            "relative_path": relative.as_posix(),
                            "bounds": Jsonb(config["bounds"]),
                            "provenance": Jsonb(
                                {
                                    "source": GEOMET,
                                    "request": params,
                                    "raw": raw_prefix.with_suffix(".png").as_posix(),
                                    "sourceSha256": hashlib.sha256(png).hexdigest(),
                                    "capabilitiesSha256": hashlib.sha256(xml).hexdigest(),
                                    "displayOnly": True,
                                    "legendPath": legend_path.as_posix(),
                                }
                            ),
                        }
                    )
                    connection.execute(loader.load("imagery/register.sql"), parameters)
                    connection.commit()
                    archive_bytes += len(png) + len(xml) + (data_root / relative).stat().st_size
                    collected += 1
                    count += 1
            except Exception as error:
                connection.rollback()
                failures.append(f"{code}: {error}")
    if failures:
        raise RuntimeError(f"Collected {collected} frames; " + "; ".join(failures))
    return {"collected": collected, "archive_bytes": archive_bytes}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/imagery.json"))
    args = parser.parse_args()
    print(
        json.dumps(
            ingest_imagery(
                args.config,
                Path(os.environ["WEATHER_DATA_ROOT"]),
                os.environ["WEATHER_DATABASE_URL"],
            )
        )
    )
