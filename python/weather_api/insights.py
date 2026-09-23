"""Read-only prepared forecasts and bounded local station queries. No upstream I/O."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from psycopg.errors import UndefinedTable

router = APIRouter()
Field = Literal[
    "temperatureC", "humidityPercent", "windKmh", "gustKmh", "precipitationMm", "pressureHpa"
]
Area = Annotated[str, Query(pattern=r"^[a-f0-9]{16}$")]
StationID = Annotated[str, Query(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


class InsightReader:
    def __init__(self, database):
        self.database = database

    async def rows(self, query, parameters):
        try:
            async with self.database.transaction() as transaction:
                return await transaction.fetch_all(f"insights/{query}.sql", parameters)
        except UndefinedTable as error:
            raise HTTPException(503, "This optional feature is not ready on the server") from error


def repository(request: Request):
    database = getattr(request.app.state, "database", None)
    if database is None:
        raise HTTPException(503, "Optional weather features are not ready")
    return InsightReader(database)


Reader = Annotated[InsightReader, Depends(repository)]


async def prepared_hourly(request: Request, region: dict, now: datetime) -> dict | None:
    """Use the rollout read model only after it covers the current 72-hour window.

    Outside the prepared rollout, the existing forecast API remains compatible.
    No new collection is dispatched from this read path.
    """
    if getattr(request.app.state, "database", None) is None:
        return None
    try:
        rows = await repository(request).rows(
            "prepared", {"area_id": region["id"], "kind": "hourly"}
        )
    except HTTPException as error:
        # Additive rollout: a missing optional table must not disable the established forecast.
        if error.status_code == 503:
            return None
        raise
    if not rows or rows[0]["valid_until"] <= now:
        return None
    payload = rows[0]["payload"]
    start = datetime.fromisoformat(payload["start"].replace("Z", "+00:00"))
    if (
        start != now.replace(minute=0, second=0, microsecond=0)
        or payload.get("latitude") != region["latitude"]
        or payload.get("longitude") != region["longitude"]
        or payload["availableHours"] < 60
    ):
        return None
    return payload


async def prepared(
    request: Request, reader: InsightReader, area: str, kind: str, extra: dict | None = None
):
    rows = await reader.rows("prepared", {"area_id": area, "kind": kind})
    if not rows:
        raise HTTPException(404, "Data preparation is pending for this location")
    row = rows[0]
    stale = row["valid_until"] <= datetime.now(UTC)
    # Freshness crossing expiry changes the validator even if collection has stopped.
    # Optional history changes independently of the scheduled comparison read model.
    suffix = hashlib.sha256(json.dumps(extra, sort_keys=True).encode()).hexdigest() if extra else ""
    etag = f'W/"{row["content_version"]}-{int(stale)}{suffix}"'
    headers = {"ETag": etag, "Cache-Control": "private, max-age=0, must-revalidate"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(
        {
            **row["payload"],
            **(extra or {}),
            "stale": stale,
            "contentVersion": row["content_version"],
        },
        headers=headers,
    )


@router.get("/api/v1/forecast/changes", tags=["forecast"])
async def forecast_changes(
    request: Request,
    reader: Reader,
    area_id: Area,
    baseline: Literal["previous"] = "previous",
    include_forecasts: bool = False,
):
    extra = None
    if include_forecasts:
        # Only read ETL-owned immutable history. No ingestion, model sampling, or
        # inference runs here, and existing clients retain their original payload.
        revisions = await reader.rows("revisions", {"area_id": area_id, "source": "bulletin"})
        extra = {"bulletins": bulletin_pair(revisions)}
    return await prepared(request, reader, area_id, "changes", extra)


def bulletin_pair(revisions: list[dict]) -> dict:
    """Bounded source forecasts, not numeric highlights or an inferred comparison."""
    if not revisions:
        return {"state": "building_history", "current": None, "previous": None}

    def public_bulletin(payload):
        return {
            **{key: payload[key] for key in ("id", "latitude", "longitude", "issuedAt")},
            "periods": [
                {
                    key: period.get(key)
                    for key in (
                        "name",
                        "start",
                        "end",
                        "temperatureClass",
                        "temperatureC",
                        "popPercent",
                        "precipitationAmount",
                        "condition",
                    )
                }
                for period in sorted(payload["periods"], key=lambda p: p["start"])[:16]
            ],
        }

    current = public_bulletin(revisions[0]["payload"])
    # Ignore duplicate deliveries and metadata-only revisions. Corrected bulletins
    # with the same issue time but changed weather remain valid previous versions.
    previous = next(
        (
            candidate
            for row in revisions[1:]
            if (candidate := public_bulletin(row["payload"])) != current
        ),
        None,
    )
    state = "ready" if previous else "building_history"
    if previous and any(current[key] != previous[key] for key in ("id", "latitude", "longitude")):
        state = "location_changed"
        previous = None
    assessment, facts = bulletin_significance(current, previous)
    return {
        "state": state,
        "current": current,
        "previous": previous,
        "assessment": assessment,
        "importantFacts": facts,
    }


def bulletin_significance(current: dict, previous: dict | None, now: datetime | None = None):
    """Conservative server-side relevance guard; the LLM still receives both bulletins.

    This only filters display comparisons of already-collected data. It neither
    collects data nor makes a new forecast. No wind/model-hourly noise is included.
    """
    if previous is None:
        return "incomplete", []
    now = now or datetime.now(UTC)
    facts = []
    comparable = 0

    def normalize(text):
        return re.sub(r"[\W_]+", " ", text.casefold()).strip()

    old_by_end = {(p["end"], p.get("temperatureClass")): p for p in previous["periods"]}
    for new in current["periods"]:
        old = old_by_end.get((new["end"], new.get("temperatureClass")))
        end = datetime.fromisoformat(new["end"].replace("Z", "+00:00"))
        if (
            not old
            or end <= now
            or any(
                datetime.fromisoformat(p["start"].replace("Z", "+00:00")) >= end for p in (old, new)
            )
        ):
            continue
        interval = f"{new['start']} to {new['end']} ({new.get('temperatureClass') or 'period'})"
        a, b = old.get("condition"), new.get("condition")
        if a and b:
            comparable += 1
            if normalize(a) != normalize(b):
                facts.append(f"Conditions {interval}: PREVIOUS {a}; CURRENT {b}.")
        for field, label, unit, threshold in [
            ("temperatureC", "Temperature", "°C", 3),
            ("popPercent", "Precipitation chance", "%", 30),
        ]:
            a, b = old.get(field), new.get(field)
            if a is None or b is None:
                continue
            comparable += 1
            if abs(a - b) >= threshold:
                facts.append(f"{label} {interval}: PREVIOUS {a:g}{unit}; CURRENT {b:g}{unit}.")
        # Only compare amounts for identical intervals and units. Preserve ranges;
        # use changes to their endpoints, never convert snow depth to liquid rain.
        if old["start"] != new["start"]:
            continue
        pattern = r"(\d+(?:\.\d+)?)(?:\s*(?:–|-|to)\s*(\d+(?:\.\d+)?))?\s*(mm|cm)"
        a = re.fullmatch(pattern, old.get("precipitationAmount") or "")
        b = re.fullmatch(pattern, new.get("precipitationAmount") or "")
        if a and b and a[3] == b[3]:
            comparable += 1
            before = (float(a[1]), float(a[2] or a[1]))
            after = (float(b[1]), float(b[2] or b[1]))
            threshold = 5 if a[3] == "mm" else 2
            if any(
                abs(x - y) >= threshold and abs(x - y) >= abs(x) * 0.25
                for x, y in zip(before, after, strict=True)
            ):
                facts.append(f"Precipitation amount {interval}: PREVIOUS {a[0]}; CURRENT {b[0]}.")
    return (
        "candidate_changes" if facts else "no_important_changes" if comparable else "incomplete"
    ), facts


@router.get("/api/v1/widgets/forecast", tags=["widgets"])
async def widget_forecast(request: Request, reader: Reader, area_id: Area):
    return await prepared(request, reader, area_id, "widget")


def station_parameters(now, **kwargs):
    return {
        "now": now,
        "id": None,
        "longitude": None,
        "latitude": None,
        "radius": 100,
        "west": None,
        "south": None,
        "east": None,
        "north": None,
        "field": "temperatureC",
        "limit": 201,
        "offset": 0,
        **kwargs,
    }


def station_item(row):
    return {
        **row["metadata"],
        "distanceKm": round(row["distance_km"], 1) if row["distance_km"] is not None else None,
        "stale": row["stale"],
        "observation": row["payload"],
    }


@router.get("/api/v1/observations/stations", tags=["observations"])
async def map_stations(
    reader: Reader,
    bbox: Annotated[str, Query(max_length=100)],
    field: Field = "temperatureC",
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0, le=1500),
):
    try:
        west, south, east, north = [float(v) for v in bbox.split(",")]
        if not (-180 <= west <= 180 and -180 <= east <= 180 and -90 <= south < north <= 90):
            raise ValueError
    except ValueError as error:
        raise HTTPException(422, "bbox requires west,south,east,north in degrees") from error
    now = datetime.now(UTC)
    rows = await reader.rows(
        "stations",
        station_parameters(
            now,
            west=west,
            east=east,
            south=south,
            north=north,
            field=field,
            limit=limit + 1,
            offset=offset,
        ),
    )
    return {
        "schemaVersion": 1,
        "generatedAt": now,
        "items": [station_item(r) for r in rows[:limit]],
        "nextOffset": offset + limit if len(rows) > limit else None,
    }


@router.get("/api/v1/observations/nearby", tags=["observations"])
async def nearby_stations(
    reader: Reader,
    longitude: float = Query(ge=-180, le=180),
    latitude: float = Query(ge=-90, le=90),
    radius: float = Query(100, ge=1, le=200),
    field: Field = "temperatureC",
):
    now = datetime.now(UTC)
    rows = await reader.rows(
        "stations",
        station_parameters(
            now, longitude=longitude, latitude=latitude, radius=radius, field=field, limit=5
        ),
    )
    return {
        "schemaVersion": 1,
        "generatedAt": now,
        "items": [station_item(r) for r in rows],
        "nextOffset": None,
    }


@router.get("/api/v1/observations/stations/{station_id}", tags=["observations"])
async def station_detail(station_id: str, reader: Reader):
    if not 1 <= len(station_id) <= 64:
        raise HTTPException(422, "Invalid station ID")
    rows = await reader.rows(
        "stations", station_parameters(datetime.now(UTC), id=station_id, limit=1)
    )
    if not rows:
        raise HTTPException(404, "Station has no collected observations")
    return station_item(rows[0])


@router.get("/api/v1/observations/stations/{station_id}/history", tags=["observations"])
async def station_history(
    station_id: str,
    reader: Reader,
    field: Field = "temperatureC",
    start: datetime | None = None,
    end: datetime | None = None,
):
    end = end or datetime.now(UTC)
    start = start or end - timedelta(hours=48)
    if not start.tzinfo or not end.tzinfo or not timedelta(0) < end - start <= timedelta(hours=48):
        raise HTTPException(422, "History requires an aware time interval of at most 48 hours")
    if not 1 <= len(station_id) <= 64:
        raise HTTPException(422, "Invalid station ID")
    rows = await reader.rows("station_history", {"id": station_id, "start": start, "end": end})
    return {
        "stationId": station_id,
        "field": field,
        "start": start,
        "end": end,
        "items": [
            {
                "time": row["observed_at"],
                "value": row["payload"]["values"].get(field),
                "quality": row["payload"]["quality"].get(field),
                "interval": row["payload"]["intervals"].get(field),
            }
            for row in rows
        ],
    }
