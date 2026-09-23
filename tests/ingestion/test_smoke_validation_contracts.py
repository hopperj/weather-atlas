from __future__ import annotations

import csv
from pathlib import Path

import pytest
from weather_ingest.smoke_validation_contracts import (
    PairRecord,
    RejectionLedger,
    clustered_bootstrap_metrics,
    write_pair_records,
)


def test_rejection_ledger_reconciles_and_requires_specific_reasons() -> None:
    ledger = RejectionLedger()
    ledger.retain("a")
    ledger.reject("b", "missing_model_hour")
    assert ledger.report()["rejection_counts"] == {"missing_model_hour": 1}
    with pytest.raises(ValueError, match="specific"):
        ledger.reject("c", "other")


def test_write_pair_records_preserves_metadata_and_rejects_duplicates(
    tmp_path: Path,
) -> None:
    pair = PairRecord(
        pair_id="p1",
        observed=1.0,
        modelled=1.25,
        units="ug m-3",
        event_id="event-1",
        role="primary",
        station_id="station-1",
        time_utc="2023-06-01T01:00:00Z",
        metadata={"operator": "containing_cell"},
    )
    path = tmp_path / "pairs.csv"
    manifest = write_pair_records(path, [pair])
    assert manifest["pair_count"] == 1
    with path.open(encoding="utf-8") as source:
        row = next(csv.DictReader(source))
    assert row["metadata_json"] == '{"operator":"containing_cell"}'
    with pytest.raises(ValueError, match="duplicate"):
        write_pair_records(tmp_path / "duplicates.csv", [pair, pair])


def test_clustered_bootstrap_is_deterministic_and_resamples_events() -> None:
    pairs = [
        PairRecord(
            pair_id=f"{event}-{hour}",
            observed=float(hour + 1),
            modelled=float(hour + 1) * factor,
            units="kg",
            event_id=event,
            role="primary",
            station_id=f"station-{event}",
        )
        for event, factor in (("a", 1.0), ("b", 2.0), ("c", 0.5))
        for hour in range(3)
    ]
    first = clustered_bootstrap_metrics(pairs, replicates=200, seed=42)
    second = clustered_bootstrap_metrics(pairs, replicates=200, seed=42)
    assert first == second
    assert first["event_count"] == 3
    assert "normalized_mean_bias" in first["intervals"]
