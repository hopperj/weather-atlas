import json
import logging

from weather_common.logging import JsonFormatter


def test_json_formatter_emits_only_stable_context(monkeypatch) -> None:
    monkeypatch.setenv("WEATHER_SERVICE_NAME", "weather-api")
    record = logging.LogRecord(
        "weather_api",
        logging.INFO,
        __file__,
        1,
        "request_%s",
        ("complete",),
        None,
    )
    record.request_id = "request-1"
    record.duration_ms = 12.5

    payload = json.loads(JsonFormatter().format(record))

    assert payload["service"] == "weather-api"
    assert payload["event"] == "request_complete"
    assert payload["request_id"] == "request-1"
    assert payload["duration_ms"] == 12.5
    assert "args" not in payload
