#!/usr/bin/env python3
"""Audit active verified golden fixtures without printing restricted values."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURES_ROOT = ROOT / "visa-eval" / "test_cases_from_raw"
FORM_DEFINITIONS_PATH = ROOT / "visa-app" / "backend" / "data" / "form_definitions" / "rasens_offer_fields.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))

from compare_with_golden import (  # noqa: E402
    _SKIP_KEYS_CASE_DATA,
    _case_data_manifest_stats,
    _flatten,
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_fixture_dirs(fixtures_root: Path) -> list[Path]:
    scenarios = sorted(fixtures_root.glob("*/*/scenario.json"))
    return [scenario.parent for scenario in scenarios]


def load_job_category_options() -> set[str]:
    definitions = read_json(FORM_DEFINITIONS_PATH)
    for field in definitions.get("fields", []):
        for control in field.get("controls", []):
            if control.get("field_name") != "item[205].selectData":
                continue
            return {
                option.get("text", "")
                for option in control.get("options", [])
                if option.get("value") != "1" and option.get("text")
            }
    raise RuntimeError("RASENS job category options were not found")


def audit_fixture(
    fixture_dir: Path,
    job_category_options: set[str],
) -> tuple[dict[str, int], list[str]]:
    expected_dir = fixture_dir / "expected_verified"
    golden_path = expected_dir / "case_data.golden.json"
    manifest_path = expected_dir / "golden_manifest.json"
    errors: list[str] = []

    if not golden_path.is_file():
        errors.append("expected_verified/case_data.golden.json is missing")
    if not manifest_path.is_file():
        errors.append("expected_verified/golden_manifest.json is missing")
    if errors:
        return {}, errors

    golden = read_json(golden_path)
    manifest = read_json(manifest_path)
    if not isinstance(golden, dict):
        return {}, ["case_data.golden.json must be an object"]
    if not isinstance(manifest, dict):
        return {}, ["golden_manifest.json must be an object"]

    job_category = golden.get("employment", {}).get("job_category_primary")
    if job_category and job_category not in job_category_options:
        errors.append("employment.job_category_primary is not a current RASENS option")

    exp_flat = _flatten(golden, skip_keys=_SKIP_KEYS_CASE_DATA)
    stats = _case_data_manifest_stats(exp_flat, manifest)
    status = manifest.get("status")
    if status not in {"reviewed", "locked"}:
        errors.append(f"manifest status must be reviewed or locked (actual={status!r})")
    if stats["needs_review_count"]:
        errors.append(f"needs_review={stats['needs_review_count']}")
    if stats["unclassified_count"]:
        errors.append(f"unclassified={stats['unclassified_count']}")
    if stats["manifest_unknown_path_count"]:
        errors.append(f"manifest_unknown_paths={stats['manifest_unknown_path_count']}")
    if not stats["scored_paths"]:
        errors.append("verified extraction fields are empty")

    old_golden = fixture_dir / "expected" / "case_data.golden.json"
    recorded_sha = manifest.get("source_golden_sha256")
    if old_golden.exists():
        if not recorded_sha:
            errors.append("old expected exists but source_golden_sha256 is missing")
        elif sha256(old_golden) != recorded_sha:
            errors.append("old expected sha256 does not match manifest")
    elif recorded_sha:
        errors.append("source_golden_sha256 is set but old expected is missing")

    output_manifest = fixture_dir / "output" / "output_manifest.json"
    if not output_manifest.is_file():
        errors.append("output/output_manifest.json is missing")
    else:
        output_documents = read_json(output_manifest).get("outputs", [])
        if any(document.get("use_as_input", False) for document in output_documents):
            errors.append("output manifest contains use_as_input=true")

    input_manifest = fixture_dir / "input" / "document_manifest.json"
    if not input_manifest.is_file():
        errors.append("input/document_manifest.json is missing")
    else:
        input_root = (fixture_dir / "input").resolve()
        for document in read_json(input_manifest).get("documents", []):
            if not document.get("use_as_input", True):
                continue
            document_path = Path(str(document.get("path", "")))
            if document_path.is_absolute():
                resolved = document_path.resolve()
            elif (ROOT / document_path).exists():
                resolved = (ROOT / document_path).resolve()
            else:
                resolved = (fixture_dir / document_path).resolve()
            if not resolved.is_relative_to(input_root):
                errors.append("input manifest references a use_as_input file outside fixture input/")
                break

    counts = {
        "field_rules": len(manifest.get("field_rules", {})),
        "scored": len(stats["scored_paths"]),
        "application_only": stats["application_only_count"],
        "excluded": stats["excluded_count"],
        "needs_review": stats["needs_review_count"],
        "unclassified": stats["unclassified_count"],
        "manifest_unknown": stats["manifest_unknown_path_count"],
        "old_expected": int(old_golden.exists()),
    }
    return counts, errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures-root", type=Path, default=DEFAULT_FIXTURES_ROOT)
    parser.add_argument("--expected-fixtures", type=int)
    parser.add_argument("--expected-scored", type=int)
    parser.add_argument("--expected-old-expected", type=int)
    args = parser.parse_args()

    fixture_dirs = discover_fixture_dirs(args.fixtures_root.resolve())
    job_category_options = load_job_category_options()
    totals = {
        "field_rules": 0,
        "scored": 0,
        "application_only": 0,
        "excluded": 0,
        "needs_review": 0,
        "unclassified": 0,
        "manifest_unknown": 0,
        "old_expected": 0,
    }
    errors: list[str] = []

    for index, fixture_dir in enumerate(fixture_dirs, start=1):
        counts, fixture_errors = audit_fixture(fixture_dir, job_category_options)
        for key in totals:
            totals[key] += counts.get(key, 0)
        for error in fixture_errors:
            errors.append(f"F{index}: {error}")

    if args.expected_fixtures is not None and len(fixture_dirs) != args.expected_fixtures:
        errors.append(
            f"fixture count={len(fixture_dirs)} (expected={args.expected_fixtures})"
        )
    if args.expected_scored is not None and totals["scored"] != args.expected_scored:
        errors.append(
            f"scored fields={totals['scored']} (expected={args.expected_scored})"
        )
    if (
        args.expected_old_expected is not None
        and totals["old_expected"] != args.expected_old_expected
    ):
        errors.append(
            f"old expected count={totals['old_expected']} "
            f"(expected={args.expected_old_expected})"
        )

    print(f"fixtures={len(fixture_dirs)}")
    for key, value in totals.items():
        print(f"{key}={value}")
    if errors:
        print("audit=NG")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)
    print("audit=OK")


if __name__ == "__main__":
    main()
