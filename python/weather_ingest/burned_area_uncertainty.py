"""Independent burned-area uncertainty curves for W6 sensitivity runs."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any


def build_independent_area_curves(
    records: list[dict[str, Any]],
    *,
    central_source: str = "MCD64A1",
) -> dict[str, Any]:
    """Select coherent event-level low/high products without percentage scaling."""

    by_event_source: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for record in records:
        area = float(record["area_ha"])
        if not math.isfinite(area) or area < 0:
            raise ValueError("burned-area inputs must be finite and non-negative")
        key = (str(record["event_id"]), str(record["source"]))
        day = str(record["date"])
        if day in by_event_source[key]:
            raise ValueError(f"duplicate burned-area record for {key} on {day}")
        by_event_source[key][day] = area
    sources_by_event: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
    for (event_id, source), daily in by_event_source.items():
        sources_by_event[event_id][source] = daily

    curves = []
    event_curves = []
    missing_central = []
    for event_id, source_daily in sorted(sources_by_event.items()):
        if central_source not in source_daily:
            missing_central.append({"event_id": event_id})
            continue
        totals = {
            source: sum(daily.values())
            for source, daily in source_daily.items()
            if sum(daily.values()) > 0
        }
        if central_source not in totals:
            missing_central.append(
                {"event_id": event_id, "reason": "central source has zero total area"}
            )
            continue
        low_source = min(totals, key=lambda source: (totals[source], source))
        high_source = max(totals, key=lambda source: (totals[source], source))
        selected = {
            "low": low_source,
            "central": central_source,
            "high": high_source,
        }
        selected_daily = {
            name: {
                day: area
                for day, area in sorted(source_daily[source].items())
                if area > 0
            }
            for name, source in selected.items()
        }
        event_curves.append(
            {
                "event_id": event_id,
                "low_source": low_source,
                "central_source": central_source,
                "high_source": high_source,
                "low_daily_increment_ha": selected_daily["low"],
                "central_daily_increment_ha": selected_daily["central"],
                "high_daily_increment_ha": selected_daily["high"],
                "source_totals_ha": dict(sorted(totals.items())),
                "low_total_ha": totals[low_source],
                "central_total_ha": totals[central_source],
                "high_total_ha": totals[high_source],
            }
        )
        all_days = sorted(
            set(selected_daily["low"])
            | set(selected_daily["central"])
            | set(selected_daily["high"])
        )
        for day in all_days:
            curves.append(
                {
                    "event_id": event_id,
                    "date": day,
                    "low_area_ha": selected_daily["low"].get(day, 0.0),
                    "central_area_ha": selected_daily["central"].get(day, 0.0),
                    "high_area_ha": selected_daily["high"].get(day, 0.0),
                    "low_source": low_source,
                    "central_source": central_source,
                    "high_source": high_source,
                }
            )
    totals = {
        name: sum(item[f"{name}_total_ha"] for item in event_curves)
        for name in ("low", "central", "high")
    }
    return {
        "schema_version": 1,
        "artifact_type": "independent-burned-area-uncertainty-curves",
        "method": (
            "per-event lowest/highest positive-total independent product, "
            "retaining each selected product's internally coherent daily timing"
        ),
        "arbitrary_percentage_scaling_used": False,
        "central_source": central_source,
        "curve_count": len(curves),
        "event_curve_count": len(event_curves),
        "missing_central": missing_central,
        "totals_ha": totals,
        "nontrivial_at_cohort_scale": totals["low"] < totals["high"],
        "event_curves": event_curves,
        "curves": curves,
    }


def write_area_curves(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)
    checksum_path = path.with_suffix(path.suffix + ".sha256")
    checksum_path.write_text(
        hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n"
    )


def build_area_sensitivity_records(
    *,
    source_ledger: dict[str, Any],
    mcd64a1_report: dict[str, Any],
    vnp64a1_report: dict[str, Any],
    provider_area_by_uid_ha: dict[int, float],
    include_reserve: bool = False,
) -> dict[str, Any]:
    """Join products while allocating shared provider perimeters without double counting."""

    source_events = list(source_ledger["retained_events"])
    if include_reserve:
        source_events.extend(source_ledger["reserve_events"])
    selected = {
        str(item["event_id"]): item
        for item in source_events
    }
    mcd = {str(item["event_id"]): item for item in mcd64a1_report["events"]}
    vnp = {str(item["event_id"]): item for item in vnp64a1_report["events"]}
    missing_product_events = sorted(set(selected) - set(mcd) | (set(selected) - set(vnp)))
    if missing_product_events:
        raise ValueError(f"selected events missing from area products: {missing_product_events}")
    mcd_totals = {
        event_id: sum(
            float(value)
            for value in mcd[event_id]["daily_area"]["central_daily_increment_ha"].values()
        )
        for event_id in selected
    }
    uid_owners: dict[int, list[str]] = defaultdict(list)
    for event_id, event in selected.items():
        for uid in {int(value) for value in event["source_perimeter_uids"]}:
            uid_owners[uid].append(event_id)
    provider_allocation_by_event: dict[str, float] = defaultdict(float)
    provider_allocation_details: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for uid, owners in sorted(uid_owners.items()):
        if uid not in provider_area_by_uid_ha:
            continue
        denominator = sum(mcd_totals[event_id] for event_id in owners)
        if denominator <= 0:
            raise ValueError(f"provider perimeter {uid} has no positive MCD allocation weight")
        for event_id in owners:
            fraction = mcd_totals[event_id] / denominator
            allocated_area = provider_area_by_uid_ha[uid] * fraction
            provider_allocation_by_event[event_id] += allocated_area
            provider_allocation_details[event_id].append(
                {
                    "uid": uid,
                    "provider_area_ha": provider_area_by_uid_ha[uid],
                    "owner_count": len(owners),
                    "allocation_fraction": fraction,
                    "allocated_area_ha": allocated_area,
                }
            )

    records = []
    event_summary = []
    for event_id, selected_event in sorted(selected.items()):
        mcd_daily = mcd[event_id]["daily_area"]["central_daily_increment_ha"]
        vnp_daily = vnp[event_id]["daily_area"]["central_daily_increment_ha"]
        provider_uids = [int(value) for value in selected_event["source_perimeter_uids"]]
        available_provider_uids = [uid for uid in provider_uids if uid in provider_area_by_uid_ha]
        provider_total = provider_allocation_by_event[event_id]
        mcd_total = mcd_totals[event_id]
        vnp_total = sum(float(value) for value in vnp_daily.values())
        all_dates = sorted(set(mcd_daily) | set(vnp_daily))
        for day in all_dates:
            records.append(
                {
                    "event_id": event_id,
                    "date": day,
                    "source": "MCD64A1",
                    "area_ha": float(mcd_daily.get(day, 0.0)),
                }
            )
            if vnp_total > 0:
                records.append(
                    {
                        "event_id": event_id,
                        "date": day,
                        "source": "VNP64A1",
                        "area_ha": float(vnp_daily.get(day, 0.0)),
                    }
                )
            if provider_total > 0 and mcd_total > 0:
                records.append(
                    {
                        "event_id": event_id,
                        "date": day,
                        "source": "CWFIS_provider_perimeters",
                        "area_ha": (provider_total * float(mcd_daily.get(day, 0.0)) / mcd_total),
                    }
                )
        event_summary.append(
            {
                "event_id": event_id,
                "mcd64a1_total_ha": mcd_total,
                "vnp64a1_total_ha": vnp_total,
                "provider_perimeter_total_ha": provider_total,
                "provider_perimeter_uid_count": len(provider_uids),
                "provider_perimeter_uid_available_count": len(available_provider_uids),
                "provider_perimeter_allocations": provider_allocation_details[event_id],
                "provider_temporal_allocation": (
                    "MCD64A1 central daily fractions after shared-perimeter allocation"
                    if provider_total > 0
                    else None
                ),
            }
        )
    return {
        "schema_version": 1,
        "artifact_type": "w6-independent-area-sensitivity-records",
        "cohort_role": "retained_and_reserve" if include_reserve else "retained",
        "provider_area_units": "hectares",
        "shared_provider_perimeter_allocation": (
            "allocate each unique provider perimeter among selected event owners "
            "in proportion to independent MCD64A1 event totals"
        ),
        "shared_provider_perimeter_count": sum(
            len(owners) > 1 for owners in uid_owners.values()
        ),
        "provider_area_allocation_closure": {
            "unique_available_provider_area_ha": sum(
                provider_area_by_uid_ha[uid]
                for uid in uid_owners
                if uid in provider_area_by_uid_ha
            ),
            "allocated_provider_area_ha": sum(provider_allocation_by_event.values()),
        },
        "records": records,
        "events": event_summary,
        "record_count": len(records),
    }


def augment_event_area_report(
    *,
    event_area_report: dict[str, Any],
    independent_curves: dict[str, Any],
    retained_event_ids: set[str],
) -> dict[str, Any]:
    """Create the cohort-specific W6 area report consumed by the candidate runner."""

    report = deepcopy(event_area_report)
    curve_by_event = {
        str(item["event_id"]): item for item in independent_curves["event_curves"]
    }
    missing = sorted(retained_event_ids - set(curve_by_event))
    if missing:
        raise ValueError(f"retained events lack independent area curves: {missing}")
    found = set()
    for event in report["events"]:
        event_id = str(event["event_id"])
        if event_id not in retained_event_ids:
            if event.get("burned_area_eligible"):
                event["burned_area_eligible"] = False
                reasons = list(event.get("ineligibility_reasons", []))
                reasons.append("outside_frozen_retained_cohort")
                event["ineligibility_reasons"] = sorted(set(reasons))
            continue
        if not event.get("burned_area_eligible"):
            raise ValueError(f"retained event is not area eligible: {event_id}")
        found.add(event_id)
        curve = curve_by_event[event_id]
        event["daily_area"]["independent_low_daily_increment_ha"] = curve[
            "low_daily_increment_ha"
        ]
        event["daily_area"]["independent_high_daily_increment_ha"] = curve[
            "high_daily_increment_ha"
        ]
        event["independent_area_sensitivity"] = {
            key: curve[key]
            for key in (
                "low_source",
                "central_source",
                "high_source",
                "source_totals_ha",
                "low_total_ha",
                "central_total_ha",
                "high_total_ha",
            )
        }
    if found != retained_event_ids:
        raise ValueError(
            f"retained events absent from event-area report: {sorted(retained_event_ids - found)}"
        )
    report["artifact_type"] = "w6-cohort-specific-event-area-report"
    report["w6_area_sensitivity"] = {
        "retained_event_ids": sorted(retained_event_ids),
        "retained_event_count": len(retained_event_ids),
        "independent_curve_method": independent_curves["method"],
        "arbitrary_percentage_scaling_used": independent_curves[
            "arbitrary_percentage_scaling_used"
        ],
        "nontrivial_at_cohort_scale": independent_curves[
            "nontrivial_at_cohort_scale"
        ],
        "totals_ha": independent_curves["totals_ha"],
    }
    return report
