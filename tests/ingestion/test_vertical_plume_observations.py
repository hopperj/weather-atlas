import csv
from datetime import UTC, datetime
from pathlib import Path

import netCDF4
import numpy as np
from weather_ingest.vertical_plume_observations import (
    VerticalPlumeObservation,
    evaluate_vertical_pairs,
    rectangle_overlap_area,
    sample_flexpart_vertical,
)


def _synthetic_model(path: Path) -> None:
    with netCDF4.Dataset(path, "w") as dataset:
        for name, size in (
            ("time", 2),
            ("height", 2),
            ("latitude", 2),
            ("longitude", 2),
            ("nageclass", 1),
            ("pointspec", 1),
        ):
            dataset.createDimension(name, size)
        time = dataset.createVariable("time", "f8", ("time",))
        time.units = "seconds since 2023-06-01 12:00:00"
        time[:] = [0, 3600]
        dataset.createVariable("height", "f8", ("height",))[:] = [1000, 3000]
        dataset.createVariable("latitude", "f8", ("latitude",))[:] = [44.75, 45.25]
        dataset.createVariable("longitude", "f8", ("longitude",))[:] = [-75.25, -74.75]
        concentration = dataset.createVariable(
            "spec001_mr",
            "f8",
            ("nageclass", "pointspec", "time", "height", "latitude", "longitude"),
        )
        concentration[:] = 0
        concentration[:, :, :, 0, :, :] = 2
        concentration[:, :, :, 1, :, :] = 1


def test_rectangle_overlap_area() -> None:
    polygon = ((0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0), (0.0, 0.0))
    assert (
        rectangle_overlap_area(
            polygon,
            west=1.0,
            east=3.0,
            south=1.0,
            north=3.0,
        )
        == 1.0
    )


def test_flexpart_vertical_operator(tmp_path: Path) -> None:
    model = tmp_path / "model.nc"
    _synthetic_model(model)
    observation = VerticalPlumeObservation(
        observation_id="obs-1",
        event_id="event-1",
        overpass_id="overpass-1",
        observed_at_utc=datetime(2023, 6, 1, 12, 30, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
        product="MISR MINX",
        product_version="V4.0",
        primary_height_agl_m=1200.0,
        upper_height_agl_m=2000.0,
        zero_wind_height_agl_m=1100.0,
        valid_retrieval_points=10,
        polygon=((-75.5, 44.5), (-74.5, 44.5), (-74.5, 45.5), (-75.5, 45.5), (-75.5, 44.5)),
        terrain_reference="test",
        qa_status="Good",
        role="holdout",
        source_path="/input.txt",
        source_sha256="abc",
    )
    sampled = sample_flexpart_vertical(model, observation)
    assert np.isclose(sampled["modelled_mean_height_agl_m"], 1250.0)
    assert sampled["modelled_95pct_top_agl_m"] == 3000.0
    assert [item["weight"] for item in sampled["model_times"]] == [0.5, 0.5]


def test_vertical_evaluation_reports_event_bootstrap_and_upper_diagnostic(
    tmp_path: Path,
) -> None:
    path = tmp_path / "pairs.csv"
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=(
                "observed",
                "modelled",
                "observed_upper_agl_m",
                "modelled_95pct_top_agl_m",
                "event_id",
            ),
        )
        writer.writeheader()
        for index in range(12):
            writer.writerow(
                {
                    "observed": 1000 + index * 100,
                    "modelled": 1050 + index * 100,
                    "observed_upper_agl_m": 2000 + index * 100,
                    "modelled_95pct_top_agl_m": 2100 + index * 100,
                    "event_id": f"event-{index % 3}",
                }
            )

    report = evaluate_vertical_pairs(
        path,
        bootstrap_seed=123,
        bootstrap_repetitions=100,
    )

    assert report["clustered_uncertainty"]["method"] == "event_block_bootstrap"
    assert report["clustered_uncertainty"]["event_count"] == 3
    assert report["upper_height_diagnostic"]["available_for_all_pairs"]
    assert report["upper_height_diagnostic"]["metrics"]["mean_bias"] == 100
