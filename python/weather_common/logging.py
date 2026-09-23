"""Compact JSON logging for long-running weather services."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

_CONTEXT_FIELDS = (
    "request_id",
    "method",
    "path",
    "status",
    "duration_ms",
    "model_code",
    "run_time",
    "asset_id",
    "source_object_id",
)


class JsonFormatter(logging.Formatter):
    """Emit predictable fields and avoid serializing arbitrary record state."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "service": os.getenv("WEATHER_SERVICE_NAME", record.name),
            "event": record.getMessage(),
        }
        for field in _CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"), default=str)
