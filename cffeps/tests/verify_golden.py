#!/usr/bin/env python3
"""Execute the portable CFFEPS driver against the versioned golden cases."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", type=Path, default=ROOT / "bin/weatherapp-cffeps")
    args = parser.parse_args()
    registry = json.loads((TESTS / "golden_cases.json").read_text(encoding="utf-8"))
    profiles = TESTS / registry["profile_fixture"]
    if sha256(profiles) != registry["profile_fixture_sha256"]:
        raise SystemExit("profile fixture checksum changed")

    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="cffeps-golden-") as temporary:
        work = Path(temporary)
        for case in registry["cases"]:
            output = work / f"{case['name']}.csv"
            config = work / f"{case['name']}.nml"
            config.write_text(
                "&portable_cffeps\n"
                f" profile_path='{profiles.resolve()}'\n output_path='{output}'\n"
                f" fueltype_index={case['fueltype_index']}\n detection_julian=183\n"
                " detection_hhmm=0\n nsteps=3\n lat=45.0\n lon=-63.0\n"
                f" ffmc={case['ffmc']}\n dmc={case['dmc']}\n dc={case['dc']}\n"
                f" estarea_ha={case['estarea_ha']}\n elevation_m=100.0\n"
                " cffeps_fire_shape='weighted'\n cffeps_fire_type='dry'\n/\n",
                encoding="ascii",
            )
            process = subprocess.run(
                [str(args.executable.resolve()), str(config)],
                capture_output=True,
                text=True,
                check=False,
            )
            if process.returncode != 0:
                failures.append(f"{case['name']}: exit {process.returncode}")
                continue
            rows = list(csv.DictReader(output.open(encoding="ascii")))
            actual = {
                "maximum_plume_top_m_agl": max(float(row["plume_top_m_agl"]) for row in rows),
                "final_fire_area_ha": float(rows[-1]["fire_area_ha"]),
                "flaming_fuel_t": sum(float(row["flaming_fuel_t_h"]) for row in rows),
                "smoldering_fuel_t": sum(float(row["smoldering_fuel_t_h"]) for row in rows),
                "residual_fuel_t": sum(float(row["residual_fuel_t_h"]) for row in rows),
            }
            released = sum(
                actual[name] for name in ("flaming_fuel_t", "smoldering_fuel_t", "residual_fuel_t")
            )
            pending = sum(
                float(rows[-1][name])
                for name in (
                    "pending_flaming_fuel_t",
                    "pending_smoldering_fuel_t",
                    "pending_residual_fuel_t",
                )
            )
            cumulative = float(rows[-1]["total_consumed_fuel_t"])
            relative_difference = (
                abs(released + pending - cumulative) / cumulative if cumulative > 0 else 0.0
            )
            if relative_difference > 0.05 and not math.isclose(
                relative_difference,
                0.05,
                rel_tol=1e-5,
                abs_tol=1e-8,
            ):
                failures.append(f"{case['name']}: released-plus-pending balance failed")
            if sha256(output) != case["output_sha256"]:
                failures.append(f"{case['name']}: output checksum changed")
            for field, value in actual.items():
                if not math.isclose(value, case[field], rel_tol=1e-10, abs_tol=1e-12):
                    failures.append(f"{case['name']}: {field} changed")
        state_case = registry["cases"][0]
        constant_state = work / "constant-fire-weather.txt"
        varying_state = work / "varying-fire-weather.txt"
        constant_state.write_text(
            (f"{state_case['ffmc']} {state_case['dmc']} {state_case['dc']}\n" * 3),
            encoding="ascii",
        )
        varying_state.write_text(
            (
                f"{state_case['ffmc']} {state_case['dmc']} {state_case['dc']}\n"
                f"{state_case['ffmc']} {state_case['dmc']} {state_case['dc']}\n"
                f"{state_case['ffmc'] - 8} {state_case['dmc'] / 2} "
                f"{state_case['dc'] / 2}\n"
            ),
            encoding="ascii",
        )
        state_outputs: dict[str, str] = {}
        for name, state_path in (
            ("constant", constant_state),
            ("varying", varying_state),
        ):
            output = work / f"state-{name}.csv"
            config = work / f"state-{name}.nml"
            config.write_text(
                "&portable_cffeps\n"
                f" profile_path='{profiles.resolve()}'\n output_path='{output}'\n"
                f" fire_weather_state_path='{state_path}'\n"
                f" fueltype_index={state_case['fueltype_index']}\n"
                " detection_julian=183\n detection_hhmm=0\n nsteps=3\n"
                " lat=45.0\n lon=-63.0\n"
                f" ffmc={state_case['ffmc']}\n dmc={state_case['dmc']}\n"
                f" dc={state_case['dc']}\n"
                f" estarea_ha={state_case['estarea_ha']}\n elevation_m=100.0\n"
                " cffeps_fire_shape='weighted'\n cffeps_fire_type='dry'\n/\n",
                encoding="ascii",
            )
            process = subprocess.run(
                [str(args.executable.resolve()), str(config)],
                capture_output=True,
                text=True,
                check=False,
            )
            if process.returncode != 0:
                failures.append(f"state-{name}: exit {process.returncode}")
            else:
                state_outputs[name] = sha256(output)
        if state_outputs.get("constant") != state_case["output_sha256"]:
            failures.append("constant hourly fire-weather states changed the legacy result")
        if state_outputs.get("varying") == state_outputs.get("constant"):
            failures.append("varying hourly fire-weather states had no effect")
        constant_area = work / "constant-estimated-area.txt"
        varying_area = work / "varying-estimated-area.txt"
        constant_area.write_text(
            f"{state_case['estarea_ha']}\n" * 3,
            encoding="ascii",
        )
        varying_area.write_text(
            (
                f"{state_case['estarea_ha'] / 4}\n"
                f"{state_case['estarea_ha'] / 2}\n"
                f"{state_case['estarea_ha']}\n"
            ),
            encoding="ascii",
        )
        area_outputs: dict[str, str] = {}
        for name, area_path in (
            ("constant", constant_area),
            ("varying", varying_area),
        ):
            output = work / f"area-{name}.csv"
            config = work / f"area-{name}.nml"
            config.write_text(
                "&portable_cffeps\n"
                f" profile_path='{profiles.resolve()}'\n output_path='{output}'\n"
                f" estimated_area_state_path='{area_path}'\n"
                f" fueltype_index={state_case['fueltype_index']}\n"
                " detection_julian=183\n detection_hhmm=0\n nsteps=3\n"
                " lat=45.0\n lon=-63.0\n"
                f" ffmc={state_case['ffmc']}\n dmc={state_case['dmc']}\n"
                f" dc={state_case['dc']}\n"
                f" estarea_ha={state_case['estarea_ha']}\n elevation_m=100.0\n"
                " cffeps_fire_shape='weighted'\n cffeps_fire_type='dry'\n/\n",
                encoding="ascii",
            )
            process = subprocess.run(
                [str(args.executable.resolve()), str(config)],
                capture_output=True,
                text=True,
                check=False,
            )
            if process.returncode != 0:
                failures.append(f"area-{name}: exit {process.returncode}")
            else:
                area_outputs[name] = sha256(output)
        if area_outputs.get("constant") != state_case["output_sha256"]:
            failures.append("constant hourly estimated area changed the legacy result")
        if area_outputs.get("varying") == area_outputs.get("constant"):
            failures.append("varying hourly estimated area had no effect")
        sensitivity_outputs: dict[str, str] = {}
        sensitivity_cases = (
            ("m2_pc25", 11, 25.0, 35.0, 80.0),
            ("m2_pc75", 11, 75.0, 35.0, 80.0),
            ("m4_pdf25", 13, 50.0, 25.0, 80.0),
            ("m4_pdf75", 13, 50.0, 75.0, 80.0),
            ("o1_cured35", 17, 50.0, 35.0, 35.0),
            ("o1_cured90", 17, 50.0, 35.0, 90.0),
        )
        for name, fuel_index, percent_conifer, percent_dead_fir, curing in sensitivity_cases:
            output = work / f"{name}.csv"
            config = work / f"{name}.nml"
            config.write_text(
                "&portable_cffeps\n"
                f" profile_path='{profiles.resolve()}'\n output_path='{output}'\n"
                f" fueltype_index={fuel_index}\n detection_julian=183\n"
                " detection_hhmm=0\n nsteps=3\n lat=45.0\n lon=-63.0\n"
                " ffmc=94\n dmc=75\n dc=500\n estarea_ha=175\n elevation_m=100.0\n"
                f" percent_conifer={percent_conifer}\n"
                f" percent_dead_fir={percent_dead_fir}\n"
                f" grass_curing_percent={curing}\n"
                " cffeps_fire_shape='weighted'\n cffeps_fire_type='dry'\n/\n",
                encoding="ascii",
            )
            process = subprocess.run(
                [str(args.executable.resolve()), str(config)],
                capture_output=True,
                text=True,
                check=False,
            )
            if process.returncode != 0:
                failures.append(f"{name}: exit {process.returncode}")
            else:
                sensitivity_outputs[name] = sha256(output)
        for low, high in (
            ("m2_pc25", "m2_pc75"),
            ("m4_pdf25", "m4_pdf75"),
            ("o1_cured35", "o1_cured90"),
        ):
            if sensitivity_outputs.get(low) == sensitivity_outputs.get(high):
                failures.append(f"{low}/{high}: FBP parameter had no effect")
    if failures:
        print("\n".join(failures))
        return 1
    print(
        f"PASS: {len(registry['cases'])} CFFEPS 4.1 golden cases and "
        f"{len(sensitivity_cases)} FBP sensitivity cases; hourly causal "
        "fire-weather and estimated-area profiles verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
