from __future__ import annotations

from datetime import UTC, datetime

import pytest
from weather_ingest.eccc_city_forecasts import (
    CityForecastSettings,
    forecast_briefing,
    forecast_locality,
    normalize_citypage_documents,
    parse_citypage_listing,
    parse_citypage_xml,
    precipitation_amount,
)


def city_xml(
    *,
    site_code: str = "s0000318",
    site_name: str = "Halifax",
    region: str = "Halifax Metro and Halifax County West",
    longitude: str = "63.57W",
    issued_at: str = "20260728190000",
    amount_text: str = "Rainfall amount 10 to 20 mm.",
) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<siteData>
  <location>
    <province code="ns">Nova Scotia</province>
    <name code="{site_code}" lat="44.65N" lon="{longitude}">{site_name}</name>
    <region>{region}</region>
  </location>
  <forecastGroup>
    <dateTime name="forecastIssue" zone="UTC" UTCOffset="0">
      <timeStamp>{issued_at}</timeStamp>
    </dateTime>
    <dateTime name="forecastIssue" zone="ADT" UTCOffset="-3">
      <timeStamp>20260728160000</timeStamp>
    </dateTime>
    <forecast>
      <period textForecastName="Tonight">Tuesday night</period>
      <textSummary>Rain tonight. {amount_text} Low 17.</textSummary>
      <abbreviatedForecast>
        <pop units="%">80</pop>
        <textSummary>Rain</textSummary>
      </abbreviatedForecast>
      <temperatures>
        <temperature unitType="metric" units="C" class="low">17</temperature>
      </temperatures>
      <precipitation><textSummary>{amount_text}</textSummary></precipitation>
      <relativeHumidity units="%">95</relativeHumidity>
    </forecast>
    <forecast>
      <period textForecastName="Wednesday">Wednesday</period>
      <textSummary>Sunny. High 25.</textSummary>
      <abbreviatedForecast>
        <pop units="%">0</pop>
        <textSummary>Sunny</textSummary>
      </abbreviatedForecast>
      <temperatures>
        <temperature unitType="metric" units="C" class="high">25</temperature>
      </temperatures>
      <precipitation><textSummary/></precipitation>
      <relativeHumidity units="%">60</relativeHumidity>
    </forecast>
  </forecastGroup>
