"""Safe generation and round-trip validation of run-local FLEXPART options."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SPECIES_NUMBERS = {"PM25": 901, "CO": 902, "BC": 903}
MAXIMUM_OUTPUT_GRID_CELLS = 50_000


@dataclass(frozen=True, slots=True)
class FlexpartDomain:
    west: float
    south: float
    east: float
    north: float
    spacing: float

    def __post_init__(self) -> None:
        if not (-180 <= self.west < self.east <= 180 and -90 <= self.south < self.north <= 90):
            raise ValueError("invalid FLEXPART output domain")
        if self.spacing not in {0.25, 0.5, 1.0}:
            raise ValueError("unsupported FLEXPART output spacing")
        longitude_cells = math.ceil((self.east - self.west) / self.spacing) + 1
        latitude_cells = math.ceil((self.north - self.south) / self.spacing) + 1
        if longitude_cells * latitude_cells > MAXIMUM_OUTPUT_GRID_CELLS:
            raise ValueError("FLEXPART output domain exceeds configured bound")

    @property
    def nx(self) -> int:
        return math.ceil((self.east - self.west) / self.spacing) + 1

    @property
    def ny(self) -> int:
        return math.ceil((self.north - self.south) / self.spacing) + 1


@dataclass(frozen=True, slots=True)
class FlexpartDeposition:
    wet: bool = True
    dry: bool = True
    settling: bool = True

    def __post_init__(self) -> None:
        if not self.settling:
            raise ValueError(
                "weatherapp requires gravitational settling to remain enabled"
            )


DEFAULT_DEPOSITION = FlexpartDeposition()


def _date_time(value: datetime) -> tuple[int, int]:
    value = value.astimezone(UTC)
    return int(value.strftime("%Y%m%d")), int(value.strftime("%H%M%S"))


def write_command(
    path: Path,
    start: datetime,
    end: datetime,
    *,
    threads: int,
    deposition: FlexpartDeposition = DEFAULT_DEPOSITION,
) -> None:
    if start.tzinfo is None or end.tzinfo is None or not start < end:
        raise ValueError("FLEXPART times must be aware and ordered")
    if (end - start).total_seconds() > 24 * 3600:
        raise ValueError("FLEXPART run exceeds 24-hour bound")
    if not 1 <= threads <= 16:
        raise ValueError("FLEXPART grid threads must be in [1, 16]")
    start_date, start_time = _date_time(start)
    end_date, end_time = _date_time(end)
    path.write_text(
        f"""&COMMAND
 LDIRECT=1,
 IBDATE={start_date}, IBTIME={start_time:06d},
 IEDATE={end_date}, IETIME={end_time:06d},
 LOUTSTEP=3600, LOUTAVER=3600, LOUTSAMPLE=300,
 LOUTRESTART=-1, LSYNCTIME=300, CTL=-5.0, IFINE=4,
 IOUT=1, IPOUT=0,
 LSUBGRID=1, LCONVECTION=1, LTURBULENCE=1, LTURBULENCE_MESO=0,
 LAGESPECTRA=0, IPIN=0, IOUTPUTFOREACHRELEASE=0, IFLUX=1,
 MDOMAINFILL=0, IND_SOURCE=1, IND_RECEPTOR=1, MQUASILAG=0,
 NESTED_OUTPUT=0, LNETCDFOUT=1, LINIT_COND=0, SFC_ONLY=0,
 CBLFLAG=1, NXSHIFT=0, MAXTHREADGRID={threads}, MAXFILESIZE=10000,
 LOGVERTINTERP=0, DRYDEP_ENABLED=.{str(deposition.dry).lower()}.,
 WETDEP_ENABLED=.{str(deposition.wet).lower()}.,
/
""",
        encoding="ascii",
    )


def write_outgrid(path: Path, domain: FlexpartDomain) -> None:
    path.write_text(
        f"""&OUTGRID
 OUTLON0={domain.west:.6f}, OUTLAT0={domain.south:.6f},
 NUMXGRID={domain.nx}, NUMYGRID={domain.ny},
 DXOUT={domain.spacing:.6f}, DYOUT={domain.spacing:.6f},
 OUTHEIGHTS=50.0,100.0,250.0,500.0,1000.0,2000.0,4000.0,8000.0,20000.0,
/
""",
        encoding="ascii",
    )


def write_pathnames(path: Path) -> None:
    path.write_text("options/\noutput/\nmet/\nmet/AVAILABLE\n", encoding="ascii")


def parse_namelist_scalars(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="ascii").splitlines():
        line = raw_line.split("!", 1)[0].strip()
        for item in line.split(","):
            if "=" in item:
                name, value = item.split("=", 1)
                values[name.strip().upper()] = value.strip()
    return values


def validate_generated_options(
    options: Path,
    start: datetime,
    end: datetime,
    domain: FlexpartDomain,
    deposition: FlexpartDeposition = DEFAULT_DEPOSITION,
) -> None:
    command = parse_namelist_scalars(options / "COMMAND")
    outgrid = parse_namelist_scalars(options / "OUTGRID")
    expected_start = _date_time(start)
    expected_end = _date_time(end)
    if (int(command["IBDATE"]), int(command["IBTIME"])) != expected_start:
        raise ValueError("generated COMMAND start did not round-trip")
    if (int(command["IEDATE"]), int(command["IETIME"])) != expected_end:
        raise ValueError("generated COMMAND end did not round-trip")
    if int(command["LCONVECTION"]) != 1 or int(command["LTURBULENCE"]) != 1:
        raise ValueError("required transport physics was not enabled")
    if (command["WETDEP_ENABLED"].lower().strip(".") == "true") != deposition.wet:
        raise ValueError("generated wet-deposition switch did not round-trip")
    if (command["DRYDEP_ENABLED"].lower().strip(".") == "true") != deposition.dry:
        raise ValueError("generated dry-deposition switch did not round-trip")
    if int(outgrid["NUMXGRID"]) != domain.nx or int(outgrid["NUMYGRID"]) != domain.ny:
        raise ValueError("generated OUTGRID dimensions did not round-trip")
