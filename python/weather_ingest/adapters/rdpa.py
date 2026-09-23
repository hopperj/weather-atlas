"""RDPA deterministic precipitation-analysis source adapter."""

from weather_ingest.adapters.eccc_analysis import EcccAnalysisAdapter


class RdpaAdapter(EcccAnalysisAdapter):
    product_code = "rdpa"
    product_kind = "analysis"
