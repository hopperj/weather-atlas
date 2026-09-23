"""RAQDPS North American air-quality source adapter."""

from weather_ingest.adapters.eccc_forecast import EcccForecastAdapter


class RaqdpsAdapter(EcccForecastAdapter):
    product_code = "raqdps"
