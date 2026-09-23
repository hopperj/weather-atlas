from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

import pytest
from weather_ingest.gfas_ads import (
    GFAS_SHORT_NAMES,
    build_archive_manifest,
    request_payload,
    split_contiguous_ranges,
    validate_gfas_grib,
)


def test_split_contiguous_ranges_preserves_only_requested_dates() -> None:
    dates = [
        date(2023, 5, 1),
        date(2023, 5, 2),
        date(2023, 5, 3),
        date(2023, 5, 7),
        date(2023, 5, 8),
    ]
    assert split_contiguous_ranges(dates, maximum_days=2) == [
        (date(2023, 5, 1), date(2023, 5, 2)),
        (date(2023, 5, 3), date(2023, 5, 3)),
        (date(2023, 5, 7), date(2023, 5, 8)),
    ]


def test_request_uses_live_ads_form_dimension_names() -> None:
    payload = request_payload(date(2023, 5, 1), date(2023, 5, 2))
    assert payload["date"] == "2023-05-01/2023-05-02"
    assert payload["data_format"] == "grib"
    assert "wildfire_flux_of_particulate_matter_d_2_5_µm" in payload["variable"]


def _runner_for_one_day(
    command: list[str],
    **_: object,
) -> subprocess.CompletedProcess[str]:
    requested = command[command.index("-p") + 1]
    if requested.startswith("edition,"):
        lines = [
            (f"1 ecmf regular_ll 3600 1800 surface 0 20230501 0 0-24 {short_name} {index + 1} unit")
            for index, short_name in enumerate(sorted(GFAS_SHORT_NAMES))
        ]
    else:
        lines = [f"{short_name} 6480000 0 0 1 0.1" for short_name in sorted(GFAS_SHORT_NAMES)]
    return subprocess.CompletedProcess(command, 0, stdout="\n".join(lines), stderr="")


def test_validate_gfas_grib_requires_complete_date_parameter_product(
    tmp_path: Path,
) -> None:
    source = tmp_path / "gfas.grib"
    source.write_bytes(b"GRIB")
    result = validate_gfas_grib(
        source,
        [date(2023, 5, 1)],
        runner=_runner_for_one_day,
    )
    assert result["message_count"] == 9
    assert set(result["parameters"]) == GFAS_SHORT_NAMES


def test_build_archive_manifest_rejects_incomplete_frozen_dates(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"dates": ["2023-05-01"]}), encoding="utf-8")
    record = {
        "validation": {"dates": ["2023-05-01"]},
    }
    with pytest.raises(ValueError, match="exactly cover"):
        build_archive_manifest(
            cohort_id="test",
            ledger_path=ledger,
            dates=[date(2023, 5, 1), date(2023, 5, 2)],
            records=[record],
            request_maximum_days=7,
        )
