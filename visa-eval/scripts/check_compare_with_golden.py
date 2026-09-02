#!/usr/bin/env python3
"""Smoke checks for compare_with_golden.py without requiring pytest."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from compare_with_golden import run_comparison


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def assign_path(data: dict, dot_path: str, value: object) -> None:
    current = data
    parts = dot_path.split(".")
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def run_case_data_comparison(tmp_path: Path, path: str, expected_value: object, generated_value: object) -> dict:
    generated_dir = tmp_path / "generated"
    expected_dir = tmp_path / "expected"

    generated_case_data: dict[str, Any] = {}
    expected_case_data: dict[str, Any] = {}
    assign_path(generated_case_data, path, generated_value)
    assign_path(expected_case_data, path, expected_value)

    write_json(generated_dir / "case_data.json", generated_case_data)
    write_json(expected_dir / "case_data.golden.json", expected_case_data)

    return run_comparison(generated_dir, expected_dir, ["case_data"])[0]


def check_generated_case_data_must_not_use_golden_fallback(tmp_path: Path) -> None:
    generated_dir = tmp_path / "generated"
    expected_dir = tmp_path / "expected"

    write_json(generated_dir / "case_data.golden.json", {"applicant": {"name_roman": "SAMPLE APPLICANT"}})
    write_json(expected_dir / "case_data.golden.json", {"applicant": {"name_roman": "SAMPLE APPLICANT"}})

    results = run_comparison(generated_dir, expected_dir, ["case_data"])
    assert results == [
        {
            "file": "case_data",
            "status": "MISSING",
            "reason": "generated file not found: case_data.json",
        }
    ]


def check_application_data_requires_generated_case_data_json(tmp_path: Path) -> None:
    generated_dir = tmp_path / "generated"
    expected_dir = tmp_path / "expected"

    write_json(generated_dir / "case_data.golden.json", {"applicant": {"name_roman": "SAMPLE APPLICANT"}})
    write_json(expected_dir / "case_data.golden.json", {"applicant": {"name_roman": "SAMPLE APPLICANT"}})

    results = run_comparison(generated_dir, expected_dir, ["application_data"])
    assert results == [
        {
            "file": "application_data",
            "status": "MISSING",
            "reason": "generated case_data.json not found",
        }
    ]


def check_case_data_compares_generated_json_to_expected_golden(tmp_path: Path) -> None:
    generated_dir = tmp_path / "generated"
    expected_dir = tmp_path / "expected"

    case_data = {"applicant": {"name_roman": "SAMPLE APPLICANT"}}
    write_json(generated_dir / "case_data.json", case_data)
    write_json(expected_dir / "case_data.golden.json", case_data)

    results = run_comparison(generated_dir, expected_dir, ["case_data"])

    assert results[0]["file"] == "case_data"
    assert results[0]["status"] == "MATCH"
    assert results[0]["golden_total"] == 1
    assert results[0]["match_count"] == 1


def check_case_data_normalizes_equivalent_values(tmp_path: Path) -> None:
    cases = [
        ("applicant.name_roman", "SAMPLE  APPLICANT", "ＳＡＭＰＬＥ　ＡＰＰＬＩＣＡＮＴ"),
        ("applicant.family.has_accompanying_members", "No", "無"),
        ("applicant.family.has_accompanying_members", "無 No", "false"),
        ("applicant.family.has_accompanying_members", "有 Yes", True),
        ("applicant.family.has_accompanying_members", "No", False),
        ("applicant.nationality_region", "NEP", "Nepal"),
        ("applicant.nationality_region", "NPL", "NEPAL"),
        ("applicant.nationality_region", "NEPAL", "Nepal"),
        ("applicant.nationality_region", "NEPAL", "ネパール Nepal"),
        ("applicant.nationality_region", "ネパール", "Nepal"),
        ("applicant.nationality_region", "ベトナム Viet Nam", "Vietnamese"),
        ("applicant.education.0.country_type", "外国 Foreign country", "Foreign country"),
        ("applicant.family.japan_relatives_or_cohabitants.0.nationality_region", "日本 Japan", "Japanese"),
        ("applicant.family.japan_relatives_or_cohabitants.0.relationship", "妻 Wife", "wife"),
        ("applicant.family.japan_relatives_or_cohabitants.0.relationship", "妻 Wife", "wife 妻"),
        ("applicant.family.japan_relatives_or_cohabitants.0.relationship", "夫 Husband", "HUSBAND"),
        ("applicant.family.japan_relatives_or_cohabitants.0.relationship", "husband 夫", "夫 Husband"),
        ("applicant.marital_status", "Single", "single"),
        ("applicant.marital_status", "無 Single", "unmarried"),
        ("applicant.sex", "男 Male", "M"),
        ("applicant.sex", "female", "Ｆ"),
        ("employment.monthly_salary", "1,234,567円", "1234567"),
        ("employment.monthly_salary", "１，２３４，５６７円", "1234567"),
        ("applicant.birth_date", "2024/01/02", "2024-01-02"),
        ("applicant.birth_date", "２０２４/０１/０２", "2024-01-02"),
        ("employment.joining_date", "2024/1/2", "2024-01-02"),
        ("employment.joining_date", "２０２４年０１月０２日", "20240102"),
    ]

    for index, (path, expected_value, generated_value) in enumerate(cases):
        result = run_case_data_comparison(tmp_path / f"equivalent_{index}", path, expected_value, generated_value)
        assert result["file"] == "case_data"
        assert result["status"] == "MATCH"
        assert result["golden_total"] == 1
        assert result["match_count"] == 1
        assert result["mismatch_count"] == 0
        assert result["only_expected_count"] == 0
        assert result["only_generated_count"] == 0


def check_case_data_does_not_normalize_different_values(tmp_path: Path) -> None:
    cases = [
        ("applicant.marital_status", "Married", "Single"),
        ("applicant.nationality_region", "Nepal", "India"),
        ("applicant.nationality_region", "Japan", "China"),
        ("applicant.nationality_region", "Nepal", "I worked in Nepal before"),
        ("applicant.nationality_region", "China", "中国地方の拠点"),
        ("applicant.birth_date", "2024-01", "2024-01-02"),
        ("employment.joining_date", "2024-01", "2024-01"),
        ("employment.joining_date", "2024-01", "2024-01-02"),
        ("employment.joining_date", "2024-13-01", "2024-13-01"),
        ("employer.address", "東京都渋谷区千駄ヶ谷四丁目25番2号", "東京都渋谷区千駄ヶ谷四丁目"),
        ("employer.corporate_number", "8011001039242", "011001039242"),
        ("employment.job_category_primary", "管理業務（経営者を除く） Management work (excluding executives)", "技術・人文知識・国際業務"),
        ("employment.has_position", False, True),
    ]

    for index, (path, expected_value, generated_value) in enumerate(cases):
        result = run_case_data_comparison(tmp_path / f"different_{index}", path, expected_value, generated_value)
        assert result["file"] == "case_data"
        assert result["status"] == "MISMATCH"
        assert result["golden_total"] == 1
        assert result["match_count"] == 0
        assert result["mismatch_count"] == 1
        assert result["only_expected_count"] == 0
        assert result["only_generated_count"] == 0


def check_case_data_manifest_scopes_scoring_paths(tmp_path: Path) -> None:
    generated_dir = tmp_path / "generated"
    expected_dir = tmp_path / "expected"

    write_json(
        generated_dir / "case_data.json",
        {
            "applicant": {
                "name_roman": "SAMPLE APPLICANT",
                "education": [{"school_name": "wrong"}],
                "extra_generated": "extra",
            },
            "proxy": {},
            "employment": {},
        },
    )
    write_json(
        expected_dir / "case_data.golden.json",
        {
            "applicant": {
                "name_roman": "SAMPLE APPLICANT",
                "education": [{"school_name": "expected"}],
            },
            "proxy": {"name": "expected proxy"},
            "employment": {"activity_details": "expected activity"},
            "entry_plan": {"planned_port": "unclassified"},
        },
    )
    write_json(
        expected_dir / "golden_manifest.json",
        {
            "field_rules": {
                "applicant.name_roman": {"scope": "extraction", "verification": "verified"},
                "applicant.education.0.school_name": {"scope": "application_only", "verification": "verified"},
                "proxy.name": {"scope": "application_only", "verification": "verified"},
                "employment.activity_details": {"scope": "excluded", "verification": "verified"},
            }
        },
    )

    results = run_comparison(generated_dir, expected_dir, ["case_data"])

    assert results[0]["file"] == "case_data"
    assert results[0]["status"] == "MISMATCH"
    assert results[0]["comparison_mode"] == "manifest_scoped"
    assert results[0]["golden_total"] == 1
    assert results[0]["match_count"] == 1
    assert results[0]["mismatch_count"] == 0
    assert results[0]["only_expected_count"] == 0
    assert results[0]["only_generated_count"] == 1
    assert results[0]["only_generated"] == ["applicant.extra_generated"]
    assert results[0]["application_only_count"] == 2
    assert results[0]["excluded_count"] == 1
    assert results[0]["unclassified_count"] == 1


def check_case_data_manifest_unknown_paths_fail_report_without_scoring(tmp_path: Path) -> None:
    generated_dir = tmp_path / "generated"
    expected_dir = tmp_path / "expected"

    write_json(generated_dir / "case_data.json", {"applicant": {"name_roman": "SAMPLE APPLICANT"}})
    write_json(expected_dir / "case_data.golden.json", {"applicant": {"name_roman": "SAMPLE APPLICANT"}})
    write_json(
        expected_dir / "golden_manifest.json",
        {
            "field_rules": {
                "applicant.name_roman": {"scope": "extraction", "verification": "verified"},
                "applicant.typo": {"scope": "extraction", "verification": "verified"},
            }
        },
    )

    results = run_comparison(generated_dir, expected_dir, ["case_data"])

    assert results[0]["status"] == "CONFIG_ERROR"
    assert results[0]["golden_total"] == 1
    assert results[0]["match_count"] == 1
    assert results[0]["manifest_unknown_path_count"] == 1
    assert results[0]["manifest_unknown_paths"] == ["applicant.typo"]
    assert results[0]["config_errors"] == [
        "golden_manifest contains path(s) not present in case_data.golden.json"
    ]


def check_case_data_manifest_zero_scored_fields_is_config_error(tmp_path: Path) -> None:
    generated_dir = tmp_path / "generated"
    expected_dir = tmp_path / "expected"

    write_json(generated_dir / "case_data.json", {"applicant": {"name_roman": "SAMPLE APPLICANT"}})
    write_json(expected_dir / "case_data.golden.json", {"applicant": {"name_roman": "SAMPLE APPLICANT"}})
    write_json(
        expected_dir / "golden_manifest.json",
        {
            "field_rules": {
                "applicant.name_roman": {"scope": "extraction", "verification": "needs_review"},
            }
        },
    )

    results = run_comparison(generated_dir, expected_dir, ["case_data"])

    assert results[0]["status"] == "CONFIG_ERROR"
    assert results[0]["golden_total"] == 0
    assert results[0]["needs_review_count"] == 1
    assert results[0]["config_errors"] == [
        "golden_manifest has no verified extraction fields"
    ]


def main() -> None:
    checks = [
        check_generated_case_data_must_not_use_golden_fallback,
        check_application_data_requires_generated_case_data_json,
        check_case_data_compares_generated_json_to_expected_golden,
        check_case_data_normalizes_equivalent_values,
        check_case_data_does_not_normalize_different_values,
        check_case_data_manifest_scopes_scoring_paths,
        check_case_data_manifest_unknown_paths_fail_report_without_scoring,
        check_case_data_manifest_zero_scored_fields_is_config_error,
    ]
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for check in checks:
            check(tmp_path / check.__name__)
    print(f"compare_with_golden checks passed: {len(checks)}")


if __name__ == "__main__":
    main()
