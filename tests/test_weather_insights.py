import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from weather_api import insights
from weather_ingest.forecast_insights import (
    compare_versions,
    digest,
    hour_rows,
    widget_payload,
)
from weather_ingest.weather_stations import parse_report

NOW = datetime(2026, 9, 8, 12, tzinfo=UTC)
REGION = {
    "id": "0123456789abcdef",
    "name": "Halifax Metro",
    "locality": "Halifax",
    "province": "NS",
    "longitude": -63.57,
    "latitude": 44.65,
    "issuedAt": "2026-09-08T10:00:00Z",
    "periods": [
        {
            "name": "Today",
            "start": "2026-09-08T09:00:00Z",
            "end": "2026-09-08T21:00:00Z",
            "temperatureClass": "high",
            "temperatureC": 20,
            "popPercent": 40,
            "precipitationAmount": "4 mm",
            "condition": "Rain",
        }
    ],
}


def test_changes_compare_intervals_not_relative_labels():
    new = deepcopy(REGION)
    new["periods"][0].update(
        name="Tuesday", temperatureC=23, popPercent=60, precipitationAmount="10 mm"
    )
    result = compare_versions(new, REGION, "bulletin", NOW)
    assert result["state"] == "changed"
    assert result["matchedPeriods"] == 1
    assert {h["field"] for h in result["highlights"]} == {
        "temperatureC",
        "popPercent",
        "precipitationMm",
    }


@pytest.mark.parametrize("amount", [None, "4–10 mm", "4 cm", "amount unavailable"])
def test_amounts_with_unknown_or_incomparable_units_do_not_generate_changes(amount):
    new = deepcopy(REGION)
    new["periods"][0]["precipitationAmount"] = amount
    assert compare_versions(new, REGION, "bulletin", NOW)["state"] == "unchanged"


def test_changes_missing_is_not_zero_and_location_revision_is_not_weather():
    new = deepcopy(REGION)
    new["periods"][0]["temperatureC"] = None
    assert compare_versions(new, REGION, "bulletin", NOW)["state"] == "unchanged"
    new["longitude"] = -64
    assert compare_versions(new, REGION, "bulletin", NOW)["state"] == "location_changed"
    assert compare_versions(new, None, "bulletin", NOW)["state"] == "building_history"


def test_no_overlap_is_incomplete_not_unchanged():
    new = deepcopy(REGION)
    new["periods"][0]["start"] = "2026-09-09T09:00:00Z"
    new["periods"][0]["end"] = "2026-09-09T21:00:00Z"
    assert compare_versions(new, REGION, "bulletin", NOW)["state"] == "incomplete"


def test_hourly_rolling_window_and_missing_companions():
    old = {**REGION, "hours": hour_rows({"2026-09-08T12:00:00Z": {"temperatureC": 20}}, [NOW], NOW)}
    new = deepcopy(old)
    new["hours"] += hour_rows({}, [NOW + timedelta(hours=1)], NOW)
    assert compare_versions(new, old, "gdps", NOW)["state"] == "unchanged"
    assert new["hours"][1]["precipitationMm"] is None


def test_widgets_never_invent_observed_or_hourly_temperature():
    result = widget_payload(REGION, None, NOW)
    assert result["name"] == "Halifax Metro"
    assert result["locality"] == "Halifax"
    assert result["entries"][0]["temperatureC"] is None
    assert result["entries"][0]["highC"] == 20
    assert result["entries"][0]["symbol"] == "cloud.rain.fill"
    assert result["issuedAt"] == REGION["issuedAt"]
    assert widget_payload(REGION, None, NOW + timedelta(days=2))["entries"] == []


def test_widget_timestamps_stay_fixed_during_polling_and_old_model_is_excluded():
    hourly = {"hours": hour_rows({"2026-09-08T12:00:00Z": {"temperatureC": 18}}, [NOW], NOW)}
    first = widget_payload(REGION, hourly, NOW)
    later = widget_payload(REGION, hourly, NOW + timedelta(minutes=10))
    assert first["entries"] == later["entries"]
    assert first["modelIssuedAt"] == "2026-09-08T12:00:00Z"
    hourly["hours"][0]["runTime"] = "2026-09-07T06:00:00Z"
    expired_model = widget_payload(REGION, hourly, NOW)
    assert expired_model["entries"][0]["temperatureC"] is None
    assert expired_model["modelIssuedAt"] is None


