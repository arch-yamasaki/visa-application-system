#!/usr/bin/env python3
"""Build Chrome-extension autofill rows from canonical case data."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def get_path(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if isinstance(current, list):
            if not part.isdigit():
                return None
            index = int(part)
            if index >= len(current):
                return None
            current = current[index]
        elif isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
        else:
            return None
    return current


def date_digits(value: Any, digits: int) -> str:
    raw = str(value or "")
    found = re.findall(r"\d+", raw)
    joined = "".join(found)
    return joined[:digits]


def transform_value(value: Any, transform: str) -> str:
    if value is None:
        return ""
    raw_value = str(value).strip()
    if raw_value.lower() in {"unknown", "not_applicable", "n/a", "na"}:
        return ""
    if transform == "date_yyyymmdd":
        return date_digits(value, 8)
    if transform == "date_yyyymm":
        return date_digits(value, 6)
    if transform == "boolean_yes_no":
        return "有 Yes" if bool(value) else "無 No"
    if transform == "marital_yes_no":
        return "有 Married" if value == "married" else "無 Single"
    if transform == "sex_ja":
        return {"male": "男 Male", "female": "女 Female"}.get(str(value), str(value))
    return str(value)


def visible(case_data: dict[str, Any], item: dict[str, Any]) -> bool:
    for condition in item.get("visible_when", []):
        actual = get_path(case_data, condition["path"])
        operator = condition.get("operator", "==")
        expected = condition.get("value")
        if operator == "==" and actual != expected:
            return False
        if operator == "!=" and actual == expected:
            return False
    return True


def build_rows(case_data: dict[str, Any], mapping_data: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in mapping_data.get("mappings", []):
        if not visible(case_data, item):
            continue
        value = get_path(case_data, item["value_path"])
        fill_value = transform_value(value, item.get("transform", ""))
        if fill_value == "":
            continue
        rows.append(
            {
                "section": item.get("section", ""),
                "no": item.get("form_item_no", ""),
                "label": item.get("label", item["canonical_id"]),
                "field_name": item.get("field_name", ""),
                "field_id": item.get("field_id", ""),
                "input_type": item.get("input_type", "text"),
                "display_value": fill_value,
                "fill_value": fill_value,
                "source_page": "case_data",
                "confidence": "demo" if case_data.get("case", {}).get("case_id", "").startswith("demo-") else "generated",
                "canonical_id": item["canonical_id"],
                "notes": "generated from canonical case_data",
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_data", type=Path)
    parser.add_argument("mapping", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    case_data = json.loads(args.case_data.read_text())
    mapping_data = json.loads(args.mapping.read_text())
    rows = build_rows(case_data, mapping_data)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
