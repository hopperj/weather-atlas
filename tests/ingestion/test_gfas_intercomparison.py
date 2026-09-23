from __future__ import annotations

import csv
from datetime import UTC, date, datetime
from pathlib import Path

import netCDF4
import numpy as np
import pytest
from eccodes import (
    codes_grib_new_from_samples,
    codes_release,
    codes_set,
    codes_set_values,
    codes_write,
)
from weather_ingest.gfas_intercomparison import (
    SECONDS_PER_DAY,
    RegularGrid,
    _cell_area_m2,
    build_gfas_pairs,
)


def _write_emissions(
    path: Path,
    *,
    latitude: float = 1.0,
    days: tuple[date, ...] = (date(2025, 11, 10),),
) -> None:
    with netCDF4.Dataset(path, "w") as dataset:
        dataset.createDimension("row", len(days))
        for name, value in (("event_id", "event-1"), ("species", "PM25")):
            variable = dataset.createVariable(name, str, ("row",))
            variable[:] = np.asarray([value] * len(days), dtype=object)
        time = dataset.createVariable("source_time_start", "i8", ("row",))
        time[:] = [
            int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp()) for day in days
        ]
        for name, value in (
            ("latitude", latitude),
            ("longitude", 0.5),
            ("emitted_mass_kg", 12.0),
        ):
            variable = dataset.createVariable(name, "f8", ("row",))
            variable[:] = [value] * len(days)


def _write_gfas(path: Path, *, days: tuple[date, ...] = (date(2025, 11, 10),)) -> None:
    grid = RegularGrid(
        ni=4,
        nj=3,
        first_latitude=1.0,
        first_longitude=0.5,
        latitude_increment=1.0,
        longitude_increment=1.0,
        latitude_sign=-1,
        longitude_sign=1,
    )
    area = _cell_area_m2(grid, 1.0, 0.5)
    values = np.zeros(12, dtype=np.float64)
    values[0] = 12.0 / area / SECONDS_PER_DAY
    with path.open("wb") as destination:
        for day in days:
            handle = codes_grib_new_from_samples("regular_ll_sfc_grib1")
            try:
                for key, value in (
                    ("Ni", 4),
                    ("Nj", 3),
                    ("latitudeOfFirstGridPointInDegrees", 1.0),
                    ("longitudeOfFirstGridPointInDegrees", 0.5),
                    ("latitudeOfLastGridPointInDegrees", -1.0),
                    ("longitudeOfLastGridPointInDegrees", 3.5),
                    ("iDirectionIncrementInDegrees", 1.0),
                    ("jDirectionIncrementInDegrees", 1.0),
                    ("dataDate", int(day.strftime("%Y%m%d"))),
                    ("dataTime", 0),
                    ("paramId", 210087),
                ):
                    codes_set(handle, key, value)
                codes_set_values(handle, values)
                codes_write(handle, destination)
            finally:
                codes_release(handle)


def test_build_gfas_pairs_converts_flux_and_preserves_provenance(tmp_path: Path) -> None:
    emissions = tmp_path / "emissions.nc"
    gfas = tmp_path / "gfas.grib"
    output = tmp_path / "pairs"
    _write_emissions(emissions)
    _write_gfas(gfas)

    report = build_gfas_pairs(
        emissions_path=emissions,
        gfas_path=gfas,
        output_directory=output,
        start=date(2025, 11, 10),
        end=date(2025, 11, 10),
        bbox=(0, -2, 4, 2),
        species=("PM25",),
        command=["test"],
    )

    pair_set = report["pair_sets"]["PM25"]
    assert pair_set["pair_count"] == 1
    assert pair_set["gfas_total_kg"] == pytest.approx(12.0, rel=1e-5)
    assert pair_set["cffeps_total_kg"] == 12.0
    assert report["acceptance_capable"] is False
    assert len(report["manifest_sha256"]) == 64
    with Path(pair_set["path"]).open(newline="", encoding="utf-8") as source:
        row = next(csv.DictReader(source))
    assert float(row["observed"]) == pytest.approx(12.0, rel=1e-5)
    assert float(row["modelled"]) == 12.0
    assert row["event_id"] == "event-1"


def test_build_gfas_pairs_rejects_candidate_outside_declared_bbox(tmp_path: Path) -> None:
    emissions = tmp_path / "emissions.nc"
    gfas = tmp_path / "gfas.grib"
    _write_emissions(emissions, latitude=5.0)
    _write_gfas(gfas)

    with pytest.raises(ValueError, match="bbox does not contain"):
        build_gfas_pairs(
            emissions_path=emissions,
            gfas_path=gfas,
            output_directory=tmp_path / "pairs",
            start=date(2025, 11, 10),
            end=date(2025, 11, 10),
            bbox=(0, -2, 4, 2),
            species=("PM25",),
        )


def test_build_gfas_pairs_accepts_non_contiguous_dates_and_product_label(
    tmp_path: Path,
) -> None:
    days = (date(2025, 11, 10), date(2025, 11, 12))
    emissions = tmp_path / "emissions.nc"
    gfas = tmp_path / "gfas.grib"
    _write_emissions(emissions, days=days)
    _write_gfas(gfas, days=days)

    report = build_gfas_pairs(
        emissions_path=emissions,
        gfas_path=gfas,
        output_directory=tmp_path / "pairs",
        start=date(2025, 11, 10),
        end=date(2025, 11, 12),
        evaluation_dates=days,
        reference_product="gfas-v1.4.2",
        bbox=(0, -2, 4, 2),
        species=("PM25",),
    )

    assert report["evaluation_dates"] == ["2025-11-10", "2025-11-12"]
    assert report["reference_product"] == "gfas-v1.4.2"
    assert report["gfas_source"]["message_counts"] == {"pm2p5fire": 2}
    assert Path(report["pair_sets"]["PM25"]["path"]).name == ("gfas-v1.4.2-pm25-pairs.csv")


def test_build_gfas_pairs_reads_multiple_immutable_grib_batches(tmp_path: Path) -> None:
    days = (date(2025, 11, 10), date(2025, 11, 12))
    emissions = tmp_path / "emissions.nc"
    first_gfas = tmp_path / "gfas-first.grib"
    second_gfas = tmp_path / "gfas-second.grib"
    _write_emissions(emissions, days=days)
    _write_gfas(first_gfas, days=(days[0],))
    _write_gfas(second_gfas, days=(days[1],))

    report = build_gfas_pairs(
        emissions_path=emissions,
        gfas_path=[first_gfas, second_gfas],
        output_directory=tmp_path / "pairs",
        start=days[0],
        end=days[1],
        evaluation_dates=days,
        bbox=(0, -2, 4, 2),
        species=("PM25",),
    )

    assert report["gfas_source"]["file_count"] == 2
    assert report["gfas_source"]["message_counts"] == {"pm2p5fire": 2}
    with Path(report["pair_sets"]["PM25"]["path"]).open(
        newline="",
        encoding="utf-8",
    ) as source:
        rows = list(csv.DictReader(source))
    assert {int(row["grid_row"]) for row in rows} == {0}
    assert {int(row["grid_column"]) for row in rows} == {0}
