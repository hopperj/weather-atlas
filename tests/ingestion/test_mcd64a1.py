from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import yaml
from pyhdf.SD import SD, SDC
from weather_ingest.mcd64a1 import build_mcd64a1_event_areas

RADIUS_M = 6_371_007.181
PIXEL_SIZE_M = 500.0
TILE_PIXELS = 4
GLOBAL_X_MIN = -18 * TILE_PIXELS * PIXEL_SIZE_M
GLOBAL_Y_MAX = 9 * TILE_PIXELS * PIXEL_SIZE_M
GRANULE_ID = "MCD64A1.A2025305.h18v09.061.2026006000000"
SECOND_GRANULE_ID = "MCD64A1.A2025335.h18v09.061.2026007000000"


def _cell_centre(row: int, column: int) -> tuple[float, float]:
    x = GLOBAL_X_MIN + (column + 0.5) * PIXEL_SIZE_M
    y = GLOBAL_Y_MAX - (row + 0.5) * PIXEL_SIZE_M
    latitude_radians = y / RADIUS_M
    return (
        math.degrees(x / (RADIUS_M * math.cos(latitude_radians))),
        math.degrees(latitude_radians),
    )


def _write_config(
    path: Path,
    *,
    duplicate_policy: str = "require_identical_then_deduplicate",
) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "operator_version": "test-mcd64-v1",
                "product": "MCD64A1",
                "collection": "061",
                "grid": {
                    "projection": "MODIS sinusoidal",
                    "sphere_radius_m": RADIUS_M,
                    "global_upper_left_x_m": GLOBAL_X_MIN,
                    "global_upper_left_y_m": GLOBAL_Y_MAX,
                    "tile_pixels": TILE_PIXELS,
                    "pixel_size_m": PIXEL_SIZE_M,
                    "connectivity": 8,
                },
                "quality": {
                    "require_land_bit": True,
                    "require_valid_data_bit": True,
                    "require_burn_date_in_reliable_window": True,
                    "include_shortened_mapping_period": True,
                    "include_contextually_relabeled": True,
                    "high_confidence_excludes_shortened_mapping_period": True,
                    "high_confidence_excludes_contextually_relabeled": True,
                },
                "matching": {
                    "seed_radius_m": 200,
                    "event_time_padding_days": 1,
                    "use_burn_date_uncertainty": True,
                    "overlapping_pixel_policy": "exclude_from_all_events",
                    "cross_month_duplicate_policy": duplicate_policy,
                },
                "area": {
                    "calculation": "equal_area_projected_pixel_area",
                    "hectares_per_square_metre": 0.0001,
                },
                "eligibility": {
                    "minimum_assigned_pixel_count": 1,
                    "require_at_least_one_high_confidence_pixel": True,
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _write_granule(
    root: Path,
    *,
    granule_id: str = GRANULE_ID,
    burn_ordinal: int = 314,
) -> None:
    month = "11" if ".A2025305." in granule_id else "12"
    path = root / "2025" / month / f"{granule_id}.hdf"
    path.parent.mkdir(parents=True)
    hdf = SD(path.as_posix(), SDC.WRITE | SDC.CREATE)
    try:
        hdf.attr("StructMetadata.0").set(
            SDC.CHAR8,
            (
                "GROUP=GridStructure\n"
                f"XDim={TILE_PIXELS}\n"
                f"YDim={TILE_PIXELS}\n"
                "UpperLeftPointMtrs=(0.000000,0.000000)\n"
                "Projection=GCTP_SNSOID\n"
                "END_GROUP=GridStructure\n"
            ),
        )
        burn_date = np.zeros((TILE_PIXELS, TILE_PIXELS), dtype=np.int16)
        burn_date[0, 0:2] = burn_ordinal
        uncertainty = np.zeros((TILE_PIXELS, TILE_PIXELS), dtype=np.uint8)
        qa = np.full((TILE_PIXELS, TILE_PIXELS), 3, dtype=np.uint8)
        first_day = np.full((TILE_PIXELS, TILE_PIXELS), 305, dtype=np.int16)
        last_day = np.full((TILE_PIXELS, TILE_PIXELS), 335, dtype=np.int16)
        for name, data, data_type in (
            ("Burn Date", burn_date, SDC.INT16),
            ("Burn Date Uncertainty", uncertainty, SDC.UINT8),
            ("QA", qa, SDC.UINT8),
            ("First Day", first_day, SDC.INT16),
            ("Last Day", last_day, SDC.INT16),
        ):
            dataset = hdf.create(name, data_type, data.shape)
            dataset[:] = data
            dataset.endaccess()
    finally:
        hdf.end()


def _event(event_id: str, row: int, column: int) -> dict[str, object]:
    longitude, latitude = _cell_centre(row, column)
    return {
        "event_id": event_id,
        "first_observed_at": "2025-11-10T12:00:00Z",
        "last_observed_at": "2025-11-10T12:00:00Z",
        "latitude": latitude,
        "longitude": longitude,
        "fuel_types": ["C2"],
        "detections": [
            {
                "detection_id": f"detection-{event_id}",
                "observed_at": "2025-11-10T12:00:00Z",
                "latitude": latitude,
                "longitude": longitude,
            }
        ],
    }


def _write_inputs(
    temporary_path: Path,
    events: list[dict[str, object]],
) -> tuple[Path, Path, Path, Path]:
    root = temporary_path / "mcd64"
    _write_granule(root)
    cmr = temporary_path / "cmr.json"
    cmr.write_text(
        json.dumps({"feed": {"entry": [{"producer_granule_id": GRANULE_ID}]}}),
        encoding="utf-8",
    )
    event_path = temporary_path / "events.json"
    event_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "algorithm_version": "test-events-v1",
                "event_count": len(events),
                "detection_count": len(events),
                "events": events,
            }
        ),
        encoding="utf-8",
    )
    config = temporary_path / "config.yaml"
    _write_config(config)
    return root, cmr, event_path, config