def test_prepared_hourly_uses_only_matching_current_coverage(monkeypatch):
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database=object())))
    payload = {**REGION, "start": "2026-09-08T12:00:00Z", "availableHours": 72}
    row = {"payload": payload, "valid_until": NOW + timedelta(hours=1)}
    reader = SimpleNamespace(rows=AsyncMock(return_value=[row]))
    monkeypatch.setattr(insights, "repository", lambda _: reader)
    assert asyncio.run(insights.prepared_hourly(request, REGION, NOW)) == payload
    for change in [{"latitude": 45}, {"availableHours": 59}, {"start": "2026-09-08T11:00:00Z"}]:
        reader.rows.return_value = [{**row, "payload": {**payload, **change}}]
        assert asyncio.run(insights.prepared_hourly(request, REGION, NOW)) is None
    reader.rows.return_value = [{**row, "valid_until": NOW}]
    assert asyncio.run(insights.prepared_hourly(request, REGION, NOW)) is None
    reader.rows.side_effect = HTTPException(503, "Optional migration not applied")
    assert asyncio.run(insights.prepared_hourly(request, REGION, NOW)) is None


def test_archive_retention_dry_run_has_strict_age_and_path_boundaries(tmp_path, monkeypatch):
    import os

    from weather_ingest import insight_retention

    root = tmp_path / "data"
    old = root / "raw/eccc/stations/CYHZ" / ("a" * 64 + ".xml")
    old.parent.mkdir(parents=True)
    old.write_text("old source report")
    os.utime(old, ((NOW - timedelta(days=8)).timestamp(),) * 2)
    recent = old.with_name("b" * 64 + ".xml")
    recent.write_text("recent source report")
    os.utime(recent, (NOW.timestamp(),) * 2)
    latest = old.with_name("latest.xml")
    latest.write_text("never a retention target")
    os.utime(latest, ((NOW - timedelta(days=90)).timestamp(),) * 2)
    external = tmp_path / ("c" * 64 + ".xml")
    external.write_text("outside the dedicated archive")
    os.utime(external, ((NOW - timedelta(days=90)).timestamp(),) * 2)
    old.with_name(external.name).symlink_to(external)
    monkeypatch.setattr(
        insight_retention.psycopg,
        "connect",
        lambda *a, **k: pytest.fail("Dry run must not mutate the database"),
    )
    result = insight_retention.maintain_insights(SimpleNamespace(data_root=root), now=NOW)
    assert result == {"dryRun": True, "archiveFiles": 1, "forecasts": 0, "observations": 0}
    assert all(path.exists() for path in [old, recent, latest, external])


def xml_report(*, temperature="13.1", qa="100", precip="0.0", flag="", unit="°C"):
    return f'''<ObservationCollection><Observation><identification-elements>
      <element name="stn_nam" value="Halifax"/><element name="icao_stn_id" value="CYHZ"/>
      <element name="date_tm" value="2026-09-08T12:00:00Z"/>
      <element name="lat" value="44.88"/><element name="long" value="-63.5"/>
      </identification-elements><elements>
      <element name="air_temp" uom="{unit}" value="{temperature}">
      <qualifier name="qa_summary" value="{qa}"/></element>
      <element name="pcpn_amt_pst1hr" uom="mm" value="{precip}">
      <qualifier name="data_flag" value="{flag}"/></element></elements></Observation>
      </ObservationCollection>'''.encode()


@pytest.mark.parametrize("qa", ["-10", "-1", "0", "10", "15", "20"])
def test_station_quality_rejects_suppressed_suspect_and_missing(qa):
    _, obs = parse_report(xml_report(qa=qa), "CYHZ-AUTO-swob.xml", NOW)
    assert obs["values"]["temperatureC"] is None
    assert obs["quality"]["temperatureC"]["state"] == "rejected"


@pytest.mark.parametrize("flag,state", [("5", "trace"), ("1,5", "trace"), ("4", "incomplete")])
def test_trace_and_incomplete_precipitation_are_not_zero(flag, state):
    _, obs = parse_report(xml_report(flag=flag), "CYHZ-AUTO-swob.xml", NOW)
    assert obs["values"]["precipitationMm"] is None
    assert obs["quality"]["precipitationMm"]["state"] == state


