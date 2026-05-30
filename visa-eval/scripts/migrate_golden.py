#!/usr/bin/env python3
"""Migrate eval case_data golden files to canonical v2."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

REMOVED_KEYS = {
    "source_refs",
    "field_metadata",
    "golden_status",
    "supporting_documents",
    "assessments",
    "raw_intake_pairs",
}

TOP_LEVEL_SOURCE_KEYS = {
    "application",
    "passport",
    "immigration_history",
    "family",
    "education",
    "employment_history",
    "qualifications",
    "residence_card",
    "transcript_subjects",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"", "unknown", "n/a", "na", "null"}
    if isinstance(value, list):
        return not value
    if isinstance(value, dict):
        return not value
    return False


def ensure_dict(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        value = {}
        data[key] = value
    return value


def set_if_present(target: dict[str, Any], key: str, value: Any) -> None:
    if key not in target and not is_empty(value):
        target[key] = value


def merge_dict(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if key in REMOVED_KEYS:
            continue
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            merge_dict(target[key], value)
        else:
            set_if_present(target, key, value)


def strip_removed_keys(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if key in REMOVED_KEYS:
                continue
            cleaned_item = strip_removed_keys(item)
            if not is_empty(cleaned_item):
                cleaned[key] = cleaned_item
        return cleaned
    if isinstance(value, list):
        return [item for item in (strip_removed_keys(item) for item in value) if not is_empty(item)]
    return value


def normalize_education(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        cleaned = strip_removed_keys(item)
        if "major" in cleaned and "major_field" not in cleaned:
            cleaned["major_field"] = cleaned.pop("major")
        cleaned.pop("id", None)
        if cleaned:
            normalized.append(cleaned)
    return normalized


def move_application(data: dict[str, Any]) -> None:
    application = data.pop("application", {})
    if not isinstance(application, dict):
        return

    entry_plan = ensure_dict(data, "entry_plan")
    employment = ensure_dict(data, "employment")
    applicant = ensure_dict(data, "applicant")
    family = ensure_dict(applicant, "family")

    mapping = {
        "desired_status_label": ("entry_plan", "main_activity_category"),
        "purpose_of_entry": ("entry_plan", "purpose_of_entry"),
        "planned_entry_date": ("entry_plan", "planned_entry_date"),
        "planned_port": ("entry_plan", "planned_port"),
        "planned_port_other": ("entry_plan", "planned_port_other"),
        "planned_period_years": ("entry_plan", "planned_period_years"),
        "planned_period_months": ("entry_plan", "planned_period_months"),
        "visa_application_location": ("entry_plan", "visa_application_location"),
        "activity_details": ("employment", "activity_details"),
        "activity_details_structured": ("employment", "activity_details_structured"),
    }
    targets = {"entry_plan": entry_plan, "employment": employment}
    for source_key, (target_name, target_key) in mapping.items():
        set_if_present(targets[target_name], target_key, application.get(source_key))

    if "has_accompanying" in application:
        set_if_present(family, "has_accompanying_members", application.get("has_accompanying"))


def migrate_case_data(data: dict[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(data)
    migrated["schema_version"] = "2.0"

    applicant = ensure_dict(migrated, "applicant")
    move_application(migrated)

    passport = migrated.pop("passport", {})
    if isinstance(passport, dict):
        merge_dict(ensure_dict(applicant, "passport"), passport)

    immigration_history = migrated.pop("immigration_history", {})
    if isinstance(immigration_history, dict):
        merge_dict(ensure_dict(applicant, "immigration_history"), immigration_history)

    family = migrated.pop("family", {})
    if isinstance(family, dict):
        merge_dict(ensure_dict(applicant, "family"), family)

    education = normalize_education(migrated.pop("education", []))
    if education and "education" not in applicant:
        applicant["education"] = education

    employment_history = migrated.pop("employment_history", [])
    if isinstance(employment_history, list) and employment_history and "employment_history" not in applicant:
        applicant["employment_history"] = strip_removed_keys(employment_history)

    qualifications = migrated.pop("qualifications", {})
    if isinstance(qualifications, dict):
        merge_dict(ensure_dict(applicant, "qualifications"), qualifications)

    residence_card = migrated.pop("residence_card", {})
    if isinstance(residence_card, dict) and not is_empty(strip_removed_keys(residence_card)):
        merge_dict(ensure_dict(applicant, "residence_card"), residence_card)

    employer = migrated.get("employer")
    if isinstance(employer, dict):
        employer.pop("source_refs", None)
        if "category" in employer and "industry_primary" not in employer:
            set_if_present(employer, "industry_primary", employer.pop("category"))
        else:
            employer.pop("category", None)

    for key in REMOVED_KEYS | TOP_LEVEL_SOURCE_KEYS:
        migrated.pop(key, None)

    return strip_removed_keys(migrated)


def legacy_keys(data: dict[str, Any]) -> list[str]:
    keys = sorted(key for key in TOP_LEVEL_SOURCE_KEYS if key in data)
    keys.extend(sorted(key for key in REMOVED_KEYS if key in data))
    return keys


def migrate_fixture(fixture_dir: Path, write: bool) -> None:
    path = fixture_dir / "expected" / "case_data.golden.json"
    original = read_json(path)
    migrated = migrate_case_data(original)
    before_keys = legacy_keys(original)
    after_keys = legacy_keys(migrated)

    print(f"{fixture_dir}:")
    print(f"  before legacy keys: {', '.join(before_keys) or '-'}")
    print(f"  after legacy keys: {', '.join(after_keys) or '-'}")

    if write:
        write_json(path, migrated)
        print("  wrote expected/case_data.golden.json")
    else:
        print("  dry-run only")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture_dirs", nargs="+", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    for fixture_dir in args.fixture_dirs:
        migrate_fixture(fixture_dir, args.write)


if __name__ == "__main__":
    main()
