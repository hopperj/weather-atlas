import pytest
from weather_ingest.units import convert_value, wind_speed_and_direction


def test_reviewed_unit_conversions() -> None:
    assert convert_value("kelvin_to_celsius", 273.15) == pytest.approx(0)
    assert convert_value("pascals_to_hectopascals", 101325) == pytest.approx(1013.25)
    assert convert_value("metres_to_kilometres", 12000) == pytest.approx(12)
    assert convert_value(
        "kilograms_per_cubic_metre_to_micrograms_per_cubic_metre", 1e-9
    ) == pytest.approx(1)


def test_wind_uses_meteorological_direction() -> None:
    speed, direction = wind_speed_and_direction(0, -10)

    assert speed == pytest.approx(10)
    assert direction == pytest.approx(0)
