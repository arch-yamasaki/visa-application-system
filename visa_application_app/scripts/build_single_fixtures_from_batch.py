#!/usr/bin/env python3
"""Build single-applicant fixtures from batch golden case_data files."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from build_application_data import build_rows


ROOT = Path(__file__).resolve().parents[1]
TEST_ROOT = ROOT / "data" / "test_cases"
FIXTURES_ROOT = TEST_ROOT / "fixtures"
SINGLE_ROOT = TEST_ROOT / "fixtures_single"
CATALOG = TEST_ROOT / "catalog.json"
MAPPING = ROOT / "data" / "mappings" / "rasens_offer_mapping.json"


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def case_documents(catalog: dict[str, Any], case_id: str) -> list[dict[str, Any]]:
    return [doc for doc in catalog["documents"] if doc["case_id"] == case_id]


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def pick_documents(all_docs: list[dict[str, Any]], applicant_name: str) -> list[dict[str, Any]]:
    docs = []
    normalized = normalize_name(applicant_name)
    for doc in all_docs:
        if doc["document_role"] in {"intake_spreadsheet", "company_documents", "submitted_application_bundle", "not_attached_reference", "email_context"}:
            docs.append(doc)
            continue
        if normalized and normalize_name(Path(doc["file_name"]).stem).find(normalized) >= 0:
            docs.append(doc)
            continue
        if doc["document_role"] == "employment_terms" and normalized and normalize_name(doc["file_name"]).find(normalized) >= 0:
            docs.append(doc)
    # If no applicant PDF matched, include all applicant bundles as fallback for transparency.
    if not any(d["document_role"] == "applicant_document_bundle" for d in docs):
        docs.extend([doc for doc in all_docs if doc["document_role"] == "applicant_document_bundle"])
    # Deduplicate by path.
    unique = {}
    for doc in docs:
        unique[doc["path"]] = doc
    return list(unique.values())


def single_case_from_batch(batch: dict[str, Any], applicant: dict[str, Any], docs: list[dict[str, Any]]) -> dict[str, Any]:
    single = {
        "schema_version": batch["schema_version"],
        "golden_status": "restricted_single_applicant_fixture",
        "case": {
            "case_id": f"{batch['case']['case_id']}__{applicant['id']}",
            "display_name": f"{batch['case']['display_name']} / {applicant['applicant']['name_roman']}",
            "application_type": batch["case"]["application_type"],
            "target_status": batch["case"]["target_status"],
            "workflow_state": "golden_ready",
            "intake_channel": batch["case"]["intake_channel"],
            "source_organization": batch["case"]["source_organization"],
            "routed_to_human_reason": [],
        },
        "application": deepcopy(batch["application"]),
        "applicant": deepcopy(applicant["applicant"]),
        "passport": deepcopy(applicant["passport"]),
        "residence_card": {},
        "immigration_history": deepcopy(applicant["immigration_history"]),
        "family": deepcopy(applicant["family"]),
        "education": deepcopy(applicant["education"]),
        "transcript_subjects": [],
        "employment_history": deepcopy(applicant["employment_history"]),
        "qualifications": deepcopy(applicant["qualifications"]),
        "employer": deepcopy(batch["employer"]),
        "proxy": {},
        "intermediary": {},
        "receiving_method": {},
        "supporting_documents": [
            {
                "document_id": f"doc_{index + 1:03d}",
                "document_type": doc["document_role"],
                "path": doc["path"],
                "file_name": doc["file_name"],
                "status": "received" if doc["use_as_input"] else "reference_only",
                "use_as_input": doc["use_as_input"],
                "contains_personal_information": doc["contains_personal_information"],
                "source_channel": "download",
            }
            for index, doc in enumerate(docs)
        ],
        "assessments": deepcopy(batch["assessments"]),
        "field_metadata": {},
    }
    return single


def review_from_case(case_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "0.1.0",
        "case_id": case_data["case"]["case_id"],
        "golden_status": case_data["golden_status"],
        "expected_route": "needs_review",
        "expected_workflow_state": case_data["case"]["workflow_state"],
        "missing_documents": [],
        "missing_items": [
            {"path": "residence_card", "reason": "not_present_in_batch_fixture"},
        ],
        "validation_errors": [],
        "findings": [
            {
                "code": "single_fixture_from_batch",
                "severity": "low",
                "message": "Derived from batch fixture for single-applicant form generation.",
            }
        ],
        "assessments": deepcopy(case_data["assessments"]),
    }


def main() -> None:
    catalog = load_json(CATALOG)
    mapping = load_json(MAPPING)
    SINGLE_ROOT.mkdir(parents=True, exist_ok=True)

    for batch_case_path in FIXTURES_ROOT.glob("*/expected/case_data.golden.json"):
        batch = load_json(batch_case_path)
        case_id = batch["case"]["case_id"]
        all_docs = case_documents(catalog, case_id)
        for applicant in batch["applicants"]:
            docs = pick_documents(all_docs, applicant["applicant"]["name_roman"])
            single = single_case_from_batch(batch, applicant, docs)
            fixture_dir = SINGLE_ROOT / case_id / applicant["id"]
            input_dir = fixture_dir / "input"
            expected_dir = fixture_dir / "expected"
            generated_dir = fixture_dir / "generated"
            input_dir.mkdir(parents=True, exist_ok=True)
            expected_dir.mkdir(parents=True, exist_ok=True)
            generated_dir.mkdir(parents=True, exist_ok=True)

            (fixture_dir / "scenario.json").write_text(
                json.dumps(
                    {
                        "schema_version": "0.1.0",
                        "case_id": single["case"]["case_id"],
                        "base_case_id": case_id,
                        "applicant_id": applicant["id"],
                        "applicant_name": applicant["applicant"]["name_roman"],
                        "target_status": single["case"]["target_status"],
                        "application_type": single["case"]["application_type"],
                        "primary_checks": [
                            "document_completeness",
                            "case_data_generation",
                            "form_mapping",
                            "gijinkoku_fit",
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            )

            (input_dir / "input_documents.json").write_text(
                json.dumps(
                    {
                        "schema_version": "0.1.0",
                        "case_id": single["case"]["case_id"],
                        "base_case_id": case_id,
                        "applicant_id": applicant["id"],
                        "documents": docs,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            )

            (expected_dir / "case_data.golden.json").write_text(json.dumps(single, ensure_ascii=False, indent=2) + "\n")
            (expected_dir / "review.golden.json").write_text(json.dumps(review_from_case(single), ensure_ascii=False, indent=2) + "\n")
            (expected_dir / "application_data.golden.json").write_text(
                json.dumps(
                    build_rows(
                        {
                            "case": single["case"],
                            "application": single["application"],
                            "applicant": single["applicant"],
                            "passport": single["passport"],
                            "residence_card": single["residence_card"],
                            "immigration_history": single["immigration_history"],
                            "family": single["family"],
                            "education": single["education"],
                            "employment_history": single["employment_history"],
                            "qualifications": single["qualifications"],
                            "employer": single["employer"],
                            "supporting_documents": single["supporting_documents"],
                            "assessments": single["assessments"],
                        },
                        mapping,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            )
            (generated_dir / ".gitkeep").write_text("")
            print(f"wrote {fixture_dir}")


if __name__ == "__main__":
    main()
