import json
from pathlib import Path

import pytest
import yaml
from weather_ingest.smoke_sensitivity_matrix import (
    build_sensitivity_matrix,
    evaluate_sensitivity_matrix,
)


def test_matrix_freezes_exact_one_factor_differences(tmp_path: Path) -> None:
    central = tmp_path / "central.yaml"
    central.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "candidate_version": "central",
                "cffeps": {"emission_factor_uncertainty": "central"},
                "selection": {"area_curve": "central"},
                "source_time": {"timing": "central"},
                "flexpart": {"threads": 8, "particles": 1, "deposition": {}},
                "observations": {"surface_pm25": {"background": "median"}},
            }
        )
    )
    factors = [
        ("central", {}, []),
        (
            "emission_factors",
            {"cffeps": {"emission_factor_uncertainty": "low"}},
            ["/cffeps/emission_factor_uncertainty"],
        ),
        ("burned_area", {"selection": {"area_curve": "low"}}, ["/selection/area_curve"]),
        ("vertical_injection", {"cffeps": {"injection": "uniform"}}, ["/cffeps/injection"]),
        ("particles", {"flexpart": {"particles": 2}}, ["/flexpart/particles"]),
        ("threads", {"flexpart": {"threads": 1}}, ["/flexpart/threads"]),
        ("deposition", {"flexpart": {"deposition": {"wet": False}}}, ["/flexpart/deposition/wet"]),
        (
            "surface_background",
            {"observations": {"surface_pm25": {"background": "p20"}}},
            ["/observations/surface_pm25/background"],
        ),
    ]
    spec = tmp_path / "spec.yaml"
    spec.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "members": [
                    {
                        "candidate_id": f"candidate-{index}",
                        "factor": factor,
                        "level": "test",
                        "overrides": override,
                        "allowed_changed_paths": paths,
                    }
                    for index, (factor, override, paths) in enumerate(factors)
                ],
            }
        )
    )
    manifest = build_sensitivity_matrix(
        central_config=central,
        matrix_specification=spec,
        output_directory=tmp_path / "out",
    )
    assert manifest["member_count"] == 8


def test_matrix_rejects_undeclared_change(tmp_path: Path) -> None:
    central = tmp_path / "central.yaml"
    central.write_text("schema_version: 1\ncandidate_version: old\nvalue: 1\n")
    spec = tmp_path / "spec.yaml"
    spec.write_text(
        "schema_version: 1\nmembers:\n"
        "  - candidate_id: bad\n"
        "    factor: central\n"
        "    level: bad\n"
        "    overrides: {value: 2}\n"
        "    allowed_changed_paths: []\n"
    )
    with pytest.raises(ValueError, match="changed paths"):
        build_sensitivity_matrix(
            central_config=central,
            matrix_specification=spec,
            output_directory=tmp_path / "out",
        )


def test_matrix_evaluation_preserves_reversals_for_review(tmp_path: Path) -> None:
    matrix = tmp_path / "matrix.json"
    matrix.write_text(
        """{
  "members": [
    {"candidate_id":"central","factor":"central","level":"central","required":true,"source_mass_group":"same"},
    {"candidate_id":"low","factor":"emission_factors","level":"low","required":true,"source_mass_group":"low"},
    {"candidate_id":"high","factor":"emission_factors","level":"high","required":true,"source_mass_group":"high"}
  ]
}"""
    )
    paths = []
    for identity, mass, passed in (
        ("central", 10, True),
        ("low", 5, False),
        ("high", 15, True),
    ):
        path = tmp_path / f"{identity}.json"
        path.write_text(
            json.dumps(
                {
                    "candidate_id": identity,
                    "whole_output_verified": True,
                    "source_mass_kg": mass,
                    "scientific_metrics": {
                        "w2": {
                            "criteria_passed": passed,
                            "normalized_mean_bias": 1 if passed else -1,
                        }
                    },
                }
            )
        )
        paths.append(path)
    report = evaluate_sensitivity_matrix(
        matrix_manifest=matrix,
        result_manifests=paths,
    )
    assert report["emission_factor_source_mass_ordered"]
    assert report["qualitative_reversals"]
    assert not report["all_reversals_physically_explained_and_reviewed"]
