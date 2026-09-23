"""RDPS North American deterministic source adapter."""

from weather_ingest.adapters.eccc_forecast import EcccForecastAdapter


class RdpsAdapter(EcccForecastAdapter):
    product_code = "rdps"
