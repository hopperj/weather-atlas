"""Safe local COG resolution and deterministic weather tile rendering."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
from rio_tiler.io import COGReader
from weather_common.display_scales import PaletteMode, palette_for_display


class TileRenderingError(ValueError):
    """Raised for an invalid registered asset or display style."""


_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")
_ALLOWED_RESAMPLING = {"nearest", "bilinear", "cubic", "average"}


def resolve_asset_path(data_root: Path, relative_path: str) -> Path:
    root = data_root.resolve()
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise TileRenderingError("Registered asset path must be relative")
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root):
        raise TileRenderingError("Registered asset path escapes the data root")
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return resolved


def _rgba(color: str) -> tuple[int, int, int, int]:
    if not _HEX_COLOR.fullmatch(color):
        raise TileRenderingError(f"Invalid palette color: {color}")
    raw = color[1:]
    if len(raw) == 6:
        raw += "ff"
    return tuple(int(raw[index : index + 2], 16) for index in range(0, 8, 2))  # type: ignore[return-value]


def build_colormap(
    definition: dict[str, Any],
    *,
    display_min: float | None = None,
    display_max: float | None = None,
    palette_mode: PaletteMode = "absolute",
) -> dict[int, tuple[int, int, int, int]]:
    """Interpolate a validated palette definition across an 8-bit display range."""
    if palette_mode == "relative":
        if display_min is None or display_max is None:
            raise TileRenderingError("Relative palettes require a display range")
        try:
            definition = palette_for_display(definition, display_min, display_max, palette_mode)
        except (KeyError, TypeError, ValueError) as exc:
            raise TileRenderingError("Relative palette is invalid") from exc
    elif palette_mode != "absolute":
        raise TileRenderingError("Unknown palette mode")
    raw_stops = definition.get("stops")
    if not isinstance(raw_stops, list) or len(raw_stops) < 2:
        raise TileRenderingError("Palette must contain at least two stops")

    stops: list[tuple[float, tuple[int, int, int, int]]] = []
    for raw_stop in raw_stops:
        if not isinstance(raw_stop, dict):
            raise TileRenderingError("Palette stop must be an object")
        try:
            value = float(raw_stop["value"])
            color = _rgba(str(raw_stop["color"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise TileRenderingError("Palette stop is invalid") from exc
        stops.append((value, color))

    stops.sort(key=lambda item: item[0])
    if any(left[0] >= right[0] for left, right in zip(stops, stops[1:], strict=False)):
        raise TileRenderingError("Palette stop values must be unique")

    interpolation = definition.get("interpolation", "linear")
    if interpolation not in {"linear", "step"}:
        raise TileRenderingError("Palette interpolation is invalid")
    minimum = stops[0][0] if display_min is None else display_min
    maximum = stops[-1][0] if display_max is None else display_max
    if minimum >= maximum:
        raise TileRenderingError("Palette display range is invalid")
    span = maximum - minimum
    normalized = [((value - minimum) / span * 255.0, color) for value, color in stops]
    colormap: dict[int, tuple[int, int, int, int]] = {}

    stop_index = 0
    for pixel in range(256):
        if interpolation == "step":
            selected_color = normalized[0][1]
            for stop_value, stop_color in normalized:
                if pixel < stop_value:
                    break
                selected_color = stop_color
            colormap[pixel] = selected_color
            continue
        while stop_index < len(normalized) - 2 and pixel > normalized[stop_index + 1][0]:
            stop_index += 1
        left_value, left_color = normalized[stop_index]
        right_value, right_color = normalized[min(stop_index + 1, len(normalized) - 1)]
        ratio = (
            0.0
            if right_value == left_value
            else (pixel - left_value) / (right_value - left_value)
        )
        ratio = max(0.0, min(1.0, ratio))
        colormap[pixel] = tuple(
            round(left + (right - left) * ratio)
            for left, right in zip(left_color, right_color, strict=True)
        )  # type: ignore[assignment]
    return colormap


def render_registered_tile(
    path: Path,
    *,
    x: int,
    y: int,
    z: int,
    display_min: float,
    display_max: float,
    opacity_cutoff: float | None,
    palette_definition: dict[str, Any],
    image_format: str,
    resampling_method: str,
    palette_mode: PaletteMode = "absolute",
) -> bytes:
    if display_min >= display_max:
        raise TileRenderingError("Display minimum must be lower than maximum")
    if opacity_cutoff is not None and not np.isfinite(opacity_cutoff):
        raise TileRenderingError("Opacity cutoff must be finite")
    if image_format not in {"png", "webp"}:
        raise TileRenderingError("Unsupported tile format")
    if resampling_method not in _ALLOWED_RESAMPLING:
        raise TileRenderingError("Unsupported resampling method")
    if x < 0 or y < 0 or z < 0 or x >= 2**z or y >= 2**z:
        raise TileRenderingError("Tile coordinate is outside its zoom matrix")

    colormap = build_colormap(
        palette_definition,
        display_min=display_min,
        display_max=display_max,
        palette_mode=palette_mode,
    )
    with COGReader(path) as reader:
        image = reader.tile(
            x,
            y,
            z,
            tilesize=256,
            resampling_method=resampling_method,
        )
    if opacity_cutoff is not None:
        image.array = np.ma.masked_where(
            image.array < opacity_cutoff,
            image.array,
        )
    image.rescale(((display_min, display_max),))
    return image.render(img_format=image_format.upper(), colormap=colormap)
