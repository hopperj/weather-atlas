"""Shared display-only ranges and palette transforms; never change weather values."""

from __future__ import annotations

import math
from typing import Any, Literal

PaletteMode = Literal["absolute", "relative"]


def rounded_temperature_range(
    minimum: float | None, maximum: float | None
) -> tuple[float, float] | None:
    """Enclose valid Celsius extrema in 5-degree steps, or report unavailable stats."""
    if minimum is None or maximum is None:
        return None
    if not math.isfinite(minimum) or not math.isfinite(maximum) or minimum > maximum:
        return None
    lower = float(math.floor(minimum / 5) * 5)
    upper = float(math.ceil(maximum / 5) * 5)
    # A constant field exactly on a step still needs a nonzero colour range.
    return lower, upper if upper > lower else lower + 5


def palette_for_display(
    definition: dict[str, Any], minimum: float, maximum: float, mode: PaletteMode
) -> dict[str, Any]:
    """Stretch temperature colour anchors together, preserving their relative spacing."""
    if mode == "absolute":
        return definition
    if mode != "relative":
        raise ValueError("Unknown palette mode")
    stops = sorted(definition["stops"], key=lambda stop: float(stop["value"]))
    if len(stops) < 2 or minimum >= maximum:
        raise ValueError("Invalid palette range")
    first, last = float(stops[0]["value"]), float(stops[-1]["value"])
    if not math.isfinite(first) or not math.isfinite(last) or first >= last:
        raise ValueError("Invalid palette anchors")
    return {
        **definition,
        "stops": [
            {
                **stop,
                "value": minimum
                + (float(stop["value"]) - first) / (last - first) * (maximum - minimum),
                # Absolute-temperature labels no longer describe shifted anchors.
                "label": None,
            }
            for stop in stops
        ],
    }
