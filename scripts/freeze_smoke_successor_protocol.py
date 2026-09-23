#!/usr/bin/env python3
"""Freeze the successor protocol or corrected model release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from weather_ingest.smoke_protocol import (
    build_reviewed_release,
    freeze_model_release,
    freeze_successor_protocol,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="kind", required=True)
    protocol = subparsers.add_parser("protocol")
    protocol.add_argument("--protocol-config", type=Path, required=True)
    protocol.add_argument("--protocol-document", type=Path, required=True)
    protocol.add_argument("--sensitivity-specification", type=Path, required=True)
    protocol.add_argument("--operator-source", type=Path, action="append", default=[])
    protocol.add_argument("--output", type=Path, required=True)
    release = subparsers.add_parser("release")
    release.add_argument("--w5-manifest", type=Path, required=True)
    release.add_argument("--executable", type=Path, action="append", default=[])
    release.add_argument("--configuration", type=Path, action="append", default=[])
    release.add_argument("--runner", type=Path, action="append", default=[])
    release.add_argument("--extension-evidence", type=Path, action="append", default=[])
    release.add_argument("--output", type=Path, required=True)
    reviewed = subparsers.add_parser("reviewed-release")
    reviewed.add_argument("--release-freeze", type=Path, required=True)
    reviewed.add_argument("--final-review-gate", type=Path, required=True)
    reviewed.add_argument("--release-id", required=True)
    reviewed.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.kind == "protocol":
        payload = freeze_successor_protocol(
            protocol_config=arguments.protocol_config,
            protocol_document=arguments.protocol_document,
            sensitivity_specification=arguments.sensitivity_specification,
            operator_sources=arguments.operator_source,
            output=arguments.output,
        )
    elif arguments.kind == "release":
        payload = freeze_model_release(
            w5_manifest=arguments.w5_manifest,
            executable_paths=arguments.executable,
            configuration_paths=arguments.configuration,
            runner_paths=arguments.runner,
            extension_evidence_paths=arguments.extension_evidence,
            output=arguments.output,
        )
    else:
        payload = build_reviewed_release(
            release_freeze=arguments.release_freeze,
            final_review_gate=arguments.final_review_gate,
            release_id=arguments.release_id,
            output=arguments.output,
        )
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
