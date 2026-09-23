from __future__ import annotations

import hashlib
import json
from datetime import date

import numpy as np
import rasterio
from rasterio.transform import from_origin
from weather_ingest.cwfis_cffdrs import (
    FIELDS,
    enrich_event_snapshot,
    grid_relative_path,
    manifest_relative_path,
    sample_fire_weather,
)


def _write_grid(root, data_date: date, field: str, value: float) -> dict[str, object]:
    path = root / grid_relative_path(data_date, field)
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=2,
        height=2,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(-65, 47, 1, 1),
        nodata=-9999,
    ) as destination:
        destination.write(np.full((2, 2), value, dtype=np.float32), 1)
    return {
        "relative_path": grid_relative_path(data_date, field).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _write_manifest(root, data_date: date) -> None:
    values = {"ffmc": 91.5, "dmc": 44.0, "dc": 310.0}
    path = root / manifest_relative_path(data_date)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "provider": "nrcan",
                "product": "cwfis_cffdrs_codes",
                "data_date": data_date.isoformat(),
                "grids": {
                    field: _write_grid(root, data_date, field, values[field])
                    for field in FIELDS
                },
            }
        ),
        encoding="utf-8",
    )


def test_sample_fire_weather_freezes_values_and_grid_provenance(tmp_path) -> None:
    data_date = date(2026, 7, 21)
    _write_manifest(tmp_path, data_date)

    result = sample_fire_weather(tmp_path, data_date, 45.5, -63.5)

    assert result["ffmc"] == 91.5
    assert result["dmc"] == 44
    assert result["dc"] == 310
    assert result["source_date"] == "2026-07-21"
    assert len(result["manifest_sha256"]) == 64
    assert result["cells"]["ffmc"] == {"row": 1, "column": 1}


def test_event_snapshot_enrichment_replaces_missing_state_warning(tmp_path) -> None:
    data_date = date(2026, 7, 21)
    _write_manifest(tmp_path, data_date)
    snapshot = tmp_path / "events.json"
    snapshot.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "event_count": 1,
                "detection_count": 1,
                "events": [
                    {
                        "event_id": "event-a",
                        "last_observed_at": "2026-07-21T15:00:00Z",
                        "latitude": 45.5,
                        "longitude": -63.5,
                        "warnings": ["missing_cffeps_fire_weather_codes"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = enrich_event_snapshot(snapshot, tmp_path)
    payload = json.loads(snapshot.read_text(encoding="utf-8"))

    assert result["enriched_event_count"] == 1
    assert payload["schema_version"] == 2
    assert payload["events"][0]["warnings"] == []
    assert payload["events"][0]["fire_weather"]["ffmc"] == 91.5
