"""HREPA ensemble precipitation-analysis source adapter."""

from weather_ingest.adapters.eccc_analysis import EcccAnalysisAdapter


class HrepaAdapter(EcccAnalysisAdapter):
    product_code = "hrepa"
    product_kind = "ensemble_analysis"
