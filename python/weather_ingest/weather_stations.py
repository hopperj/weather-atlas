"""Bounded SWOB-ML land-station ETL. Source QC and measurement intervals survive normalization."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import math
import os
import re
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from weather_common.db import SqlFileLoader
from weather_common.settings import Settings

from weather_ingest.eccc_city_forecasts import _atomic_bytes, _atomic_json, _ListingParser
from weather_ingest.forecast_insights import InsightWriter, digest, stamp, utc
from weather_ingest.storage import resolve_under

BASE = "https://dd.weather.gc.ca/today/observations/"
LOG = logging.getLogger(__name__)
REPORT = re.compile(
    r"(?:latest_)?(?:\d{4}-\d\d-\d\d-\d{4}-)?"
    r"(?P<id>[A-Z0-9]{3,8})[-_](?P<type>AUTO|MAN|MANNED)"
    r"(?:-Cor(?P<correction>[A-Z]))?[-_]swob\.xml$"
)
MEASUREMENTS = {
    "temperatureC": (["air_temp"], "°C", -100, 65, 0),
    "humidityPercent": (["rel_hum"], "%", 0, 100, 0),
    "windKmh": (["avg_wnd_spd_10m_pst10mts", "avg_wnd_spd_10m_pst2mts"], "km/h", 0, 500, 10),
    "gustKmh": (["max_wnd_gst_spd_10m_pst10mts"], "km/h", 0, 600, 10),
    "precipitationMm": (["pcpn_amt_pst1hr"], "mm", 0, 1000, 60),
    "pressureHpa": (["mslp"], "hPa", 800, 1100, 0),
}


def parse_report(body: bytes, filename: str, now: datetime) -> tuple[dict, dict]:
    match = REPORT.fullmatch(filename)
    if (
        not match
        or len(body) > 262144
        or b"<!DOCTYPE" in body.upper()
        or b"<!ENTITY" in body.upper()
    ):
        raise ValueError("Unsupported or unsafe land-station report")
    root = ET.fromstring(body)
    elements = {}
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == "element":
            elements.setdefault(element.get("name"), []).append(element)

    def text(name, default=""):
        found = elements.get(name, [])
        return found[0].get("value", default) if found else default

    observed = stamp(text("date_tm"))
    if observed > now + timedelta(minutes=5) or observed < now - timedelta(days=30):
        raise ValueError("Observation timestamp outside admission window")
    lon, lat = float(text("long")), float(text("lat"))
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError("Invalid station coordinates")
    identity = text("icao_stn_id") or text("tc_id")
    if identity and identity != match["id"] and "C" + identity != match["id"]:
        raise ValueError("Station identity mismatch")
    metadata = {
        "id": match["id"],
        "name": text("stn_nam", match["id"]),
        "longitude": lon,
        "latitude": lat,
        "elevationM": None,
        "source": text("data_pvdr", "ECCC MSC"),
        "attribution": text("data_attrib_not", "Environment and Climate Change Canada"),
        "mscId": text("msc_id"),
    }
    try:
        elevation = float(text("stn_elev"))
        if math.isfinite(elevation):
            metadata["elevationM"] = elevation
    except ValueError:
        pass
    values, quality, intervals = {}, {}, {}
    for field, (names, unit, lower, upper, minutes) in MEASUREMENTS.items():
        candidates = [e for name in names for e in elements.get(name, [])]
        values[field] = None
        quality[field] = {"state": "missing", "sourceField": names[0], "unit": unit}
        for element in candidates:
            flags = {e.get("name"): e.get("value") for e in element}
            qa = flags.get("qa_summary")
            data_flags = set((flags.get("data_flag") or "").split(","))
            state = (
                "rejected"
                if qa not in (None, "100")
                else "incomplete"
                if "4" in data_flags
                else "trace"
                if "5" in data_flags
                else "accepted"
                if qa == "100"
                else "unchecked"
            )
            quality[field] = {
                "state": state,
                "qa": qa,
                "dataFlags": sorted(data_flags - {""}),
                "sourceField": element.get("name"),
                "unit": element.get("uom"),
            }
            if state in ("rejected", "incomplete", "trace"):
                continue
            try:
                number = float(element.get("value", ""))
            except ValueError:
                quality[field]["state"] = "missing"
                continue
            if (
                element.get("uom") != unit
                or not math.isfinite(number)
                or not lower <= number <= upper
            ):
                quality[field]["state"] = "unsupported"
                continue
            values[field] = number
            period = 2 if element.get("name", "").endswith("pst2mts") else minutes
            intervals[field] = {
                "start": utc(observed - timedelta(minutes=period)),
                "end": utc(observed),
            }
            break
    # Only hourly AUTO/MANNED streams are admitted; minute reports are excluded.
    observation = {
        "observedAt": utc(observed),
        "expiresAt": utc(observed + timedelta(minutes=135)),
        "expectedIntervalMinutes": 60,
        "values": values,
        "quality": quality,
        "intervals": intervals,
        "reportType": match["type"],
        "correction": ord(match["correction"]) - 64 if match["correction"] else 0,
        "version": hashlib.sha256(body).hexdigest(),
    }
    # A correction in the metadata URI survives a static latest filename.
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == "id":
            href = next(iter(element.attrib.values()), "")
            correction = re.search(r"/cor([a-z])/", href, re.I)
            if correction:
                observation["correction"] = ord(correction[1].upper()) - 64
            cadence = re.search(r"/(?:data|supp)_(\d+)$", href)
            if cadence and 1 <= int(cadence[1]) <= 1440:
                minutes = int(cadence[1])
                observation["expectedIntervalMinutes"] = minutes
                observation["expiresAt"] = utc(observed + timedelta(minutes=2 * minutes + 15))
    return metadata, observation


def bounded_get(client: httpx.Client, url: str, maximum: int) -> bytes:
    allowed = url.startswith(BASE) or re.match(
        r"^https://dd\.weather\.gc\.ca/\d{8}/WXO-DD/observations/", url
    )
    if not allowed or ".." in url:
        raise ValueError("Untrusted observation URL")
    with client.stream("GET", url) as response:
        response.raise_for_status()
        body = bytearray()
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) > maximum:
                raise ValueError("Observation download exceeds configured bound")
        return bytes(body)


def collect_stations(settings: Settings, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    config_root = Path(os.getenv("WEATHER_CONFIG_ROOT", "config"))
    config = json.loads((config_root / "stations.json").read_bytes())
    ids = set(config["station_ids"])
    if not 1 <= len(ids) <= min(128, config["maximum_stations"]):
        raise ValueError("Invalid station collection bound")
    if any(not re.fullmatch(r"[A-Z0-9]{3,8}", code) for code in ids):
        raise ValueError("Invalid station identifier")
    if shutil.disk_usage(settings.data_root).free < config["minimum_free_bytes"]:
        raise OSError("Station collection paused: insufficient free storage")
    accepted, rejected = 0, 0
    with (
        psycopg.connect(settings.database_url, row_factory=dict_row) as connection,
        httpx.Client(
            timeout=httpx.Timeout(20, connect=10),
            follow_redirects=False,
            headers={"User-Agent": "WeatherAtlas-stations/1.0"},
        ) as client,
    ):
        writer = InsightWriter(connection, SqlFileLoader(settings.sql_root))

        def accept(body, filename):
            nonlocal accepted, rejected
            try:
                metadata, observation = parse_report(body, filename, now)
                if metadata["id"] not in ids:
                    return
                relative = Path(
                    "raw/eccc/stations", metadata["id"], observation["version"] + ".xml"
                )
                archive = resolve_under(settings.data_root, relative)
                if not archive.exists():
                    _atomic_bytes(archive, body)
                observation["rawPath"] = relative.as_posix()
                with connection.transaction():
                    writer.query(
                        "upsert_station",
                        {
                            **metadata,
                            "metadata": Jsonb(metadata),
                            "observed_at": observation["observedAt"],
                        },
                    )
                    writer.query(
                        "station_revision",
                        {
                            "id": metadata["id"],
                            "version": digest(metadata),
                            "metadata": Jsonb(metadata),
                        },
                    )
                    writer.query(
                        "insert_observation",
                        {
                            "id": metadata["id"],
                            "observed_at": observation["observedAt"],
                            "report_type": observation["reportType"],
                            "correction": observation["correction"],
                            "version": observation["version"],
                            "payload": Jsonb(observation),
                        },
                    )
                accepted += 1
            except (ValueError, ET.ParseError):
                rejected += 1
                LOG.warning("station_report_rejected", extra={"filename": filename})

        # The daily catalogue is cached independently of the five-minute report cycle.
        catalogue_path = settings.data_root / "processed/eccc/stations/catalogue.json"
        if not catalogue_path.exists() or now.timestamp() - catalogue_path.stat().st_mtime > 86400:
            body = bounded_get(client, BASE + "doc/swob-xml_station_list.csv", 2 * 1024**2)
            catalogue = list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))
            _atomic_json(catalogue_path, {"generatedAt": utc(now), "stations": catalogue})

        inbox = settings.data_root / "amqp/inbox"
        paths = []
        # Scan only the recovery window, not an ever-growing inbox of old reports.
        recovery_dates = {now.date(), (now - timedelta(hours=config["history_hours"])).date()}
        for date in recovery_dates:
            for pattern in (
                f"{date:%Y%m%d}/WXO-DD/observations/swob-ml/{date:%Y%m%d}/*/*.xml",
                f"observations/swob-ml/{date:%Y%m%d}/*/*.xml",
                f"today/observations/swob-ml/{date:%Y%m%d}/*/*.xml",
            ):
                paths.extend(inbox.glob(pattern))
        for path in sorted(set(paths), key=lambda p: p.name, reverse=True)[
            : config["maximum_inbox_reports"]
        ]:
            if (
                path.is_file()
                and not path.is_symlink()
                and path.stat().st_size <= config["maximum_report_bytes"]
            ):
                accept(path.read_bytes(), path.name)

        listing = _ListingParser()
        listing.feed(bounded_get(client, BASE + "swob-ml/latest/", 2 * 1024**2).decode())
        for filename in listing.hrefs:
            match = REPORT.fullmatch(filename)
            if not match or match["id"] not in ids:
                continue
            try:
                body = bounded_get(
                    client, BASE + "swob-ml/latest/" + filename, config["maximum_report_bytes"]
                )
                accept(body, filename)
            except (httpx.HTTPError, ValueError):
                rejected += 1
                LOG.warning("station_latest_unavailable", extra={"filename": filename})
        # Recovery is bounded by station count, two date directories and six recent reports.
        for station in sorted(ids):
            for date in sorted(recovery_dates):
                day_base = (
                    BASE
                    if date == now.date()
                    else (f"https://dd.weather.gc.ca/{date:%Y%m%d}/WXO-DD/observations/")
                )
                prefix = day_base + f"swob-ml/{date:%Y%m%d}/{station}/"
                try:
                    listing = _ListingParser()
                    listing.feed(bounded_get(client, prefix, 2 * 1024**2).decode())
                    names = [n for n in listing.hrefs if REPORT.fullmatch(n)]
                    for name in sorted(names, reverse=True)[: min(config["history_hours"], 6)]:
                        accept(
                            bounded_get(client, prefix + name, config["maximum_report_bytes"]), name
                        )
                except (httpx.HTTPError, ValueError):
                    LOG.warning("station_recovery_unavailable", extra={"station": station})
        connection.commit()
    summary = {
        "generatedAt": utc(now),
        "accepted": accepted,
        "rejected": rejected,
        "configuredStations": len(ids),
    }
    _atomic_json(settings.data_root / "processed/eccc/stations/status.json", summary)
    if accepted == 0:
        raise ValueError("No station reports accepted; previous observations remain available")
    return summary


if __name__ == "__main__":
    print(json.dumps(collect_stations(Settings.from_environment())))
