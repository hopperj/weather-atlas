from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from weather_ingest.minx_blind_qa import (
    blind_quality_checks,
    parse_minx_without_heights,
    plume_family_name,
)


def test_blind_parser_never_requires_or_retains_height_values(tmp_path: Path) -> None:
    path = tmp_path / "Plumes_O000001-B001-SPWB01.txt"
    rows = "\n".join(
        f" {index} -75.{index:02d} 45.0 1 1 1 0 0 0 100 SECRET SECRET SECRET"
        for index in range(1, 11)
    )
    path.write_text(
        f"""Orbit number : 1
Date acquired : 2023-06-01
UTC time : 12:30:00
MINX version : V4.0
Region name : O000001-B001-SPWB01
Region aerosol type : Smoke
Region geometry type : Polygon
Retrieval quality est. : Good

POLYGON: 5 points in this table define the digitized bounding polygon.
 1 -75.2 44.8
 2 -74.8 44.8
 3 -74.8 45.2
 4 -75.2 45.2
 5 -75.2 44.8

RESULTS: 10 points in this table.
{rows}
"""
    )
    plume = parse_minx_without_heights(path)

    assert plume.raw_retrieval_count == 10
    assert plume.band == "B"
    assert not hasattr(plume, "wind_corrected_asl_m")
    checks = blind_quality_checks(
        plume,
        expected_orbit=1,
        expected_time=datetime(2023, 6, 1, 12, 30, tzinfo=UTC),
        expected_region_name="O000001-B001-SPWB01",
        expected_retrieval_count=10,
        source_latitude=45.0,
        source_longitude=-75.0,
    )
    assert all(checks.values())


def test_plume_family_name_ignores_spectral_band() -> None:
    assert (
        plume_family_name("O093614-B041-SPWB03")
        == plume_family_name("O093614-B041-SPWR03")
        == "O093614-B041-SPW03"
    )
