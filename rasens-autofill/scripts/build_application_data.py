#!/usr/bin/env python3
"""Build Chrome-extension autofill rows using visa-app backend generator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "visa-app/backend"
sys.path.insert(0, str(BACKEND_DIR))

from application_data import build_application_data  # noqa: E402


def build_rows(case_data: dict, mapping_data: dict, form_definitions: dict | None = None) -> list[dict]:
    if form_definitions is None:
        form_path = Path(__file__).resolve().parents[1] / "data/form_definitions/rasens_offer_fields.json"
        form_definitions = json.loads(form_path.read_text())
    response = build_application_data(
        {"case_id": case_data.get("case", {}).get("case_id", ""), "workflow_state": "extracted", "case_data": case_data},
        mapping_data,
        form_definitions,
    )
    return response["rows"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_data", type=Path)
    parser.add_argument("mapping", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    case_data = json.loads(args.case_data.read_text())
    mapping_data = json.loads(args.mapping.read_text())
    form_path = Path(__file__).resolve().parents[1] / "data/form_definitions/rasens_offer_fields.json"
    form_definitions = json.loads(form_path.read_text())
    rows = build_rows(case_data, mapping_data, form_definitions)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