def test_mcd64a1_seed_grows_connected_scar_and_calculates_area(tmp_path: Path) -> None:
    root, cmr, events, config = _write_inputs(
        tmp_path,
        [_event("event-a", 9 * TILE_PIXELS, 18 * TILE_PIXELS)],
    )

    report = build_mcd64a1_event_areas(
        mcd64_root=root,
        cmr_path=cmr,
        events_path=events,
        config_path=config,
        start=date(2025, 11, 10),
        end=date(2025, 12, 1),
    )

    result = report["events"][0]
    assert result["seed_pixel_count"] == 1
    assert result["raw_claim_pixel_count"] == 2
    assert result["assigned_pixel_count"] == 2
    assert result["central_area_ha"] == 50.0
    assert result["daily_area"]["central_daily_increment_ha"] == {"2025-11-10": 50.0}
    assert result["burned_area_eligible"] is True
    assert report["summary"]["eligible_strata_counts"] == {
        "weak": 1,
        "moderate": 0,
        "major": 0,
    }


def test_mcd64a1_excludes_pixels_claimed_by_multiple_events(tmp_path: Path) -> None:
    root, cmr, events, config = _write_inputs(
        tmp_path,
        [
            _event("event-a", 9 * TILE_PIXELS, 18 * TILE_PIXELS),
            _event("event-b", 9 * TILE_PIXELS, 18 * TILE_PIXELS + 1),
        ],
    )

    report = build_mcd64a1_event_areas(
        mcd64_root=root,
        cmr_path=cmr,
        events_path=events,
        config_path=config,
        start=date(2025, 11, 10),
        end=date(2025, 12, 1),
    )

    assert report["summary"]["ambiguous_pixel_count"] == 2
    assert report["summary"]["burned_area_eligible_event_count"] == 0
    assert all(item["assigned_pixel_count"] == 0 for item in report["events"])
    assert all(
        "insufficient_unambiguous_burn_pixels" in item["ineligibility_reasons"]
        for item in report["events"]
    )


def test_mcd64a1_v2_retains_distinct_burn_dates_at_same_cell(tmp_path: Path) -> None:
    root, cmr, events, config = _write_inputs(
        tmp_path,
        [_event("event-a", 9 * TILE_PIXELS, 18 * TILE_PIXELS)],
    )
    _write_granule(
        root,
        granule_id=SECOND_GRANULE_ID,
        burn_ordinal=335,
    )
    cmr.write_text(
        json.dumps(
            {
                "feed": {
                    "entry": [
                        {"producer_granule_id": GRANULE_ID},
                        {"producer_granule_id": SECOND_GRANULE_ID},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    payload = json.loads(events.read_text(encoding="utf-8"))
    event = payload["events"][0]
    later_detection = dict(event["detections"][0])
    later_detection["detection_id"] = "detection-event-a-later"
    later_detection["observed_at"] = "2025-12-01T12:00:00Z"
    event["detections"].append(later_detection)
    payload["detection_count"] = 2
    events.write_text(json.dumps(payload), encoding="utf-8")
    _write_config(
        config,
        duplicate_policy=(
            "retain_distinct_burn_dates_deduplicate_identical_occurrences"
        ),
    )

    report = build_mcd64a1_event_areas(
        mcd64_root=root,
        cmr_path=cmr,
        events_path=events,
        config_path=config,
        start=date(2025, 11, 10),
        end=date(2025, 12, 1),
    )

    result = report["events"][0]
    assert result["assigned_burn_occurrence_count"] == 4
    assert result["assigned_spatial_pixel_count"] == 2
    assert result["central_area_ha"] == 100.0
    assert result["daily_area"]["central_daily_increment_ha"] == {
        "2025-11-10": 50.0,
        "2025-12-01": 50.0,
    }
    provenance = report["sources"]["mcd64a1"]
    assert provenance["unique_spatial_pixel_count"] == 2
    assert provenance["unique_burn_occurrence_count"] == 4
    assert provenance["distinct_repeat_burn_coordinate_count"] == 2
    assert provenance["distinct_repeat_burn_occurrence_count"] == 4


def test_mcd64a1_v2_deduplicates_identical_cross_month_occurrence(
    tmp_path: Path,
) -> None:
    root, cmr, events, config = _write_inputs(
        tmp_path,
        [_event("event-a", 9 * TILE_PIXELS, 18 * TILE_PIXELS)],
    )
    _write_granule(
        root,
        granule_id=SECOND_GRANULE_ID,
        burn_ordinal=314,
    )
    cmr.write_text(
        json.dumps(
            {
                "feed": {
                    "entry": [
                        {"producer_granule_id": GRANULE_ID},
                        {"producer_granule_id": SECOND_GRANULE_ID},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    _write_config(
        config,
        duplicate_policy=(
            "retain_distinct_burn_dates_deduplicate_identical_occurrences"
        ),
    )

    report = build_mcd64a1_event_areas(
        mcd64_root=root,
        cmr_path=cmr,
        events_path=events,
        config_path=config,
        start=date(2025, 11, 10),
        end=date(2025, 12, 1),
    )

    result = report["events"][0]
    assert result["assigned_burn_occurrence_count"] == 2
    assert result["central_area_ha"] == 50.0
    provenance = report["sources"]["mcd64a1"]
    assert provenance["cross_month_identical_duplicate_count"] == 2
    assert provenance["unique_spatial_pixel_count"] == 2
    assert provenance["unique_burn_occurrence_count"] == 2
    assert provenance["distinct_repeat_burn_coordinate_count"] == 0
