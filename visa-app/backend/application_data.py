"""Generate RASENS application-data rows from canonical case_data."""

from __future__ import annotations

import re
import os
import json
from pathlib import Path
from typing import Any


EMPTY_STRINGS = {"unknown", "not_applicable", "n/a", "na"}


def get_path(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if isinstance(current, list):
            index = int(part)
            current = current[index]
        else:
            current = current[part]
    return current


def has_path(data: dict[str, Any], path: str) -> bool:
    try:
        get_path(data, path)
    except (KeyError, IndexError, ValueError, TypeError):
        return False
    return True


def date_digits(value: Any, digits: int) -> str:
    return "".join(re.findall(r"\d+", str(value)))[:digits]


def is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        stripped = value.strip()
        return not stripped or stripped.lower() in EMPTY_STRINGS
    return False


def transform_value(value: Any, transform: str = "") -> str:
    if is_empty_value(value):
        return ""
    if transform == "date_yyyymmdd":
        return date_digits(value, 8)
    if transform == "date_yyyymm":
        return date_digits(value, 6)
    if transform == "boolean_yes_no":
        normalized = value.lower() if isinstance(value, str) else value
        return "有 Yes" if normalized in {True, "true", "yes", "有", "あり", 1, "1"} else "無 No"
    if transform == "marital_yes_no":
        return "有 Married" if value == "married" else "無 Single"
    if transform == "sex_ja":
        return {"male": "男 Male", "female": "女 Female"}.get(str(value), str(value))
    return str(value).strip()


def visible(case_data: dict[str, Any], mapping_item: dict[str, Any]) -> bool:
    for condition in mapping_item.get("visible_when", []):
        if not has_path(case_data, condition["path"]):
            return False
        actual = get_path(case_data, condition["path"])
        expected = condition.get("value")
        operator = condition.get("operator", "==")
        if operator == "==" and actual != expected:
            return False
        if operator == "!=" and actual == expected:
            return False
    return True


BACKEND_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = BACKEND_DIR.parents[1]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def default_mapping_path() -> Path:
    env_path = os.environ.get("RASENS_MAPPING_PATH")
    if env_path:
        return Path(env_path)
    workspace_path = WORKSPACE_DIR / "rasens-autofill/data/mappings/rasens_offer_mapping_v2.json"
    if workspace_path.exists():
        return workspace_path
    return BACKEND_DIR / "data/mappings/rasens_offer_mapping_v2.json"


def default_form_definitions_path() -> Path | None:
    env_path = os.environ.get("RASENS_FORM_DEFINITIONS_PATH")
    if env_path:
        return Path(env_path)
    workspace_path = WORKSPACE_DIR / "rasens-autofill/data/form_definitions/rasens_offer_fields.json"
    if workspace_path.exists():
        return workspace_path
    return None


def load_default_mapping() -> dict[str, Any]:
    return load_json(default_mapping_path())


def load_default_form_definitions() -> dict[str, Any]:
    path = default_form_definitions_path()
    if path is None:
        return {}
    return load_json(path)


def _field_controls(
    form_definitions: dict[str, Any],
    mapping: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    controls: dict[tuple[str, str], dict[str, Any]] = {}
    fields = form_definitions.get("fields", [])
    for index, field in enumerate(fields, start=1):
        for control in field.get("controls", []):
            key = (control.get("field_id", ""), control.get("field_name", ""))
            controls[key] = {
                "section": field.get("section", ""),
                "form_order": index,
                "display_no": field.get("no", ""),
                "label": field.get("label", ""),
                "required": field.get("required", False),
                "input_type": control.get("input_type", ""),
            }
    if fields:
        return controls

    for index, item in enumerate(mapping.get("mappings", []), start=1):
        key = (item.get("field_id", ""), item.get("field_name", ""))
        controls[key] = {
            "section": item.get("section", ""),
            "form_order": item.get("form_order", index),
            "display_no": item.get("display_no") or item.get("form_item_no", ""),
            "label": item.get("label", item.get("canonical_id", "")),
            "required": item.get("required", False),
            "input_type": item.get("input_type", ""),
        }
    return controls


def _field_info(
    mapping_item: dict[str, Any],
    controls: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    field_id = mapping_item.get("field_id", "")
    field_name = mapping_item.get("field_name", "")
    info = controls.get((field_id, field_name))
    if info is None:
        raise ValueError(f"mapping target not found: {field_id or field_name}")
    if mapping_item.get("input_type") and mapping_item["input_type"] != info["input_type"]:
        raise ValueError(f"input_type mismatch: {mapping_item.get('canonical_id')}")
    return info


def build_rows(
    case_data: dict[str, Any],
    mapping: dict[str, Any],
    form_definitions: dict[str, Any],
) -> list[dict[str, Any]]:
    controls = _field_controls(form_definitions, mapping)
    rows: list[dict[str, Any]] = []

    for item in mapping.get("mappings", []):
        if not visible(case_data, item):
            continue

        value_path = item.get("value_path", "")
        if value_path and not has_path(case_data, value_path):
            continue

        raw_value = get_path(case_data, value_path) if value_path else item.get("fixed_value")
        fill_value = transform_value(raw_value, item.get("transform", ""))
        if fill_value == "":
            continue

        info = _field_info(item, controls)
        rows.append(
            {
                "section": info["section"],
                "form_order": info["form_order"],
                "display_no": info["display_no"],
                "label": item.get("label") or info["label"],
                "canonical_path": value_path,
                "source_paths": [value_path] if value_path else [],
                "field_name": item.get("field_name", ""),
                "field_id": item.get("field_id", ""),
                "input_type": item.get("input_type") or info["input_type"],
                "display_value": str(raw_value).strip(),
                "fill_value": fill_value,
                "source_page": item.get("source_page", "case_data"),
                "confidence": item.get("confidence", "generated"),
                "required": info["required"],
                "manual_required": item.get("manual_required", False),
                "notes": item.get("notes", ""),
            }
        )

    return rows


def build_application_data(
    case_doc: dict[str, Any],
    mapping: dict[str, Any],
    form_definitions: dict[str, Any],
) -> dict[str, Any]:
    case_data = case_doc.get("case_data", {})
    settings = case_doc.get("settings", {})
    source_data = dict(case_data)
    if settings:
        source_data["settings"] = settings
    workflow_state = case_doc.get("workflow_state") or case_data.get("case", {}).get("workflow_state", "")
    rows = build_rows(source_data, mapping, form_definitions)
    fillable = workflow_state == "ready_to_fill"
    warnings = [] if fillable else ["workflow_state is not ready_to_fill"]

    return {
        "schema_version": "1.0",
        "case_id": case_doc.get("case_id") or case_data.get("case", {}).get("case_id", ""),
        "workflow_state": workflow_state,
        "fillable": fillable,
        "mapping_version": mapping.get("schema_version", ""),
        "form_definition": mapping.get("form_definition") or form_definitions.get("source_file", ""),
        "warnings": warnings,
        "summary": {
            "rows_total": len(rows),
            "rows_fillable": len([row for row in rows if row["fill_value"]]),
            "rows_skipped_empty": len(mapping.get("mappings", [])) - len(rows),
            "manual_required": len([row for row in rows if row["manual_required"]]),
        },
        "rows": rows,
    }
