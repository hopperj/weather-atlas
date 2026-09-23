from datetime import UTC, datetime, timedelta

import httpx
import pytest
from weather_ingest.downloader import SourceUnavailableError, classify_source_failure

NOW = datetime(2026, 9, 7, 2, tzinfo=UTC)


@pytest.mark.parametrize("status", [404, 410])
@pytest.mark.parametrize("age", [1, 18, 19, 720])
def test_only_confirmed_missing_objects_outside_retry_window_are_retired(status, age):
    request = httpx.Request("GET", "https://dd.weather.gc.ca/old.grib2")
    response = httpx.Response(status, request=request)
    error = httpx.HTTPStatusError("provider response", request=request, response=response)
    result = classify_source_failure(
        error, reference_time=NOW - timedelta(hours=age), now=NOW, retry_window_hours=18
    )
    assert isinstance(result, SourceUnavailableError) == (age > 18)
    if age <= 18:
        assert result is error
    else:
        assert "historical gap retained" in str(result)


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
def test_other_http_errors_remain_retryable_even_for_old_sources(status):
    request = httpx.Request("GET", "https://dd.weather.gc.ca/old.grib2")
    response = httpx.Response(status, request=request)
    error = httpx.HTTPStatusError("provider response", request=request, response=response)
    assert (
        classify_source_failure(
            error, reference_time=NOW - timedelta(days=30), now=NOW, retry_window_hours=18
        )
        is error
    )


@pytest.mark.parametrize("error", [httpx.ConnectError("offline"), ValueError("bad GRIB")])
def test_network_and_validation_failures_are_not_hidden(error):
    assert (
        classify_source_failure(
            error, reference_time=NOW - timedelta(days=30), now=NOW, retry_window_hours=18
        )
        is error
    )