def test_station_zero_intervals_identity_and_correction():
    station, obs = parse_report(xml_report(), "2026-09-08-1200-CYHZ-AUTO-CorB-swob.xml", NOW)
    assert station["longitude"] == -63.5
    assert obs["values"]["precipitationMm"] == 0
    assert obs["intervals"]["precipitationMm"]["start"] == "2026-09-08T11:00:00Z"
    assert obs["correction"] == 2
    with pytest.raises(ValueError):
        parse_report(xml_report(), "CYQM-AUTO-swob.xml", NOW)


@pytest.mark.parametrize(
    "body",
    [
        xml_report(temperature="NaN"),
        xml_report(temperature="MSNG"),
        xml_report(unit="K"),
        xml_report(temperature="1000"),
    ],
)
def test_station_nonfinite_missing_wrong_units_and_invalid_values(body):
    _, obs = parse_report(body, "CYHZ-AUTO-swob.xml", NOW)
    assert obs["values"]["temperatureC"] is None


def test_station_rejects_entities_minute_reports_and_future_dates():
    for body, filename, now in [
        (b"<!DOCTYPE x []>" + xml_report(), "CYHZ-AUTO-swob.xml", NOW),
        (xml_report(), "CYHZ-AUTO-minute-swob.xml", NOW),
        (xml_report(), "CYHZ-AUTO-swob.xml", NOW - timedelta(hours=1)),
    ]:
        with pytest.raises(ValueError):
            parse_report(body, filename, now)


class Reader:
    def __init__(self):
        self.calls = []

    async def rows(self, name, params):
        self.calls.append((name, params))
        if name == "prepared":
            payload = {"schemaVersion": 1, "regionId": REGION["id"], "groups": []}
            return [
                {
                    "payload": payload,
                    "content_version": digest(payload),
                    "valid_until": datetime.now(UTC) + timedelta(hours=1),
                }
            ]
        return []


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(insights.router)
    reader = Reader()
    app.dependency_overrides[insights.repository] = lambda: reader
    return TestClient(app), reader


def test_prepared_reads_have_validators_and_no_collection(client):
    client, reader = client
    result = client.get("/api/v1/forecast/changes", params={"area_id": REGION["id"]})
    assert result.status_code == 200 and not result.json()["stale"]
    assert (
        client.get(
            "/api/v1/forecast/changes",
            params={"area_id": REGION["id"]},
            headers={"if-none-match": result.headers["etag"]},
        ).status_code
        == 304
    )
    assert all(name == "prepared" for name, _ in reader.calls)


def test_bulletin_pair_preserves_full_conditions_amounts_and_missing_values():
    previous = deepcopy(REGION)
    previous["issuedAt"] = "2026-09-08T04:00:00Z"
    previous["periods"][0].update(condition="Sunny", popPercent=None, precipitationAmount=None)
    current = deepcopy(REGION)
    current["periods"][0]["precipitationAmount"] = "10 to 20 mm"
    result = insights.bulletin_pair([{"payload": current}, {"payload": previous}])
    assert result["state"] == "ready"
    assert result["current"]["periods"][0]["precipitationAmount"] == "10 to 20 mm"
    assert result["previous"]["periods"][0]["popPercent"] is None
    assert result["previous"]["periods"][0]["condition"] == "Sunny"
    assert "highlights" not in result
    assert current == {**REGION, "periods": current["periods"]}


def test_bulletin_pair_handles_missing_history_metadata_and_coordinate_changes():
    assert insights.bulletin_pair([])["state"] == "building_history"
    metadata = {**REGION, "locality": "A different display name"}
    assert insights.bulletin_pair([{"payload": REGION}, {"payload": metadata}])["previous"] is None
    corrected = deepcopy(REGION)
    corrected["periods"][0]["condition"] = "Snow"
    pair = insights.bulletin_pair([{"payload": corrected}, {"payload": REGION}])
    assert pair["state"] == "ready"  # Same issue-time corrections are real revisions.
    moved = {**REGION, "longitude": -64}
    pair = insights.bulletin_pair([{"payload": moved}, {"payload": REGION}])
    assert pair["state"] == "location_changed" and pair["previous"] is None


@pytest.mark.parametrize(
    "fields",
    [
        {"temperatureC": 22, "popPercent": 60},
        {"condition": "rain.", "precipitationAmount": "5 mm"},
        {"name": "Tuesday", "start": "2026-09-08T12:00:00Z"},
        {"popPercent": None, "precipitationAmount": None},
        {"windKmh": 99, "gustKmh": 100},  # Not daily/nightly bulletin fields.
    ],
)
def test_bulletin_relevance_suppresses_minor_missing_and_rolling_changes(fields):
    current = deepcopy(REGION)
    current["periods"][0].update(fields)
    assert insights.bulletin_significance(current, REGION, NOW) == ("no_important_changes", [])


