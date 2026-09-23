from pathlib import Path

from weather_ingest.misr_minx import parse_minx_plume


def test_parse_minx_plume_and_agl_operator(tmp_path: Path) -> None:
    path = tmp_path / "Plumes_O000001-B001-SPW01.txt"
    path.write_text(
        """Orbit number : 1
Date acquired : 2023-06-01
UTC time : 12:30:00
MINX version : V4.0
Region name : O000001-B001-SPW01
Region aerosol type : Smoke
Region geometry type : Polygon
Retrieval quality est. : Good
Fire elev. (m > MSL) : 100

POLYGON: 5 points in this table define the digitized bounding polygon.
 1 -75.2 44.8 1 1 1
 2 -74.8 44.8 1 1 1
 3 -74.8 45.2 1 1 1
 4 -75.2 45.2 1 1 1
 5 -75.2 44.8 1 1 1

RESULTS: 3 points in this table.
 1 -75.0 45.0 1 1 1 0 0 0 100 1000 1200 1100
 2 -75.1 45.0 1 1 1 0 0 0 200 1200 1500 1300
 3 -75.2 45.0 1 1 1 0 0 0 150 -9999 -9999 -9999
"""
    )
    plume = parse_minx_plume(path)
    assert plume.region_name == "O000001-B001-SPW01"
    assert plume.polygon[0] == plume.polygon[-1]
    assert plume.valid_heights_agl_m().tolist() == [1100.0, 1300.0]
    assert plume.robust_height_agl_m() == 1200.0
