#!/usr/bin/env python3
"""Prepare a blind AI extraction run directory for one single-applicant fixture."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RUNS_ROOT = ROOT / "visa-eval" / "runs"
PROMPT_TEMPLATE = ROOT / "visa-eval" / "eval" / "prompts" / "blind_single_case_prompt.md"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_")


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def safe_suffix(path: Path) -> str:
    return path.suffix if path.suffix else ""


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def make_symlink(source: Path, link: Path) -> None:
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(source)


def build_output_contract() -> str:
    return """# Output Contract

Write outputs only under this run directory's `generated/` directory.

Reference schemas:

- `rasens-autofill/data/schemas/case_data.schema.json`
- `rasens-autofill/data/schemas/review.schema.json`
- `rasens-autofill/data/schemas/input_documents.schema.json`

## generated/case_data.json

Create a single-applicant case object. Use the existing project shape where practical:

- `schema_version`
- `case`
- `application`
- `applicant`
- `passport`
- `residence_card`
- `immigration_history`
- `family`
- `education`
- `transcript_subjects`
- `employment_history`
- `qualifications`
- `employer`
- `proxy`
- `intermediary`
- `receiving_method`
- `supporting_documents`
- `assessments`
- `field_metadata`

If a value is not found in allowed documents, use an empty string, `null`, or an empty array/object as appropriate. Do not guess.

## generated/review.json

Include:

- `schema_version`
- `case_id`
- `expected_route`
- `missing_documents`
- `missing_items`
- `validation_errors`
- `findings`
- `assessments`

Use `needs_review` when human review is required.

## generated/run_notes.md

Briefly list:

- Documents read.
- Fields that were strongly supported.
- Fields that were missing or weakly supported.
- 技術・人文知識・国際業務 review concerns.

Do not include long verbatim personal data in notes.
"""


def build_agent_task(run_dir: Path, scenario: dict[str, Any]) -> str:
    template = PROMPT_TEMPLATE.read_text()
    return f"""# Agent Task

Run directory:

```text
{rel(run_dir)}
```

Case:

```json
{json.dumps(scenario, ensure_ascii=False, indent=2)}
```

{template}
"""


def blind_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    forbidden_keys = {
        "expected_case_data",
        "expected_application_data",
        "expected_review",
    }
    clean = {key: value for key, value in scenario.items() if key not in forbidden_keys}
    clean["input_documents"] = "input_documents.blind.json"
    clean["generated_dir"] = "generated"
    return clean


def prepare(fixture_dir: Path) -> Path:
    fixture_dir = fixture_dir.resolve()
    scenario_path = fixture_dir / "scenario.json"
    input_path = fixture_dir / "input" / "input_documents.json"
    if not scenario_path.exists():
        raise SystemExit(f"missing scenario: {scenario_path}")
    if not input_path.exists():
        raise SystemExit(f"missing input documents: {input_path}")

    scenario = blind_scenario(load_json(scenario_path))
    input_manifest = load_json(input_path)
    case_id = scenario["case_id"]
    run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{slug(case_id)}"
    run_dir = RUNS_ROOT / run_id
    documents_dir = run_dir / "documents"
    generated_dir = run_dir / "generated"
    documents_dir.mkdir(parents=True, exist_ok=False)
    generated_dir.mkdir(parents=True, exist_ok=True)

    blind_documents = []
    for index, doc in enumerate(input_manifest.get("documents", []), start=1):
        if not doc.get("use_as_input", True):
            continue
        source = ROOT / doc["path"]
        if not source.exists():
            raise SystemExit(f"missing source document: {source}")
        link_name = f"doc_{index:03d}{safe_suffix(source)}"
        link = documents_dir / link_name
        make_symlink(source, link)
        blind_doc = {
            "document_id": f"doc_{index:03d}",
            "document_role": doc.get("document_role", ""),
            "path": f"documents/{link_name}",
            "file_name": doc.get("file_name", source.name),
            "extension": doc.get("extension", source.suffix.lower().lstrip(".")),
            "use_as_input": True,
            "notes": doc.get("notes", ""),
        }
        for key in ("pdf_pages", "sheets"):
            if key in doc:
                blind_doc[key] = doc[key]
        blind_documents.append(blind_doc)

    blind_manifest = {
        "schema_version": input_manifest.get("schema_version", "0.1.0"),
        "case_id": input_manifest.get("case_id", case_id),
        "base_case_id": input_manifest.get("base_case_id", scenario.get("base_case_id")),
        "applicant_id": input_manifest.get("applicant_id", scenario.get("applicant_id")),
        "documents": blind_documents,
        "blind_run_policy": {
            "forbidden_globs": [
                "visa-eval/fixtures_single/**/expected/**",
                "**/*.golden.json",
                "visa-eval/runs/*/generated/**",
            ],
            "write_only": "generated/",
        },
    }

    write_json(run_dir / "scenario.json", scenario)
    write_json(run_dir / "input_documents.blind.json", blind_manifest)
    (run_dir / "output_contract.md").write_text(build_output_contract())
    (run_dir / "allowed_reference_paths.txt").write_text(
        "\n".join(
            [
                "rasens-autofill/data/schemas/case_data.schema.json",
                "rasens-autofill/data/schemas/review.schema.json",
                "rasens-autofill/data/schemas/input_documents.schema.json",
                "rasens-autofill/data/mappings/rasens_offer_mapping.json",
                "rasens-autofill/data/form_definitions/rasens_offer_fields.json",
                "rasens-autofill/scripts/build_application_data.py",
            ]
        )
        + "\n"
    )
    (run_dir / "AGENT_TASK.md").write_text(build_agent_task(run_dir, scenario))
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture_dir", type=Path, help="Path to visa-eval/fixtures_single/<case_id>/<applicant_id>")
    args = parser.parse_args()

    run_dir = prepare(args.fixture_dir)
    print(f"wrote blind run: {rel(run_dir)}")
    print(f"agent task: {rel(run_dir / 'AGENT_TASK.md')}")


if __name__ == "__main__":
    main()
