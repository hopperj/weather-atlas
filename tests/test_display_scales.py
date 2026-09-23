import copy
import math

import pytest
from weather_common.display_scales import palette_for_display, rounded_temperature_range
from weather_tiles.rendering import build_colormap


@pytest.mark.parametrize(
    ("minimum", "maximum", "expected"),
    [
        (3.3, 22.1, (0, 25)),
        (-3.3, 22.1, (-5, 25)),
        (-18.8, -3.3, (-20, 0)),
        (0, 25, (0, 25)),
        (-20, -5, (-20, -5)),
        (3.3, 3.3, (0, 5)),
        (5, 5, (5, 10)),
        (0, 0, (0, 5)),
        (-5, -5, (-5, 0)),
        (None, 25, None),
        (0, None, None),
        (math.nan, 25, None),
        (0, math.inf, None),
        (25, 0, None),
    ],
)
def test_temperature_range_rounds_outward(minimum, maximum, expected):
    assert rounded_temperature_range(minimum, maximum) == expected


def test_palette_and_tiles_use_the_same_full_colour_range_without_mutation():
    original = {
        "stops": [
            {"value": -40, "color": "#0000ff", "label": "-40°C"},
            {"value": -24, "color": "#00ffff"},
            {"value": 40, "color": "#ff0000"},
        ]
    }
    saved = copy.deepcopy(original)
    shifted = palette_for_display(original, 0, 25, "relative")
    assert [stop["value"] for stop in shifted["stops"]] == [0, 5, 25]
    assert all(stop["label"] is None for stop in shifted["stops"])
    colours = build_colormap(original, display_min=0, display_max=25, palette_mode="relative")
    assert colours == build_colormap(shifted, display_min=0, display_max=25)
    assert colours[0] == (0, 0, 255, 255)
    assert colours[51] == (0, 255, 255, 255)
    assert colours[255] == (255, 0, 0, 255)
    assert palette_for_display(original, 0, 25, "absolute") == original
    assert original == saved
