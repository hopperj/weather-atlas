"""ECCC source adapters and the single reviewed adapter registry."""

from __future__ import annotations

from types import MappingProxyType

from weather_ingest.adapters.eccc_analysis import EcccAnalysisAdapter
from weather_ingest.adapters.eccc_forecast import EcccForecastAdapter
from weather_ingest.adapters.gdps import GdpsAdapter
from weather_ingest.adapters.hrdpa import HrdpaAdapter
from weather_ingest.adapters.hrdps import HrdpsAdapter
from weather_ingest.adapters.hrepa import HrepaAdapter
from weather_ingest.adapters.raqdps import RaqdpsAdapter
from weather_ingest.adapters.rdpa import RdpaAdapter
from weather_ingest.adapters.rdps import RdpsAdapter
from weather_ingest.config import ProductConfig
from weather_ingest.http_listing import ListingSource

ADAPTER_TYPES = MappingProxyType(
    {
        "gdps": GdpsAdapter,
        "hrdpa": HrdpaAdapter,
        "hrdps": HrdpsAdapter,
        "hrepa": HrepaAdapter,
        "raqdps": RaqdpsAdapter,
        "rdpa": RdpaAdapter,
        "rdps": RdpsAdapter,
    }
)


def adapter_type_for(
    config: ProductConfig,
) -> type[EcccForecastAdapter] | type[EcccAnalysisAdapter]:
    """Resolve a validated product configuration to its source adapter."""

    try:
        return ADAPTER_TYPES[config.adapter]
    except KeyError as exc:
        raise ValueError(
            f"no ECCC forecast adapter is implemented for {config.code!r} "
            f"(adapter {config.adapter!r})"
        ) from exc


def create_adapter(
    config: ProductConfig, listing_source: ListingSource
) -> EcccForecastAdapter | EcccAnalysisAdapter:
    """Construct the configured adapter without product-specific call sites."""

    return adapter_type_for(config)(config, listing_source)


__all__ = [
    "ADAPTER_TYPES",
    "GdpsAdapter",
    "HrdpaAdapter",
    "HrdpsAdapter",
    "HrepaAdapter",
    "RaqdpsAdapter",
    "RdpaAdapter",
    "RdpsAdapter",
    "adapter_type_for",
    "create_adapter",
]
