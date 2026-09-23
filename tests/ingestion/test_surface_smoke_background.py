from datetime import UTC, datetime, timedelta

from weather_ingest.naps_pm25 import NapsPm25Observation
from weather_ingest.surface_smoke_background import calculate_surface_enhancements


def test_background_uses_same_utc_hour_and_never_drops_high_values() -> None:
    target = datetime(2023, 6, 15, 12, tzinfo=UTC)
    values = [1, 2, 3, 4, 5, 6, 100]
    observations = [
        NapsPm25Observation(
            station_id="A",
            method_code="1",
            city="Test",
            province="NS",
            latitude=45,
            longitude=-63,
            interval_end_utc=target,
            value_ug_m3=20,
        )
    ]
    observations.extend(
        NapsPm25Observation(
            station_id="A",
            method_code="1",
            city="Test",
            province="NS",
            latitude=45,
            longitude=-63,
            interval_end_utc=target + timedelta(days=index + 1),
            value_ug_m3=value,
        )
        for index, value in enumerate(values)
    )
    result, rejections = calculate_surface_enhancements(
        observations,
        target_keys={("A", target)},
        excluded_background_dates=set(),
    )
    assert not rejections
    assert result[0].background_sample_count == 7
    assert result[0].background_pm25_ug_m3 == 4
    assert result[0].enhancement_pm25_ug_m3 == 16
