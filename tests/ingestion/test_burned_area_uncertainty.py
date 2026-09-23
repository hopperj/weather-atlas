from weather_ingest.burned_area_uncertainty import (
    augment_event_area_report,
    build_area_sensitivity_records,
    build_independent_area_curves,
)


def test_independent_area_envelope() -> None:
    report = build_independent_area_curves(
        [
            {"event_id": "A", "date": "2023-06-01", "source": "MCD64A1", "area_ha": 10},
            {"event_id": "A", "date": "2023-06-01", "source": "VNP64A1", "area_ha": 8},
            {"event_id": "A", "date": "2023-06-01", "source": "provider", "area_ha": 15},
        ]
    )
    curve = report["curves"][0]
    assert (curve["low_area_ha"], curve["central_area_ha"], curve["high_area_ha"]) == (
        8,
        10,
        15,
    )
    assert report["nontrivial_at_cohort_scale"]
    assert not report["arbitrary_percentage_scaling_used"]


def test_area_records_keep_provider_total_but_use_frozen_mcd_timing() -> None:
    source = {
        "retained_events": [{"event_id": "A", "source_perimeter_uids": [1]}],
        "reserve_events": [],
    }

    def product(values: dict[str, int]) -> dict[str, object]:
        return {
            "events": [
                {
                    "event_id": "A",
                    "daily_area": {"central_daily_increment_ha": values},
                }
            ]
        }

    report = build_area_sensitivity_records(
        source_ledger=source,
        mcd64a1_report=product({"2023-06-01": 25, "2023-06-02": 75}),
        vnp64a1_report=product({"2023-06-01": 20, "2023-06-02": 60}),
        provider_area_by_uid_ha={1: 200},
    )
    provider = [item for item in report["records"] if item["source"] == "CWFIS_provider_perimeters"]
    assert [item["area_ha"] for item in provider] == [50, 150]


def test_area_records_allocate_shared_provider_perimeter_without_double_counting() -> None:
    source = {
        "retained_events": [
            {"event_id": "A", "source_perimeter_uids": [1]},
            {"event_id": "B", "source_perimeter_uids": [1]},
        ],
        "reserve_events": [],
    }

    def product(a: int, b: int) -> dict[str, object]:
        return {
            "events": [
                {
                    "event_id": "A",
                    "daily_area": {"central_daily_increment_ha": {"2023-06-01": a}},
                },
                {
                    "event_id": "B",
                    "daily_area": {"central_daily_increment_ha": {"2023-06-01": b}},
                },
            ]
        }

    report = build_area_sensitivity_records(
        source_ledger=source,
        mcd64a1_report=product(25, 75),
        vnp64a1_report=product(20, 60),
        provider_area_by_uid_ha={1: 200},
    )

    provider = {
        item["event_id"]: item["area_ha"]
        for item in report["records"]
        if item["source"] == "CWFIS_provider_perimeters"
    }
    assert provider == {"A": 50, "B": 150}
    assert report["shared_provider_perimeter_count"] == 1
    assert report["provider_area_allocation_closure"] == {
        "unique_available_provider_area_ha": 200,
        "allocated_provider_area_ha": 200,
    }


def test_area_curves_retain_one_coherent_product_timing_per_event() -> None:
    report = build_independent_area_curves(
        [
            {"event_id": "A", "date": "2023-06-01", "source": "MCD64A1", "area_ha": 10},
            {"event_id": "A", "date": "2023-06-02", "source": "MCD64A1", "area_ha": 10},
            {"event_id": "A", "date": "2023-06-01", "source": "VNP64A1", "area_ha": 0},
            {"event_id": "A", "date": "2023-06-02", "source": "VNP64A1", "area_ha": 15},
            {"event_id": "A", "date": "2023-06-01", "source": "provider", "area_ha": 30},
            {"event_id": "A", "date": "2023-06-02", "source": "provider", "area_ha": 30},
        ]
    )

    event = report["event_curves"][0]
    assert event["low_source"] == "VNP64A1"
    assert event["low_daily_increment_ha"] == {"2023-06-02": 15}
    assert event["high_source"] == "provider"
    assert event["high_daily_increment_ha"] == {
        "2023-06-01": 30,
        "2023-06-02": 30,
    }


def test_w6_event_area_report_is_limited_to_frozen_retained_cohort() -> None:
    base = {
        "operator_version": "mcd64a1-event-area-v2",
        "events": [
            {
                "event_id": "A",
                "burned_area_eligible": True,
                "ineligibility_reasons": [],
                "daily_area": {
                    "central_daily_increment_ha": {"2023-06-01": 10},
                    "earliest_timing_daily_increment_ha": {"2023-05-31": 10},
                    "latest_timing_daily_increment_ha": {"2023-06-02": 10},
                },
            },
            {
                "event_id": "B",
                "burned_area_eligible": True,
                "ineligibility_reasons": [],
                "daily_area": {"central_daily_increment_ha": {"2023-06-01": 5}},
            },
        ],
    }
    curves = build_independent_area_curves(
        [
            {"event_id": "A", "date": "2023-06-01", "source": "MCD64A1", "area_ha": 10},
            {"event_id": "A", "date": "2023-06-01", "source": "VNP64A1", "area_ha": 8},
            {"event_id": "A", "date": "2023-06-01", "source": "provider", "area_ha": 15},
        ]
    )

    report = augment_event_area_report(
        event_area_report=base,
        independent_curves=curves,
        retained_event_ids={"A"},
    )

    retained, excluded = report["events"]
    assert retained["daily_area"]["independent_low_daily_increment_ha"] == {
        "2023-06-01": 8
    }
    assert retained["daily_area"]["independent_high_daily_increment_ha"] == {
        "2023-06-01": 15
    }
    assert not excluded["burned_area_eligible"]
    assert "outside_frozen_retained_cohort" in excluded["ineligibility_reasons"]
