"""Compact signed layer tokens shared by the catalogue and tile services."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import time
from dataclasses import asdict, dataclass
from typing import Any, Literal

from weather_common.display_scales import PaletteMode


class LayerTokenError(ValueError):
    """Raised when a layer token is malformed, tampered with, or expired."""


@dataclass(frozen=True, slots=True)
class LayerTokenPayload:
    asset_id: int
    style_id: int
    asset_sha256: str
    display_min: float
    display_max: float
    output_format: Literal["png", "webp"]
    expires_at: int
    opacity_cutoff: float | None = None
    version: int = 1
    palette_mode: PaletteMode = "absolute"

    def validate(self) -> None:
        if self.version != 1:
            raise LayerTokenError("Unsupported layer token version")
        if self.asset_id <= 0 or self.style_id <= 0:
            raise LayerTokenError("Layer token identifiers must be positive")
        if len(self.asset_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.asset_sha256
        ):
            raise LayerTokenError("Layer token checksum is invalid")
        if not math.isfinite(self.display_min) or not math.isfinite(self.display_max):
            raise LayerTokenError("Layer token display range must be finite")
        if self.display_min >= self.display_max:
            raise LayerTokenError("Layer token display range is invalid")
        if self.opacity_cutoff is not None and not math.isfinite(self.opacity_cutoff):
            raise LayerTokenError("Layer token opacity cutoff must be finite")
        if self.output_format not in {"png", "webp"}:
            raise LayerTokenError("Layer token output format is invalid")
        if self.palette_mode not in {"absolute", "relative"}:
            raise LayerTokenError("Layer token palette mode is invalid")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    try:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(value + padding)
    except (ValueError, UnicodeError) as exc:
        raise LayerTokenError("Layer token encoding is invalid") from exc


def create_layer_token(payload: LayerTokenPayload, secret: str) -> str:
    payload.validate()
    if len(secret) < 24:
        raise LayerTokenError("Layer token secret must contain at least 24 characters")
    body = json.dumps(asdict(payload), separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return f"{_encode(body)}.{_encode(signature)}"


def verify_layer_token(
    token: str,
    secret: str,
    *,
    now: int | None = None,
) -> LayerTokenPayload:
    if len(token) > 1024 or token.count(".") != 1:
        raise LayerTokenError("Layer token format is invalid")
    encoded_body, encoded_signature = token.split(".")
    body = _decode(encoded_body)
    signature = _decode(encoded_signature)
    expected_signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected_signature):
        raise LayerTokenError("Layer token signature is invalid")

    try:
        raw: dict[str, Any] = json.loads(body)
        payload = LayerTokenPayload(
            asset_id=int(raw["asset_id"]),
            style_id=int(raw["style_id"]),
            asset_sha256=str(raw["asset_sha256"]),
            display_min=float(raw["display_min"]),
            display_max=float(raw["display_max"]),
            output_format=str(raw["output_format"]),  # type: ignore[arg-type]
            expires_at=int(raw["expires_at"]),
            opacity_cutoff=(
                float(raw["opacity_cutoff"])
                if raw.get("opacity_cutoff") is not None
                else None
            ),
            version=int(raw["version"]),
            palette_mode=str(raw.get("palette_mode", "absolute")),  # type: ignore[arg-type]
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise LayerTokenError("Layer token payload is invalid") from exc

    payload.validate()
    current_time = int(time.time()) if now is None else now
    if payload.expires_at <= current_time:
        raise LayerTokenError("Layer token has expired")
    return payload
