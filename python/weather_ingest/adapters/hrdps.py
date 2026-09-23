"""HRDPS continental-grid source adapter."""

from weather_ingest.adapters.eccc_forecast import EcccForecastAdapter


class HrdpsAdapter(EcccForecastAdapter):
    product_code = "hrdps"
