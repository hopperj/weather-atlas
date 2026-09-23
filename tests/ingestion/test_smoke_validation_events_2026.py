from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parents[2] / "scripts" / "prepare_smoke_validation_events_2026.py"
SPEC = importlib.util.spec_from_file_location("prepare_smoke_validation_events_2026", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

_inside_canada = MODULE._inside_canada
_inside_ring = MODULE._inside_ring


def test_point_in_ring_includes_interior_and_boundary() -> None:
    ring = [[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0], [0.0, 0.0]]

    assert _inside_ring(2.0, 2.0, ring)
    assert _inside_ring(0.0, 2.0, ring)
    assert not _inside_ring(5.0, 2.0, ring)


def test_country_polygon_excludes_hole_and_uses_bbox() -> None:
    exterior = [[0.0, 0.0], [5.0, 0.0], [5.0, 5.0], [0.0, 5.0], [0.0, 0.0]]
    hole = [[1.0, 1.0], [2.0, 1.0], [2.0, 2.0], [1.0, 2.0], [1.0, 1.0]]
    polygons = [{"bbox": (0.0, 0.0, 5.0, 5.0), "rings": [exterior, hole]}]

    assert _inside_canada(4.0, 4.0, polygons)
    assert not _inside_canada(1.5, 1.5, polygons)
    assert not _inside_canada(-1.0, 4.0, polygons)
