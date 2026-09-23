"""Optional geospatial runtime tool discovery for diagnostics and readiness."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolStatus:
    name: str
    available: bool
    executable: str | None
    version: str | None


def inspect_tool(name: str, version_args: tuple[str, ...]) -> ToolStatus:
    executable = shutil.which(name)
    if executable is None:
        return ToolStatus(name, False, None, None)
    completed = subprocess.run(
        (executable, *version_args),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    output = (completed.stdout or completed.stderr).strip().splitlines()
    version = output[0] if completed.returncode == 0 and output else None
    return ToolStatus(name, True, executable, version)


def inspect_geospatial_tools() -> tuple[ToolStatus, ...]:
    return (
        inspect_tool("grib_ls", ("-V",)),
        inspect_tool("gdal_translate", ("--version",)),
        inspect_tool("gdalinfo", ("--version",)),
        inspect_tool("gdal_calc.py", ("--help",)),
    )
