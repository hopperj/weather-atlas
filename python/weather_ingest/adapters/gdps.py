"""GDPS global deterministic source adapter."""

from weather_ingest.adapters.eccc_forecast import EcccForecastAdapter


class GdpsAdapter(EcccForecastAdapter):
    product_code = "gdps"
