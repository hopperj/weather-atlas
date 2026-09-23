"""Reviewed scalar conversions mirrored by raster processing expressions."""

from __future__ import annotations

import math
from collections.abc import Callable


def identity(value: float) -> float:
    return value


def kelvin_to_celsius(value: float) -> float:
    return value - 273.15


def kilograms_per_cubic_metre_to_micrograms_per_cubic_metre(value: float) -> float:
    return value * 1_000_000_000.0


def metres_to_kilometres(value: float) -> float:
    return value / 1000.0


def pascals_to_hectopascals(value: float) -> float:
    return value / 100.0


CONVERSIONS: dict[str, Callable[[float], float]] = {
    "identity": identity,
    "kilograms_per_cubic_metre_to_micrograms_per_cubic_metre": (
        kilograms_per_cubic_metre_to_micrograms_per_cubic_metre
    ),
    "kelvin_to_celsius": kelvin_to_celsius,
    "metres_to_kilometres": metres_to_kilometres,
    "pascals_to_hectopascals": pascals_to_hectopascals,
}

GDAL_CALC_EXPRESSIONS: dict[str, str | None] = {
    "identity": None,
    "kilograms_per_cubic_metre_to_micrograms_per_cubic_metre": "A*1000000000.0",
    "kelvin_to_celsius": "A-273.15",
    "metres_to_kilometres": "A/1000.0",
    "pascals_to_hectopascals": "A/100.0",
}


def convert_value(conversion_key: str, value: float) -> float:
    try:
        conversion = CONVERSIONS[conversion_key]
    except KeyError as exc:
        raise ValueError(f"unknown conversion key: {conversion_key}") from exc
    return conversion(value)


def wind_speed_and_direction(u: float, v: float) -> tuple[float, float]:
    """Return speed and meteorological direction (the direction wind comes from)."""

    speed = math.hypot(u, v)
    if speed == 0:
        return 0.0, 0.0
    direction = (270.0 - math.degrees(math.atan2(v, u))) % 360.0
    return speed, direction
