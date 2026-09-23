import base64
import hashlib
import hmac
import json
from dataclasses import asdict, replace

import pytest
from weather_common.layer_tokens import (
    LayerTokenError,
    LayerTokenPayload,
    create_layer_token,
    verify_layer_token,
)

SECRET = "test-layer-token-secret-that-is-long-enough"


def test_relative_palette_mode_is_signed_and_has_a_distinct_cache_key():
    original = payload()
    relative = replace(original, palette_mode="relative")
    token = create_layer_token(relative, SECRET)
    assert token != create_layer_token(original, SECRET)
    assert verify_layer_token(token, SECRET, now=1_900_000_000) == relative
    with pytest.raises(LayerTokenError, match="palette mode"):
        create_layer_token(replace(original, palette_mode="unknown"), SECRET)


def test_existing_tokens_without_palette_mode_keep_absolute_colours():
    legacy = asdict(payload())
    del legacy["palette_mode"]
    body = json.dumps(legacy).encode()
    signature = hmac.new(SECRET.encode(), body, hashlib.sha256).digest()
    token = ".".join(
        base64.urlsafe_b64encode(part).rstrip(b"=").decode() for part in [body, signature]
    )
    assert verify_layer_token(token, SECRET, now=1_900_000_000).palette_mode == "absolute"


def payload(
    *,
    expires_at: int = 2_000_000_000,
    opacity_cutoff: float | None = None,
) -> LayerTokenPayload:
    return LayerTokenPayload(
        asset_id=42,
        style_id=8,
        asset_sha256="a" * 64,
        display_min=-40,
        display_max=40,
        output_format="webp",
        expires_at=expires_at,
        opacity_cutoff=opacity_cutoff,
    )


def test_layer_token_round_trip() -> None:
    token = create_layer_token(payload(), SECRET)

    assert verify_layer_token(token, SECRET, now=1_900_000_000) == payload()


def test_layer_token_round_trip_preserves_opacity_cutoff() -> None:
    token = create_layer_token(payload(opacity_cutoff=20), SECRET)

    assert verify_layer_token(
        token,
        SECRET,
        now=1_900_000_000,
    ).opacity_cutoff == 20


def test_layer_token_rejects_tampering() -> None:
    token = create_layer_token(payload(), SECRET)
    body, signature = token.split(".")
    tampered = f"{body[:-1]}A.{signature}"

    try:
        verify_layer_token(tampered, SECRET, now=1_900_000_000)
    except LayerTokenError as exc:
        assert "signature" in str(exc) or "payload" in str(exc)
    else:
        raise AssertionError("tampered token was accepted")


def test_layer_token_rejects_expired_payload() -> None:
    token = create_layer_token(payload(expires_at=100), SECRET)

    try:
        verify_layer_token(token, SECRET, now=100)
    except LayerTokenError as exc:
        assert "expired" in str(exc)
    else:
        raise AssertionError("expired token was accepted")
