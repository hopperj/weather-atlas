import hashlib
import json
from pathlib import Path

from weather_ingest.vertical_input_readiness import (
    audit_vertical_input_readiness,
    build_assignment_template,
)


def test_vertical_readiness_requires_input_only_assignment_and_all_inputs(
    tmp_path: Path,
) -> None:
    vertical_path = tmp_path / "vertical.json"
    vertical = {
        "artifact_type": "w1-input-only-misr-merlin-vertical-ledger",
        "overpass_count": 1,
        "overpasses": [{"overpass_id": "O1"}],
    }
    vertical_path.write_text(json.dumps(vertical))
    input_file = tmp_path / "input.dat"
    input_file.write_text("frozen")
    artifact = {
        "path": input_file.as_posix(),
        "sha256": hashlib.sha256(input_file.read_bytes()).hexdigest(),
    }
    assignment = build_assignment_template(vertical)
    assignment["complete_candidate_pool_preregistered"] = True
    assignment["complete_candidate_pool_rationale"] = "Complete provider pool."
    record = assignment["assignments"][0]
    record.update(
        {
            "event_id": "event-1",
            "assignment_method": "location_time_geometry_v1",
            "status": "ready",
        }
    )
    record["artifacts"] = {
        name: artifact
        for name in ("fuel", "independent_area", "cffdrs_state", "transport_meteorology")
    }
    assignment_path = tmp_path / "assignments.json"
    assignment_path.write_text(json.dumps(assignment))
    report = audit_vertical_input_readiness(
        vertical_ledger_path=vertical_path,
        assignment_ledger_path=assignment_path,
        minimum_overpasses=1,
    )
    assert report["all_required_vertical_inputs_complete"]
