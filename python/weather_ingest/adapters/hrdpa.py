"""HRDPA deterministic precipitation-analysis source adapter."""

from weather_ingest.adapters.eccc_analysis import EcccAnalysisAdapter


class HrdpaAdapter(EcccAnalysisAdapter):
    product_code = "hrdpa"
    product_kind = "analysis"
