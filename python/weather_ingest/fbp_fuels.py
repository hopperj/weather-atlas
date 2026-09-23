"""Lossless CWFIS-to-CFFEPS FBP fuel parameter handling."""

from __future__ import annotations

from dataclasses import dataclass

CFFEPS_SUPPORTED_CWFIS_FUEL_BASES = frozenset(
    {
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
        "C7",
        "D1",
        "D2",
        "M1",
        "M2",
        "M3",
        "M4",
        "O1A",
        "O1B",
        "S1",
        "S2",
        "S3",
    }
)


@dataclass(frozen=True, slots=True)
class FbpFuel:
    source_code: str
    model_code: str
    percent_conifer: float = 50.0
    percent_dead_fir: float = 35.0
    grass_curing_percent: float = 80.0
    parameter_source: str = "cffeps_4_1_default"


def has_supported_cffeps_fuel(source_codes: object) -> bool:
    """Return whether at least one Fire M3 code can enter the CFFEPS adapter."""

    if not isinstance(source_codes, list | tuple):
        return False
    return any(
        isinstance(source_code, str)
        and source_code.strip().upper().partition("_")[0]
        in CFFEPS_SUPPORTED_CWFIS_FUEL_BASES
        for source_code in source_codes
    )


def resolve_fbp_fuel(source_code: str, crosswalk: dict[str, str]) -> FbpFuel | None:
    """Map a Fire M3 code while preserving encoded mixedwood percentages."""

    normalized = source_code.strip().upper()
    base, separator, suffix = normalized.partition("_")
    mapped = crosswalk.get(normalized) or crosswalk.get(base)
    if mapped is None:
        return None
    model = mapped.upper()
    percent_conifer = 50.0
    percent_dead_fir = 35.0
    grass_curing = 80.0
    parameter_source = "cffeps_4_1_default"
    if separator:
        try:
            percentage = float(suffix)
        except ValueError:
            return None
        if not 0.0 <= percentage <= 100.0:
            return None
        if model in {"M1", "M2"}:
            percent_conifer = percentage
            parameter_source = "cwfis_fuel_code_suffix"
        elif model in {"M3", "M4"}:
            percent_dead_fir = percentage
            parameter_source = "cwfis_fuel_code_suffix"
        elif model in {"O1A", "O1B"}:
            grass_curing = percentage
            parameter_source = "cwfis_fuel_code_suffix"
        else:
            return None
    model_code = normalized if parameter_source != "cffeps_4_1_default" else model
    return FbpFuel(
        source_code=normalized,
        model_code=model_code,
        percent_conifer=percent_conifer,
        percent_dead_fir=percent_dead_fir,
        grass_curing_percent=grass_curing,
        parameter_source=parameter_source,
    )
