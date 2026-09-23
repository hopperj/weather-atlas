import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException, Request
from weather_api.main import _enforce_sample_rate_limit, _sample_cache_key, app, settings


class LimitExceededRedis:
    def __init__(self) -> None:
        self.expirations: list[tuple[str, int]] = []

    async def incr(self, _key: str) -> int:
        return settings.sample_rate_limit_per_minute + 1

    async def expire(self, key: str, seconds: int) -> None:
        self.expirations.append((key, seconds))


def test_sample_cache_identity_is_stable_and_opaque() -> None:
    run = datetime(2026, 7, 16, 12, tzinfo=UTC)
    first = _sample_cache_key(
        product="hrdps",
        domain="continental",
        run_time=run,
        valid_time=run,
        longitude=-63.5752,
        latitude=44.6488,
        fields=("air_temperature_2m",),
    )
    second = _sample_cache_key(
        product="hrdps",
        domain="continental",
        run_time=run,
        valid_time=run,
        longitude=-63.5752,
        latitude=44.6488,
        fields=("air_temperature_2m",),
    )

    assert first == second
    assert first.startswith("weather:v1:sample:")
    assert "-63" not in first


def test_sample_rate_limit_returns_retry_after() -> None:
    app.state.redis = LimitExceededRedis()
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/sample",
            "headers": [(b"x-forwarded-for", b"203.0.113.8")],
            "client": ("127.0.0.1", 12345),
            "app": app,
        }
    )
    try:
        with pytest.raises(HTTPException) as error:
            asyncio.run(_enforce_sample_rate_limit(request))
    finally:
        del app.state.redis

    assert error.value.status_code == 429
    assert error.value.headers == {"Retry-After": "60"}
