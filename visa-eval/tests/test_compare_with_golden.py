import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "visa-eval/scripts"))

from compare_with_golden import run_comparison  # noqa: E402


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_generated_case_data_must_not_use_golden_fallback(tmp_path: Path) -> None:
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


def test_application_data_requires_generated_case_data_json(tmp_path: Path) -> None:
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


def test_case_data_compares_generated_json_to_expected_golden(tmp_path: Path) -> None:
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
