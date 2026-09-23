import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from weather_api.forecast import precipitation_outlook, utc_text
from weather_api.repository import CatalogueNotFoundError

HOUR = timedelta(hours=1)
RUN = datetime(2026, 9, 7, tzinfo=UTC)
NOW = RUN + 12 * HOUR
ONE = "total_precipitation_1h"
THREE = "total_precipitation_3h"


def region(start=0, end=12, official=None):
    return {
        "id": "0123456789abcdef",
        "issuedAt": utc_text(NOW),
        "longitude": -63.58,
        "latitude": 44.66,
        "periods": [
            {
                "start": utc_text(RUN + start * HOUR),
                "end": utc_text(RUN + end * HOUR),
                "precipitationAmount": official,
            }
        ],
    }


class Catalogue:
    def __init__(self, frames):
        self.frames = frames
        self.listed = []

    async def list_runs(self, product, limit, before=None, field=None):
        assert product == "gdps" and limit == 4
        assert before == NOW + timedelta(microseconds=1)
        return [{"run_time": run} for run in self.frames]

    async def list_times(self, product, run_time, field=None):
        self.listed.append((run_time, field))
        return [
            {"valid_time": run_time + lead * HOUR, "forecast_hour": lead}
            for lead in self.frames[run_time].get(field, [])
        ]


async def sample(_repo, **kwargs):
    assert kwargs["product"] == "gdps" and kwargs["domain"] == "global"
    assert kwargs["longitude"] == -63.58 and kwargs["latitude"] == 44.66
    return SimpleNamespace(value=1 if kwargs["field"] == ONE else 3, unit="mm", nodata=False)


def result(frames, place=None, sampler=sample):
    return asyncio.run(precipitation_outlook(Catalogue(frames), place or region(), NOW, sampler))


def test_full_period_includes_elapsed_hours_without_double_counting():
    response = result({RUN: {ONE: range(1, 13), THREE: range(3, 13, 3)}})
    row = response["periods"][0]
    assert row["precipitationMm"] == 12
    assert row["status"] == "complete" and row["runTime"] == utc_text(RUN)
    assert len(row["intervals"]) == 12
    assert all(interval["field"] == ONE for interval in row["intervals"])
    assert response["issuedAt"] == utc_text(NOW)


def test_hourly_to_three_hourly_tail_tiles_exactly_without_dead_end():
    response = result({RUN: {ONE: [82, 83, 84, 87, 90], THREE: [84, 87, 90]}}, region(81, 90))
    row = response["periods"][0]
    assert row["precipitationMm"] == 9
    assert [interval["field"] for interval in row["intervals"]] == [ONE] * 3 + [THREE] * 2
    assert row["intervals"][0]["start"] == row["start"]
    assert row["intervals"][-1]["end"] == row["end"]
    assert all(
        a["end"] == b["start"] for a, b in zip(row["intervals"], row["intervals"][1:], strict=False)
    )


@pytest.mark.parametrize("official", ["0 mm", "5 to 10 mm", "2 cm"])
def test_existing_bulletin_amounts_never_request_model_data(official):
    response = asyncio.run(precipitation_outlook(object(), region(official=official), NOW, sample))
    assert response["periods"][0]["status"] == "official"
    assert response["periods"][0]["precipitationMm"] is None


@pytest.mark.parametrize(
    "frames,place",
    [
        ({RUN: {ONE: [1, 3]}}, region(0, 3)),  # Missing hour 2 is not zero.
        ({RUN: {THREE: [3]}}, region(1, 3)),  # Do not prorate an overlap.
        ({RUN: {ONE: [1, 2]}}, region(0.5, 1.5)),  # Half-hour boundary.
        ({RUN: {THREE: [171]}}, region(168, 171)),  # Beyond the configured lead horizon.
        ({}, region()),
    ],
)
def test_incomplete_periods_remain_missing(frames, place):
    row = result(frames, place)["periods"][0]
    assert row["status"] == "missing" and row["precipitationMm"] is None
    assert row["runTime"] is None and row["intervals"] == []


def test_no_mixing_of_runs_but_older_complete_cycle_is_eligible():
    newer = RUN + 12 * HOUR
    frames = {newer: {ONE: [1]}, RUN: {ONE: [14]}}
    assert result(frames, region(12, 14))["periods"][0]["status"] == "missing"
    frames[RUN][ONE] = [13, 14]
    row = result(frames, region(12, 14))["periods"][0]
    assert row["status"] == "complete" and row["runTime"] == utc_text(RUN)
    # Once the newer cycle is complete, it takes precedence.
    frames[newer][ONE] = [1, 2]
    row = result(frames, region(12, 14))["periods"][0]
    assert row["runTime"] == utc_text(newer)


def test_future_old_and_initialized_after_period_start_cycles_are_rejected():
    catalogue = Catalogue(
        {
            RUN + 24 * HOUR: {ONE: range(1, 13)},
            RUN - 60 * HOUR: {ONE: range(1, 13)},
            RUN + 12 * HOUR: {ONE: range(1, 13)},
        }
    )
    response = asyncio.run(precipitation_outlook(catalogue, region(8, 21), NOW, sample))
    assert response["periods"][0]["status"] == "missing"
    assert catalogue.listed == []


@pytest.mark.parametrize(
    "bad", [None, -1, float("nan"), float("inf"), "unit", "nodata", "file", "asset"]
)
def test_invalid_samples_never_become_partial_totals(bad):
    async def invalid(_repo, **kwargs):
        if bad == "file":
            raise FileNotFoundError
        if bad == "asset":
            raise CatalogueNotFoundError
        return SimpleNamespace(
            value=1 if isinstance(bad, str) else bad,
            unit="inches" if bad == "unit" else "mm",
            nodata=bad == "nodata",
        )

    row = result({RUN: {ONE: [1, 2, 3]}}, region(0, 3), invalid)["periods"][0]
    assert row["status"] == "missing" and row["precipitationMm"] is None


def test_missing_hourly_sample_can_use_complete_three_hour_alternative():
    calls = []

    async def one_gap(repo, **kwargs):
        calls.append((kwargs["field"], kwargs["valid_time"]))
        if kwargs["field"] == ONE and kwargs["valid_time"] == RUN + 2 * HOUR:
            raise CatalogueNotFoundError
        return await sample(repo, **kwargs)

    row = result({RUN: {ONE: [1, 2, 3], THREE: [3]}}, region(0, 3), one_gap)["periods"][0]
    assert row["precipitationMm"] == 3
    assert len(row["intervals"]) == 1 and row["intervals"][0]["field"] == THREE
    assert len(calls) == len(set(calls))


def test_zero_model_total_is_valid_and_values_are_summed_before_rounding():
    async def zero(_repo, **_kwargs):
        return SimpleNamespace(value=0, unit="mm", nodata=False)

    async def small(_repo, **_kwargs):
        return SimpleNamespace(value=0.004, unit="mm", nodata=False)

    frames = {RUN: {ONE: range(1, 13)}}
    assert result(frames, sampler=zero)["periods"][0]["precipitationMm"] == 0
    assert result(frames, sampler=small)["periods"][0]["precipitationMm"] == 0.05
