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

    write_json(generated_dir / "case_data.golden.json", {"applicant": {"name_roman": "AMIT TAMANG"}})
    write_json(expected_dir / "case_data.golden.json", {"applicant": {"name_roman": "AMIT TAMANG"}})

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

    write_json(generated_dir / "case_data.golden.json", {"applicant": {"name_roman": "AMIT TAMANG"}})
    write_json(expected_dir / "case_data.golden.json", {"applicant": {"name_roman": "AMIT TAMANG"}})

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

    case_data = {"applicant": {"name_roman": "AMIT TAMANG"}}
    write_json(generated_dir / "case_data.json", case_data)
    write_json(expected_dir / "case_data.golden.json", case_data)

    results = run_comparison(generated_dir, expected_dir, ["case_data"])

    assert results[0]["file"] == "case_data"
    assert results[0]["status"] == "MATCH"
    assert results[0]["golden_total"] == 1
    assert results[0]["match_count"] == 1


def check_case_data_normalizes_equivalent_values(tmp_path: Path) -> None:
    cases = [
        ("applicant.family.has_accompanying_members", "No", "無"),
        ("applicant.family.has_accompanying_members", "No", False),
        ("applicant.nationality_region", "NEPAL", "Nepal"),
        ("applicant.nationality_region", "NEPAL", "ネパール Nepal"),
        ("applicant.marital_status", "Single", "single"),
        ("employment.monthly_salary", "1,234,567円", "1234567"),
        ("applicant.birth_date", "2024/01/02", "2024-01-02"),
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


def main() -> None:
    checks = [
        check_generated_case_data_must_not_use_golden_fallback,
        check_application_data_requires_generated_case_data_json,
        check_case_data_compares_generated_json_to_expected_golden,
        check_case_data_normalizes_equivalent_values,
        check_case_data_does_not_normalize_different_values,
    ]
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for check in checks:
            check(tmp_path / check.__name__)
    print(f"compare_with_golden checks passed: {len(checks)}")


if __name__ == "__main__":
    main()