@pytest.mark.parametrize(
    "fields,label",
    [
        ({"temperatureC": 16}, "Temperature"),
        ({"popPercent": 80}, "Precipitation chance"),
        ({"condition": "Snow at times heavy"}, "Conditions"),
        ({"precipitationAmount": "10 to 20 mm"}, "Precipitation amount"),
    ],
)
def test_bulletin_relevance_preserves_only_supported_important_facts(fields, label):
    current = deepcopy(REGION)
    current["periods"][0].update(fields)
    state, facts = insights.bulletin_significance(current, REGION, NOW)
    assert state == "candidate_changes" and len(facts) == 1
    assert facts[0].startswith(label) and "PREVIOUS" in facts[0] and "CURRENT" in facts[0]


def test_bulletin_relevance_never_invents_comparisons_across_missing_or_mismatched_periods():
    current = deepcopy(REGION)
    current["periods"][0].update(temperatureClass="low", condition="Snow")
    assert insights.bulletin_significance(current, REGION, NOW) == ("incomplete", [])
    assert insights.bulletin_significance(REGION, None, NOW) == ("incomplete", [])
    assert insights.bulletin_significance(REGION, REGION, NOW + timedelta(days=1)) == (
        "incomplete",
        [],
    )
    current["periods"][0].update(temperatureClass="high", start="2026-09-08T22:00:00Z")
    assert insights.bulletin_significance(current, REGION, NOW) == ("incomplete", [])
    current["periods"][0].update(
        start="2026-09-08T12:00:00Z", condition="Rain", precipitationAmount="40 mm"
    )
    assert insights.bulletin_significance(current, REGION, NOW) == ("no_important_changes", [])
    missing = deepcopy(REGION)
    missing["periods"][0].update(
        condition=None, temperatureC=None, popPercent=None, precipitationAmount=None
    )
    assert insights.bulletin_significance(REGION, missing, NOW) == ("incomplete", [])


def test_paired_forecast_api_is_opt_in_read_only_and_has_independent_validator(client):
    client, reader = client
    original = reader.rows
    current = deepcopy(REGION)
    previous = {**REGION, "issuedAt": "2026-09-08T04:00:00Z"}

    async def rows(name, params):
        if name == "revisions":
            reader.calls.append((name, params))
            assert params == {"area_id": REGION["id"], "source": "bulletin"}
            return [{"payload": current}, {"payload": previous}]
        return await original(name, params)

    reader.rows = rows
    params = {"area_id": REGION["id"], "include_forecasts": "true"}
    first = client.get("/api/v1/forecast/changes", params=params)
    assert first.status_code == 200 and first.json()["bulletins"]["state"] == "ready"
    assert (
        client.get(
            "/api/v1/forecast/changes",
            params=params,
            headers={"if-none-match": first.headers["etag"]},
        ).status_code
        == 304
    )
    current["periods"][0]["condition"] = "Snow"
    updated = client.get(
        "/api/v1/forecast/changes", params=params, headers={"if-none-match": first.headers["etag"]}
    )
    assert updated.status_code == 200 and updated.headers["etag"] != first.headers["etag"]
    legacy = client.get("/api/v1/forecast/changes", params={"area_id": REGION["id"]})
    assert "bulletins" not in legacy.json()
    assert {name for name, _ in reader.calls} == {"prepared", "revisions"}


def test_station_api_bounds_and_antimeridian(client):
    client, reader = client
    assert client.get("/api/v1/observations/stations?bbox=170,-10,-170,10").status_code == 200
    assert reader.calls[-1][1]["west"] == 170
    for query in [
        "bbox=nan,-10,10,10",
        "bbox=1,2,3",
        "bbox=-181,0,180,10",
        "bbox=-180,-90,180,90&limit=1000",
    ]:
        assert client.get("/api/v1/observations/stations?" + query).status_code == 422
    assert (
        client.get("/api/v1/observations/nearby?latitude=44&longitude=-63&radius=1000").status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/observations/stations/CYHZ/history?start=2026-09-01T00:00:00Z&end=2026-09-08T00:00:00Z"
        ).status_code
        == 422
    )