</siteData>
""".encode()


def test_settings_validate_provider_bounds() -> None:
    settings = CityForecastSettings.from_environment(
        {
            "ECCC_CITY_FORECAST_PROVINCES": "NS,PE",
            "ECCC_CITY_FORECAST_LOOKBACK_HOURS": "2",
            "ECCC_CITY_FORECAST_MAXIMUM_SITES": "100",
            "ECCC_CITY_FORECAST_MAXIMUM_DOWNLOAD_BYTES": "200000",
            "ECCC_CITY_FORECAST_MINIMUM_FREE_BYTES": "0",
            "ECCC_CITY_FORECAST_TIMEOUT_SECONDS": "30",
            "ECCC_CITY_FORECAST_PARALLEL_DOWNLOADS": "4",
        }
    )

    assert settings.provinces == ("NS", "PE")
    assert settings.parallel_downloads == 4
    with pytest.raises(ValueError, match="unsupported"):
        CityForecastSettings(provinces=("XX",))


def test_locality_uses_official_city_names_without_changing_region_identity():
    documents = [
        parse_citypage_xml(city_xml(site_name="Halifax (Shearwater)", site_code="s0000021")),
        parse_citypage_xml(city_xml()),
    ]
    snapshot = normalize_citypage_documents(
        documents, generated_at=datetime(2026, 7, 28, 20, tzinfo=UTC)
    )
    props = snapshot["features"][0]["properties"]
    assert props["name"] == "Halifax Metro and Halifax County West"
    assert props["locality"] == "Halifax"
    assert props["map_site"] == "s0000318"
    assert (
        props["area_id"]
        == normalize_citypage_documents(
            documents[:1], generated_at=datetime(2026, 7, 28, 20, tzinfo=UTC)
        )["features"][0]["properties"]["area_id"]
    )
    assert (
        forecast_locality(
            "City of Edmonton - St. Albert - Sherwood Park",
            [
                {"site_name": "St. Albert"},
                {"site_name": "Edmonton"},
                {"site_name": "Sherwood Park"},
            ],
        )
        == "Edmonton"
    )
    assert forecast_locality("Queens County", [{"site_name": "Liverpool"}]) == "Liverpool"
    assert (
        forecast_locality("County", [{"site_name": "Sainte-Anne-des-Monts"}])
        == "Sainte-Anne-des-Monts"
    )
    assert forecast_locality("Unknown region", []) == "Unknown region"
    assert (
        forecast_locality(
            "Pictou County", [{"site_name": "Caribou"}, {"site_name": "New Glasgow"}], "NS"
        )
        == "New Glasgow"
    )
    assert forecast_locality("Pictou County", [{"site_name": "Caribou"}], "NS") == "Caribou"


def test_briefing_keeps_uncertainty_and_computes_ranges_only_on_server():
    periods = parse_citypage_xml(city_xml())["periods"]
    periods[0]["condition"] = "Chance of showers"
    periods[0]["pop_percent"] = 40
    periods[1]["condition"] = "Showers"
    result = forecast_briefing(periods, datetime(2026, 7, 28, 20, tzinfo=UTC))
    assert result["precipitation"] == "Showers are possible Tuesday, and expected Wednesday."
    assert result["temperatures"] == "Daytime highs are 25°C, with overnight lows of 17°C."
    assert result["validUntil"] == periods[0]["valid_end"]
    assert forecast_briefing(periods, datetime(2026, 8, 1, tzinfo=UTC)) is None


def test_briefing_does_not_turn_missing_temperature_or_probability_into_zero():
    periods = parse_citypage_xml(city_xml())["periods"]
    for period in periods:
        period["temperature_c"] = None
        period["pop_percent"] = None
        period["condition"] = "Cloudy"
    result = forecast_briefing(periods, datetime(2026, 7, 28, 20, tzinfo=UTC))
    assert "unavailable" in result["temperatures"]
    assert "0" not in result["precipitation"]
    assert "No wet weather is mentioned" in result["precipitation"]
    for period in periods:
        period["condition"] = "Freezing fog"
    assert (
        "No wet weather is mentioned"
        in forecast_briefing(periods, datetime(2026, 7, 28, 20, tzinfo=UTC))["precipitation"]
    )


def test_listing_selects_latest_english_issue_per_site() -> None:
    listing = """
    <a href="20260728T180000.000Z_MSC_CitypageWeather_s0000318_en.xml">old</a>
    <a href="20260728T180500.000Z_MSC_CitypageWeather_s0000318_en.xml">new</a>
    <a href="20260728T180500.000Z_MSC_CitypageWeather_s0000318_fr.xml">fr</a>
    <a href="20260728T180100.000Z_MSC_CitypageWeather_s0000365_en.xml">other</a>
    """

    sources = parse_citypage_listing(
        listing,
        province="NS",
        listing_url="https://dd.weather.gc.ca/today/citypage_weather/NS/18/",
    )

    assert [source.site_code for source in sources] == [
        "s0000318",
        "s0000365",
    ]
    assert sources[0].filename.startswith("20260728T180500")
    assert sources[0].url.startswith("https://dd.weather.gc.ca/")


def test_xml_normalizes_values_and_half_day_periods() -> None:
    parsed = parse_citypage_xml(city_xml())

    assert parsed["province"] == "NS"
    assert parsed["region"] == "Halifax Metro and Halifax County West"
    assert parsed["longitude"] == -63.57
    assert parsed["periods"][0] == {
        "period": "Tuesday night",
        "valid_start": "2026-07-28T19:00:00Z",
        "valid_end": "2026-07-29T09:00:00Z",
        "temperature_c": 17.0,
        "temperature_class": "low",
        "relative_humidity_percent": 95.0,
        "pop_percent": 80.0,
        "precipitation_amount": "10–20 mm",
        "condition": "Rain",
    }
    assert parsed["periods"][1]["valid_end"] == "2026-07-29T21:00:00Z"
    assert parsed["periods"][1]["precipitation_amount"] == "0 mm"


def test_precipitation_amount_is_not_invented() -> None:
    assert precipitation_amount("Rain at times.", probability=70) is None
    assert precipitation_amount("", probability=0) == "0 mm"
    assert precipitation_amount("Snowfall amount 5 cm.", probability=100) == "5 cm"


def test_normalization_collapses_sites_into_official_regions() -> None:
    halifax = parse_citypage_xml(city_xml())
    shearwater = parse_citypage_xml(
        city_xml(
            site_code="s0000021",
            site_name="Halifax (Shearwater)",
            longitude="63.50W",
            issued_at="20260728190500",
        )
    )

    snapshot = normalize_citypage_documents(
        [halifax, shearwater],
        generated_at=datetime(2026, 7, 28, 19, 10, tzinfo=UTC),
    )

    assert snapshot["feature_count"] == 1
    assert snapshot["source_site_count"] == 2
    assert snapshot["features"][0]["properties"]["source_site"] == "s0000021"
    # The card points to the named on-land locality, not the average between
    # Halifax and the coastal Shearwater source site.
    assert snapshot["features"][0]["geometry"]["coordinates"] == [-63.57, 44.65]
    assert snapshot["features"][0]["properties"]["locality"] == "Halifax"
    assert snapshot["features"][0]["properties"]["map_site"] == "s0000318"


def test_coastal_region_anchor_uses_named_locality_instead_of_offshore_average() -> None:
    guysborough = parse_citypage_xml(
        city_xml(
            site_code="s0000464",
            site_name="Guysborough",
            region="Guysborough County",
            longitude="61.50W",
        )
    )
    hart_island = parse_citypage_xml(
        city_xml(
            site_code="s0000308",
            site_name="Hart Island",
            region="Guysborough County",
            longitude="61.00W",
        )
    )

    snapshot = normalize_citypage_documents(
        [guysborough, hart_island],
        generated_at=datetime(2026, 7, 28, 20, tzinfo=UTC),
    )

    feature = snapshot["features"][0]
    assert feature["geometry"]["coordinates"] == [-61.5, 44.65]
    assert feature["properties"]["locality"] == "Guysborough"
    assert feature["properties"]["map_site"] == "s0000464"
