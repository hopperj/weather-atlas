"""ECCC City Page Weather XML ingestion and regional forecast normalization."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
from collections import defaultdict
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

import httpx

from weather_ingest.storage import resolve_under

ECCC_CITYPAGE_HOST = "dd.weather.gc.ca"
ECCC_CITYPAGE_BASE_URL = f"https://{ECCC_CITYPAGE_HOST}"
ECCC_CITYPAGE_LICENSE_URL = f"{ECCC_CITYPAGE_BASE_URL}/doc/LICENCE_GENERAL.txt"
ECCC_CITYPAGE_ATTRIBUTION = (
    "Environment and Climate Change Canada, Meteorological Service of Canada"
)
PROVINCES = (
    "AB",
    "BC",
    "MB",
    "NB",
    "NL",
    "NS",
    "NT",
    "NU",
    "ON",
    "PE",
    "QC",
    "SK",
    "YT",
)
SOURCE_FILENAME = re.compile(
    r"^(?P<timestamp>\d{8}T\d{6}(?:\.\d+)?Z)"
    r"_MSC_CitypageWeather_(?P<site>s\d{7})_en\.xml$"
)
AMOUNT_RANGE = re.compile(
    r"\bamount(?:s)?(?:\s+of)?\s+"
    r"(?P<low>\d+(?:\.\d+)?)\s*(?:to|-)\s*"
    r"(?P<high>\d+(?:\.\d+)?)\s*(?P<unit>mm|cm)\b",
    re.IGNORECASE,
)
AMOUNT_SINGLE = re.compile(
    r"\bamount(?:s)?(?:\s+of)?\s+"
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mm|cm)\b",
    re.IGNORECASE,
)


class CityForecastUnavailable(ValueError):
    """The provider published a site document with no forecast bulletin."""


class _ListingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.hrefs.append(href)


def _positive_integer(
    values: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int = 1,
) -> int:
    raw = values.get(name, str(default)).strip()
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return parsed


@dataclass(frozen=True, slots=True)
class CityForecastSettings:
    """Bounded settings for the frequently amended ECCC city forecast feed."""

    provinces: tuple[str, ...] = PROVINCES
    listing_lookback_hours: int = 3
    maximum_sites: int = 1_200
    maximum_download_bytes: int = 256 * 1024
    minimum_free_bytes: int = 1024**3
    timeout_seconds: int = 60
    parallel_downloads: int = 12

    def __post_init__(self) -> None:
        invalid = set(self.provinces) - set(PROVINCES)
        if invalid:
            raise ValueError(f"unsupported province code(s): {sorted(invalid)}")
        if not self.provinces:
            raise ValueError("at least one province must be configured")
        if self.listing_lookback_hours < 1:
            raise ValueError("listing lookback must be positive")
        if self.maximum_sites < 1 or self.maximum_download_bytes < 1:
            raise ValueError("city forecast download bounds must be positive")
        if self.minimum_free_bytes < 0:
            raise ValueError("minimum free space must not be negative")
        if self.timeout_seconds < 1:
            raise ValueError("city forecast timeout must be positive")
        if not 1 <= self.parallel_downloads <= 32:
            raise ValueError("parallel downloads must be between 1 and 32")

    @classmethod
    def from_environment(
        cls,
        values: Mapping[str, str] | None = None,
    ) -> CityForecastSettings:
        environment = os.environ if values is None else values
        raw_provinces = environment.get(
            "ECCC_CITY_FORECAST_PROVINCES",
            ",".join(PROVINCES),
        )
        provinces = tuple(
            dict.fromkeys(
                value.strip().upper() for value in raw_provinces.split(",") if value.strip()
            )
        )
        return cls(
            provinces=provinces,
            listing_lookback_hours=_positive_integer(
                environment,
                "ECCC_CITY_FORECAST_LOOKBACK_HOURS",
                3,
            ),
            maximum_sites=_positive_integer(
                environment,
                "ECCC_CITY_FORECAST_MAXIMUM_SITES",
                1_200,
            ),
            maximum_download_bytes=_positive_integer(
                environment,
                "ECCC_CITY_FORECAST_MAXIMUM_DOWNLOAD_BYTES",
                256 * 1024,
            ),
            minimum_free_bytes=_positive_integer(
                environment,
                "ECCC_CITY_FORECAST_MINIMUM_FREE_BYTES",
                1024**3,
                minimum=0,
            ),
            timeout_seconds=_positive_integer(
                environment,
                "ECCC_CITY_FORECAST_TIMEOUT_SECONDS",
                60,
            ),
            parallel_downloads=_positive_integer(
                environment,
                "ECCC_CITY_FORECAST_PARALLEL_DOWNLOADS",
                12,
            ),
        )


@dataclass(frozen=True, slots=True)
class CityForecastSource:
    province: str
    site_code: str
    filename: str
    url: str


def citypage_hour_url(hour: datetime, *, current_date: datetime) -> str:
    """Return the live or dated Datamart directory for one issue hour."""

    aware_hour = hour.astimezone(UTC)
    today = current_date.astimezone(UTC).date()
    prefix = "today" if aware_hour.date() == today else f"{aware_hour:%Y%m%d}/WXO-DD"
    return f"{ECCC_CITYPAGE_BASE_URL}/{prefix}/citypage_weather/{{province}}/{aware_hour:%H}/"


def parse_citypage_listing(
    html: str,
    *,
    province: str,
    listing_url: str,
) -> tuple[CityForecastSource, ...]:
    """Select the newest English issue for every site in a directory."""

    parser = _ListingParser()
    parser.feed(html)
    newest: dict[str, CityForecastSource] = {}
    for href in parser.hrefs:
        filename = Path(urlsplit(href).path).name
        match = SOURCE_FILENAME.fullmatch(filename)
        if not match:
            continue
        site_code = match.group("site")
        source = CityForecastSource(
            province=province,
            site_code=site_code,
            filename=filename,
            url=urljoin(listing_url, href),
        )
        current = newest.get(site_code)
        if current is None or source.filename > current.filename:
            newest[site_code] = source
    return tuple(sorted(newest.values(), key=lambda item: item.site_code))


def discover_latest_sources(
    client: httpx.Client,
    settings: CityForecastSettings,
    *,
    now: datetime,
) -> tuple[CityForecastSource, ...]:
    if now.tzinfo is None:
        raise ValueError("city forecast discovery time must be timezone-aware")
    now_utc = now.astimezone(UTC)
    newest: dict[str, CityForecastSource] = {}
    for offset in reversed(range(settings.listing_lookback_hours)):
        issue_hour = now_utc.replace(minute=0, second=0, microsecond=0) - timedelta(hours=offset)
        template = citypage_hour_url(issue_hour, current_date=now_utc)
        for province in settings.provinces:
            listing_url = template.format(province=province)
            response = client.get(listing_url)
            if response.status_code == 404:
                continue
            response.raise_for_status()
            for source in parse_citypage_listing(
                response.text,
                province=province,
                listing_url=listing_url,
            ):
                current = newest.get(source.site_code)
                if current is None or source.filename > current.filename:
                    newest[source.site_code] = source
    if len(newest) > settings.maximum_sites:
        raise ValueError(
            f"provider exposed {len(newest)} sites, above the configured "
            f"limit of {settings.maximum_sites}"
        )
    return tuple(sorted(newest.values(), key=lambda item: item.site_code))


def citypage_archive() -> Path:
    return Path("processed", "eccc", "citypage_weather")


def citypage_latest_relative_path() -> Path:
    return citypage_archive() / "latest.json"


def citypage_manifest_relative_path() -> Path:
    return citypage_archive() / "manifest.json"


def citypage_raw_relative_path(source: CityForecastSource) -> Path:
    return Path(
        "raw",
        "eccc",
        "citypage_weather",
        "latest",
        source.province,
        f"{source.site_code}.xml",
    )


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.unlink(missing_ok=True)
    try:
        with temporary.open("xb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_json(path: Path, payload: object) -> None:
    encoded = (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode()
    _atomic_bytes(path, encoded)


def _read_manifest(data_root: Path) -> dict[str, object]:
    path = resolve_under(data_root, citypage_manifest_relative_path())
    if not path.is_file() or path.is_symlink():
        return {}
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or payload.get("product") != "citypage_weather"
    ):
        return {}
    return payload


def _number(element: ElementTree.Element | None) -> float | None:
    if element is None or element.text is None or not element.text.strip():
        return None
    try:
        return float(element.text.strip())
    except ValueError:
        return None


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=UTC)


def _coordinate(value: str, *, latitude: bool) -> float:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([NSEW])\s*", value)
    if not match:
        raise ValueError(f"invalid city forecast coordinate: {value!r}")
    coordinate = float(match.group(1))
    direction = match.group(2)
    if (latitude and direction not in {"N", "S"}) or (not latitude and direction not in {"E", "W"}):
        raise ValueError(f"coordinate direction does not match axis: {value!r}")
    if direction in {"S", "W"}:
        coordinate *= -1
    limit = 90 if latitude else 180
    if not -limit <= coordinate <= limit:
        raise ValueError(f"coordinate is outside the valid range: {value!r}")
    return coordinate


def _period_boundaries(
    issue_time: datetime,
    utc_offset_hours: float,
    period_names: Iterable[str],
) -> tuple[tuple[datetime, datetime], ...]:
    names = tuple(period_names)
    if not names:
        return ()
    offset = timezone(timedelta(hours=utc_offset_hours))
    local_issue = issue_time.astimezone(offset)
    first_name = names[0].casefold()
    boundary_hour = 6 if "night" in first_name or "tonight" in first_name else 18
    first_end = local_issue.replace(
        hour=boundary_hour,
        minute=0,
        second=0,
        microsecond=0,
    )
    if first_end <= local_issue:
        first_end += timedelta(days=1)
    boundaries: list[tuple[datetime, datetime]] = [(issue_time, first_end.astimezone(UTC))]
    for _name in names[1:]:
        start = boundaries[-1][1]
        boundaries.append((start, start + timedelta(hours=12)))
    return tuple(boundaries)


def precipitation_amount(
    summary: str,
    *,
    probability: float | None,
) -> str | None:
    """Extract only explicitly issued precipitation totals."""

    range_match = AMOUNT_RANGE.search(summary)
    if range_match:
        return (
            f"{range_match.group('low')}–{range_match.group('high')} "
            f"{range_match.group('unit').lower()}"
        )
    single_match = AMOUNT_SINGLE.search(summary)
    if single_match:
        return f"{single_match.group('value')} {single_match.group('unit').lower()}"
    if probability == 0:
        return "0 mm"
    return None


def parse_citypage_xml(payload: bytes) -> dict[str, object]:
    """Normalize one official city forecast document."""

    if len(payload) < 100:
        raise ValueError("city forecast XML is unexpectedly small")
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise ValueError("city forecast XML is malformed") from exc
    if root.tag != "siteData":
        raise ValueError("city forecast XML has an unexpected root element")

    location = root.find("location")
    name = location.find("name") if location is not None else None
    province = location.find("province") if location is not None else None
    if (
        location is None
        or name is None
        or name.text is None
        or province is None
        or name.get("code") is None
        or name.get("lat") is None
        or name.get("lon") is None
    ):
        raise ValueError("city forecast XML is missing location metadata")
    site_code = str(name.get("code"))
    if not re.fullmatch(r"s\d{7}", site_code):
        raise ValueError("city forecast site code is invalid")

    forecast_group = root.find("forecastGroup")
    if forecast_group is None:
        raise ValueError("city forecast XML has no forecast group")
    issue_utc_element = forecast_group.find("dateTime[@zone='UTC']/timeStamp")
    if issue_utc_element is None or issue_utc_element.text is None:
        raise CityForecastUnavailable("city forecast XML has no UTC issue time")
    issue_time = _timestamp(issue_utc_element.text.strip())
    local_issue_element = next(
        (item for item in forecast_group.findall("dateTime") if item.get("zone") != "UTC"),
        None,
    )
    try:
        utc_offset = float(
            local_issue_element.get("UTCOffset", "0") if local_issue_element is not None else "0"
        )
    except ValueError as exc:
        raise ValueError("city forecast UTC offset is invalid") from exc

    forecasts = forecast_group.findall("forecast")
    if not forecasts:
        raise CityForecastUnavailable("city forecast XML has no forecast periods")
    period_names = [(forecast.findtext("period") or "").strip() for forecast in forecasts]
    boundaries = _period_boundaries(issue_time, utc_offset, period_names)
    periods: list[dict[str, object]] = []
    for forecast, period_name, (valid_start, valid_end) in zip(
        forecasts,
        period_names,
        boundaries,
        strict=True,
    ):
        temperature = _number(forecast.find("temperatures/temperature"))
        humidity = _number(forecast.find("relativeHumidity"))
        probability = _number(forecast.find("abbreviatedForecast/pop"))
        condition = (forecast.findtext("abbreviatedForecast/textSummary") or "").strip()
        summary = " ".join(
            value.strip()
            for value in (
                forecast.findtext("precipitation/textSummary") or "",
                forecast.findtext("textSummary") or "",
            )
            if value.strip()
        )
        periods.append(
            {
                "period": period_name,
                "valid_start": _utc_text(valid_start),
                "valid_end": _utc_text(valid_end),
                "temperature_c": temperature,
                "temperature_class": (
                    forecast.find("temperatures/temperature").get("class")
                    if forecast.find("temperatures/temperature") is not None
                    else None
                ),
                "relative_humidity_percent": humidity,
                "pop_percent": probability,
                "precipitation_amount": precipitation_amount(
                    summary,
                    probability=probability,
                ),
                "condition": condition,
            }
        )

    region = (location.findtext("region") or "").strip()
    return {
        "site_code": site_code,
        "site_name": name.text.strip(),
        "province": str(province.get("code", "")).upper(),
        "region": region or name.text.strip(),
        "longitude": _coordinate(str(name.get("lon")), latitude=False),
        "latitude": _coordinate(str(name.get("lat")), latitude=True),
        "issued_at": _utc_text(issue_time),
        "periods": periods,
    }


def forecast_briefing(periods: list[dict], now: datetime) -> dict | None:
    """Prepare bounded, source-only weekly facts in ETL, never on a phone/API read."""
    active = [
        p
        for p in periods
        if datetime.fromisoformat(str(p["valid_end"]).replace("Z", "+00:00")) > now
        and datetime.fromisoformat(str(p["valid_start"]).replace("Z", "+00:00"))
        < now + timedelta(days=7)
    ][:14]
    if not active:
        return None
    conditions = [str(p.get("condition", "")).lower() for p in active]
    sun = any(re.search(r"sun|clear", c) for c in conditions)
    cloud = any("cloud" in c for c in conditions)
    if sun and cloud:
        overview = "Expect a mix of sunshine and cloud over the coming days."
    elif sun:
        overview = "Clearer periods feature in the outlook for the coming days."
    elif cloud:
        overview = "Cloudy periods feature in the outlook for the coming days."
    else:
        first = str(active[0].get("condition", "")).strip().rstrip(".")
        overview = f"The outlook starts with {first[:90].lower() or 'limited condition details'}."
    wet: dict[str, bool] = {}
    wet_types = []
    for p, condition in zip(active, conditions, strict=True):
        probability = p.get("pop_percent")
        if re.search(
            r"rain|showers|snow|flurries|drizzle|thunder|ice pellets|hail|blizzard", condition
        ) or (isinstance(probability, (int, float)) and probability > 0):
            # Keep the provider's day label; collapse day/night only for prose timing.
            day = re.sub(r"\s+(night|evening)$", "", str(p["period"]), flags=re.IGNORECASE)
            uncertain = bool(re.search(r"chance|risk|possible", condition)) or not re.search(
                r"rain|showers|snow|flurries|drizzle|thunder|ice pellets|hail|blizzard", condition
            )
            wet[day] = wet.get(day, False) or not uncertain
            wet_types.append(condition)

    def joined(items: list[str]) -> str:
        return (
            " and ".join(items) if len(items) < 3 else ", ".join(items[:-1]) + " and " + items[-1]
        )

    possible = [day for day, expected in wet.items() if not expected]
    expected = [day for day, expected in wet.items() if expected]
    # A broad term avoids relabeling mixed/frozen precipitation as ordinary rain.
    kind = (
        "Showers"
        if wet_types
        and all("showers" in c and not re.search(r"snow|freezing", c) for c in wet_types)
        else "Precipitation"
    )
    if possible and expected:
        precipitation = f"{kind} are possible {joined(possible)}, and expected {joined(expected)}."
    elif possible:
        precipitation = f"{kind} are possible {joined(possible)}."
    elif expected:
        precipitation = f"{kind} are expected {joined(expected)}."
    else:
        precipitation = "No wet weather is mentioned in the available forecast."
    if kind == "Precipitation":
        precipitation = precipitation.replace("Precipitation are", "Precipitation is")

    def values(kind: str) -> list[float]:
        return [
            float(p["temperature_c"])
            for p in active
            if p.get("temperature_class") == kind
            and isinstance(p.get("temperature_c"), (int, float))
            and math.isfinite(p["temperature_c"])
        ]

    def span(numbers: list[float]) -> str:
        low, high = min(numbers), max(numbers)
        return f"{low:g}°C" if low == high else f"{low:g}°C to {high:g}°C"

    highs, lows = values("high"), values("low")
    if highs and lows:
        high_phrase = (
            f"Daytime highs range from {span(highs)}"
            if min(highs) != max(highs)
            else f"Daytime highs are {span(highs)}"
        )
        temperatures = f"{high_phrase}, with overnight lows of {span(lows)}."
    elif highs:
        temperatures = f"Daytime highs are forecast at {span(highs)}."
    elif lows:
        temperatures = f"Overnight lows are forecast at {span(lows)}."
    else:
        temperatures = "Temperature details are unavailable for this outlook."
    return {
        "overview": overview,
        "precipitation": precipitation,
        "temperatures": temperatures,
        "validUntil": min(str(p["valid_end"]) for p in active),
    }


def _city_site_label(site: dict[str, object]) -> str:
    return re.sub(r"\s+\([^()]*\)$", "", str(site.get("site_name", ""))).strip()


def forecast_locality(region: str, sites: list[dict[str, object]], province: str = "") -> str:
    """Choose an official city-site label, independently of the newest bulletin.

    Prefer the first named locality in the region title. Where the title only
    names a county/landscape, use a deterministic official covered city site.
    No client geocoding, inferred town names, or region-ID changes are involved.
    """
    names = {_city_site_label(site) for site in sites} - {""}
    # County titles do not identify their main service town. Only use a preferred
    # label when it is present in the collected official sites for this region.
    preferred = {
        ("NS", "Annapolis County"): "Annapolis Royal",
        ("NS", "Pictou County"): "New Glasgow",
        ("NS", "Kings County"): "Kentville",
        ("NS", "Halifax County - east of Porters Lake"): "Sheet Harbour",
    }.get((province, region))
    if preferred in names:
        return preferred

    def order(name: str) -> tuple[int, int, str]:
        match = re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", region, re.IGNORECASE)
        return (match.start() if match else len(region) + 1, len(name), name.casefold())

    return min(names, key=order) if names else region


def forecast_map_site(
    locality: str,
    sites: list[dict[str, object]],
) -> dict[str, object]:
    """Return the official city site used as a forecast region's map anchor.

    Region centroids are intentionally not calculated from the covered sites:
    coastal regions commonly mix an inland locality with island, headland, or
    marine sites, and their arithmetic mean can fall in open water.
    """

    matching = [site for site in sites if _city_site_label(site).casefold() == locality.casefold()]
    candidates = matching or sites
    if not candidates:
        raise ValueError("city forecast region has no source sites")
    return min(
        candidates,
        key=lambda site: (
            str(site.get("site_name", "")).casefold() != locality.casefold(),
            str(site.get("site_code", "")),
        ),
    )


def normalize_citypage_documents(
    documents: Iterable[dict[str, object]],
    *,
    generated_at: datetime,
) -> dict[str, object]:
    """Collapse duplicate city sites into their official forecast regions."""

    grouped: defaultdict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for document in documents:
        grouped[(str(document["province"]), str(document["region"]))].append(document)
    features: list[dict[str, object]] = []
    available_starts: list[str] = []
    available_ends: list[str] = []
    issued_at: list[str] = []
    for (province, region), sites in sorted(grouped.items()):
        representative = max(
            sites,
            key=lambda item: (str(item["issued_at"]), str(item["site_code"])),
        )
        periods = representative["periods"]
        if not isinstance(periods, list) or not periods:
            continue
        starts = [str(period["valid_start"]) for period in periods]
        ends = [str(period["valid_end"]) for period in periods]
        available_starts.append(starts[0])
        available_ends.append(ends[-1])
        issued_at.append(str(representative["issued_at"]))
        locality = forecast_locality(region, sites, province)
        map_site = forecast_map_site(locality, sites)
        longitude = float(map_site["longitude"])
        latitude = float(map_site["latitude"])
        area_id = hashlib.sha256(f"{province}\0{region}".encode()).hexdigest()[:16]
        features.append(
            {
                "type": "Feature",
                "id": area_id,
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        round(longitude, 5),
                        round(latitude, 5),
                    ],
                },
                "properties": {
                    "area_id": area_id,
                    "name": region,
                    "locality": locality,
                    "map_site": map_site["site_code"],
                    "briefing": forecast_briefing(periods, generated_at),
                    "province": province,
                    "issued_at": representative["issued_at"],
                    "source_site": representative["site_code"],
                    "source_sites": sorted(str(site["site_code"]) for site in sites),
                    "periods": periods,
                },
            }
        )
    if not features:
        raise ValueError("city forecast normalization produced no forecast regions")
    return {
        "type": "FeatureCollection",
        "schema_version": 1,
        "provider": "eccc",
        "product": "citypage_weather",
        "generated_at": _utc_text(generated_at),
        "issued_at": max(issued_at),
        "available_start": min(available_starts),
        # Use the common horizon so every normalized region still has a
        # forecast at every time exposed by the seven-day view.
        "available_end": min(available_ends),
        "feature_count": len(features),
        "source_site_count": sum(
            len(feature["properties"]["source_sites"]) for feature in features
        ),
        "attribution": ECCC_CITYPAGE_ATTRIBUTION,
        "license_url": ECCC_CITYPAGE_LICENSE_URL,
        "features": features,
    }


def _download_source(
    client: httpx.Client,
    source: CityForecastSource,
    data_root: Path,
    maximum_download_bytes: int,
) -> dict[str, object]:
    response = client.get(source.url)
    response.raise_for_status()
    payload = response.content
    if len(payload) > maximum_download_bytes:
        raise ValueError(f"city forecast {source.filename} exceeds the configured size limit")
    try:
        parsed = parse_citypage_xml(payload)
    except CityForecastUnavailable:
        return {
            "site_code": source.site_code,
            "province": source.province,
            "filename": source.filename,
            "url": source.url,
            "status": "unavailable",
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    if parsed["site_code"] != source.site_code or parsed["province"] != source.province:
        raise ValueError(f"city forecast identity mismatch for {source.filename}")
    destination = resolve_under(data_root, citypage_raw_relative_path(source))
    # Preserve source revisions before replacing the compatibility latest path.
    for body in ([destination.read_bytes()] if destination.is_file() else []) + [payload]:
        digest = hashlib.sha256(body).hexdigest()
        archive = resolve_under(
            data_root,
            Path(
                "raw/eccc/citypage_weather/history",
                source.province,
                source.site_code,
                f"{digest}.xml",
            ),
        )
        if not archive.exists():
            _atomic_bytes(archive, body)
    _atomic_bytes(destination, payload)
    return {
        "site_code": source.site_code,
        "province": source.province,
        "filename": source.filename,
        "url": source.url,
        "relative_path": citypage_raw_relative_path(source).as_posix(),
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def ingest_city_forecasts(
    settings: CityForecastSettings,
    data_root: Path,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    """Discover amendments, atomically refresh raw XML, and publish regions."""

    collected_at = now or datetime.now(UTC)
    if collected_at.tzinfo is None:
        raise ValueError("city forecast collection time must be timezone-aware")
    data_root.mkdir(parents=True, exist_ok=True)
    free_bytes = shutil.disk_usage(data_root).free
    if free_bytes < settings.minimum_free_bytes:
        raise OSError(
            f"city forecast ingestion requires {settings.minimum_free_bytes} "
            f"free bytes but only {free_bytes} are available"
        )
    timeout = httpx.Timeout(settings.timeout_seconds, connect=15.0)
    headers = {"User-Agent": "weather-platform-city-forecast/0.1"}
    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers=headers,
    ) as client:
        discovered = discover_latest_sources(
            client,
            settings,
            now=collected_at,
        )
        manifest = _read_manifest(data_root)
        existing_sources = manifest.get("sources", {})
        if not isinstance(existing_sources, dict):
            existing_sources = {}
        changed = [
            source
            for source in discovered
            if (
                not isinstance(existing_sources.get(source.site_code), dict)
                or existing_sources[source.site_code].get("filename") != source.filename
                or (
                    existing_sources[source.site_code].get("status") != "unavailable"
                    and not resolve_under(
                        data_root,
                        citypage_raw_relative_path(source),
                    ).is_file()
                )
            )
        ]
        with ThreadPoolExecutor(max_workers=settings.parallel_downloads) as executor:
            downloaded = list(
                executor.map(
                    lambda source: _download_source(
                        client,
                        source,
                        data_root,
                        settings.maximum_download_bytes,
                    ),
                    changed,
                )
            )

    sources = {
        key: value
        for key, value in existing_sources.items()
        if isinstance(key, str) and isinstance(value, dict)
    }
    sources.update({str(item["site_code"]): item for item in downloaded})
    documents: list[dict[str, object]] = []
    valid_sources: dict[str, dict[str, object]] = {}
    for site_code, source in sorted(sources.items()):
        relative = source.get("relative_path")
        if not isinstance(relative, str):
            continue
        path = resolve_under(data_root, Path(relative))
        if not path.is_file() or path.is_symlink():
            continue
        try:
            parsed = parse_citypage_xml(path.read_bytes())
        except (OSError, ValueError):
            continue
        if parsed["site_code"] != site_code:
            continue
        documents.append(parsed)
        valid_sources[site_code] = source
    snapshot = normalize_citypage_documents(
        documents,
        generated_at=collected_at,
    )
    snapshot_path = resolve_under(data_root, citypage_latest_relative_path())
    from weather_ingest.forecast_insights import archive_bulletins

    if snapshot_path.is_file():
        archive_bulletins(data_root, json.loads(snapshot_path.read_bytes()))
    archive_bulletins(data_root, snapshot)
    _atomic_json(snapshot_path, snapshot)
    snapshot_bytes = snapshot_path.read_bytes()
    manifest_payload = {
        "schema_version": 1,
        "provider": "eccc",
        "product": "citypage_weather",
        "collected_at": _utc_text(collected_at),
        "source_site_count": len(valid_sources),
        "changed_site_count": len(downloaded),
        "unavailable_site_count": sum(
            source.get("status") == "unavailable" for source in sources.values()
        ),
        "region_count": snapshot["feature_count"],
        "sources": valid_sources,
        "snapshot": {
            "relative_path": citypage_latest_relative_path().as_posix(),
            "size_bytes": len(snapshot_bytes),
            "sha256": hashlib.sha256(snapshot_bytes).hexdigest(),
        },
    }
    _atomic_json(
        resolve_under(data_root, citypage_manifest_relative_path()),
        manifest_payload,
    )
    return {
        "status": "updated" if downloaded else "unchanged",
        "changed_site_count": len(downloaded),
        "unavailable_site_count": manifest_payload["unavailable_site_count"],
        "source_site_count": len(valid_sources),
        "region_count": snapshot["feature_count"],
        "issued_at": snapshot["issued_at"],
        "available_start": snapshot["available_start"],
        "available_end": snapshot["available_end"],
        "snapshot_relative_path": citypage_latest_relative_path().as_posix(),
    }
