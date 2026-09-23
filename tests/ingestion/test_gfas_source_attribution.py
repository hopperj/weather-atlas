from __future__ import annotations

import csv
from pathlib import Path

from weather_ingest.gfas_event_support import (
    build_support_records,
    write_sparse_support_netcdf,
)
from weather_ingest.gfas_source_attribution import evaluate_source_attribution


def _write_domain_pairs(path: Path) -> None:
    fields = (
        "observed",
        "modelled",
        "date",
        "latitude",
        "longitude",
        "grid_row",
        "grid_column",
        "species",
        "event_id",
    )
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(
            [
                {
                    "observed": 10,
                    "modelled": 8,
                    "date": "2023-06-01",
                    "latitude": 45.05,
                    "longitude": -75.05,
                    "grid_row": 449,
                    "grid_column": 1049,
                    "species": "PM25",
                    "event_id": "event-a",
                },
                {
                    "observed": 5,
                    "modelled": 0,
                    "date": "2023-06-01",
                    "latitude": 40.05,
                    "longitude": -80.05,
                    "grid_row": 499,
                    "grid_column": 999,
                    "species": "PM25",
                    "event_id": "",
                },
            ]
        )


def test_evaluate_source_attribution_closes_domain_mass(tmp_path: Path) -> None:
    area = {
        "events": [
            {
                "event_id": "event-a",
                "daily_area": {"central_daily_increment_ha": {"2023-06-01": 1.0}},
                "support_occurrences": [
                    {
                        "longitude": -75.05,
                        "latitude": 45.05,
                        "burn_date": "2023-06-01",
                    }
                ],
            }
        ]
    }
    ledger = {
        "retained_events": [{"event_id": "event-a", "role": "retained"}],
        "reserve_events": [],
    }
    support = build_support_records(area_report=area, source_ledger=ledger)
    support_path = tmp_path / "support.nc"
    write_sparse_support_netcdf(support_path, support)
    pairs = tmp_path / "pm25.csv"
    _write_domain_pairs(pairs)

    report = evaluate_source_attribution(
        pair_paths=[pairs],
        support_path=support_path,
        output_directory=tmp_path / "evaluation",
    )

    closure = report["species"]["PM25"]["coverage_closure"]
    assert closure["observed"]["domain"] == 15
    assert closure["observed"]["inside_supported_masks"] == 10
    assert closure["observed"]["outside_supported_masks"] == 5
    assert report["all_coverage_closures_passed"]
