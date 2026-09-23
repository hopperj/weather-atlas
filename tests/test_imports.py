from importlib import import_module

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "weather_common",
        "weather_common.settings",
        "weather_api.main",
        "weather_tiles.main",
    ],
)
def test_python_packages_import(module_name: str) -> None:
    assert import_module(module_name) is not None

